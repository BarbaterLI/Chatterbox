"""批量工具任务调度器。

定义 :class:`TaskScheduler`，基于 :class:`PySide6.QtCore.QThreadPool` 调度
:class:`chatterbox.core.base_worker.BaseToolTask` 的任意子类（如
:class:`chatterbox.core.worker.BalconTask`、blb2txt 任务等），
并对外暴露统一的批次信号（开始/结束/进度/日志/错误/全部完成）。

调度器在内部聚合各任务信号，统计成功/失败数与总耗时，便于 GUI 显示批次进度。

断点续传支持：
- :meth:`attach_checkpoint` 绑定 :class:`CheckpointManager` 后，
  每个任务完成时自动调用 ``mark_completed`` / ``mark_failed`` 更新 checkpoint
- :meth:`emergency_save_checkpoint` 用于程序崩溃前紧急保存当前进度
"""

from __future__ import annotations

import logging
import os
import threading
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from chatterbox.core.base_worker import BaseToolTask
from chatterbox.core.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


class _PausableRunnable(QRunnable):
    """QRunnable 包装器：在执行内部任务前等待调度器的恢复事件。

    当调度器暂停时（``_resume_event`` 处于 clear 状态），工作线程在
    :meth:`run` 入口处阻塞，从而阻止新任务开始执行；已通过该等待点
    （即已出队并真正开始执行）的任务继续运行直至完成，不受暂停影响。

    :attr:`_dequeued` 标志在 :meth:`run` 入口处（``wait()`` 之前）置为
    ``True``，用于 :meth:`TaskScheduler.cancel_all` 区分"已出队（运行中/
    暂停中）"与"仍在队列中（被 ``QThreadPool.clear()`` 清除）"的任务。
    清除的任务永远不会执行 :meth:`run`，因此 ``_dequeued`` 保持 ``False``。
    """

    def __init__(self, task: BaseToolTask, resume_event: threading.Event) -> None:
        super().__init__()
        self._task = task
        self._resume_event = resume_event
        self._dequeued: bool = False

    def run(self) -> None:
        # 标记已出队：cancel_all() 据此判断任务是否需要合成 finished 信号
        self._dequeued = True
        # 在真正执行任务前等待恢复：暂停时阻塞出队线程，恢复时唤醒。
        self._resume_event.wait()
        self._task.run()


class TaskScheduler(QObject):
    """批量工具任务调度器。

    通过 :class:`QThreadPool` 并发执行 :class:`BaseToolTask` 的任意子类
    （如 :class:`BalconTask`、blb2txt 任务等），控制最大并发数，并聚合各任务
    信号为本调度器信号，便于 UI 订阅。可在同一批次中混合调度不同工具的
    ``BaseToolTask`` 子类实例。

    断点续传：通过 :meth:`attach_checkpoint` 绑定 :class:`CheckpointManager`，
    每个任务完成时自动更新进度。全部完成时自动清除 checkpoint。

    Signals:
        all_finished(int, int, float): 全部任务完成，依次为成功数、失败数、总耗时（秒）。
        progress_updated(int, int, int, int): 进度更新，依次为已完成数、总数、
            成功数、失败数。``succeeded`` 与 ``failed`` 为累计真实计数（由
            ``task_finished`` 增量累计），便于 UI 实时显示分段着色。
            注意：信号签名固定为 4 参数，向后兼容，不在此处追加 queue_depth
            （PySide6 Signal 签名在类定义后不可变）。
        queue_depth_changed(int): 队列深度更新，参数为当前待处理任务数
            （总任务数 - 已完成 - 正在运行）。在 ``_on_task_finished`` 中
            于 ``progress_updated`` 之后发射，便于 UI 显示饱和状态。
        warning_signal(str): 警告消息，如并发数超过 12 时的崩溃风险提示。
        task_started(str): 某任务开始，参数为文件名。
        task_finished(str, int, str, float): 某任务结束，参数依次为文件名、
            返回码、stderr 摘要、耗时（秒）。
        task_log(str): 任务日志消息。
        task_error(str, str): 任务出错，参数为文件名与错误信息。
    """

    all_finished = Signal(int, int, float)
    progress_updated = Signal(int, int, int, int)
    queue_depth_changed = Signal(int)
    warning_signal = Signal(str)
    task_started = Signal(str)
    task_finished = Signal(str, int, str, float)
    task_log = Signal(str)
    task_error = Signal(str, str)

    def __init__(
        self,
        max_concurrency: int = 2,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool()
        self.set_max_concurrency(max_concurrency)
        self._tasks: list[BaseToolTask] = []
        # basename → task 索引，使 _find_task_by_filename 为 O(1)
        self._task_by_filename: dict[str, BaseToolTask] = {}
        self._total = 0
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._start_time = 0.0
        self._is_running = False
        # 暂停/恢复：_resume_event 初始为 set 状态（非暂停）；
        # 暂停时 clear() 阻塞出队线程，恢复时 set() 唤醒所有等待线程。
        self._paused: bool = False
        self._resume_event: threading.Event = threading.Event()
        self._resume_event.set()
        # 断点续传管理器（可选，通过 attach_checkpoint 绑定）
        self._checkpoint: CheckpointManager | None = None
        # 已出队的 _PausableRunnable 列表，cancel_all() 据此判断哪些任务
        # 被队列清除（未出队）需要合成 finished 信号。
        self._runnables: list[_PausableRunnable] = []
        # 已完成（含合成取消）的文件名集合，_on_task_finished 据此做幂等
        # 防护，避免同一任务的合成 finished 与真实 finished 双重计数。
        self._finished_filenames: set[str] = set()

    def set_max_concurrency(self, n: int) -> None:
        """设置最大并发线程数，钳制到 [1, 16]。

        当 ``n > 12`` 时通过 :attr:`warning_signal` 发出崩溃风险警告
        （符合项目硬约束：并发超过 12 可能引发崩溃，程序不负责由此导致的问题）。
        警告不影响设置生效——并发数仍按钳制值应用，仅提示风险。
        """
        clamped = max(1, min(16, n))
        self._thread_pool.setMaxThreadCount(clamped)
        if n > 12:
            self.warning_signal.emit(
                f"并发数 {n} 超过 12，可能引发崩溃，程序不负责由此导致的问题"
            )

    def max_concurrency(self) -> int:
        """返回当前最大并发线程数。"""
        return self._thread_pool.maxThreadCount()

    @property
    def queue_depth(self) -> int:
        """待处理任务数 = 总任务数 - 已完成 - 正在运行。"""
        if not self._is_running:
            return 0
        active = self._thread_pool.activeThreadCount()
        remaining = self._total - self._completed
        return max(0, remaining - active)

    @property
    def active_workers(self) -> int:
        """当前正在运行的任务数（活跃工作线程数）。"""
        return self._thread_pool.activeThreadCount()

    def is_running(self) -> bool:
        """是否仍有任务在运行。"""
        return self._is_running

    def set_paused(self, paused: bool) -> None:
        """暂停或恢复任务调度。

        - ``paused=True``：设置暂停标志并 ``clear`` 恢复事件，使尚未真正
          开始执行的任务（仍在 :class:`QThreadPool` 队列中或已被工作线程
          取出但尚未通过恢复事件等待点）阻塞，不再开始新的任务执行。
        - ``paused=False``：清除暂停标志并 ``set`` 恢复事件，唤醒所有
          阻塞在等待点的工作线程，继续按顺序执行后续任务。

        已通过恢复事件等待点（即已真正开始 ``run``）的任务将继续运行
        直至完成，不受暂停影响。

        线程安全：``_paused`` 为普通 bool（GIL 保证读写原子），
        :class:`threading.Event` 本身线程安全，``set()`` 会唤醒全部等待者。
        """
        self._paused = paused
        if paused:
            self._resume_event.clear()
        else:
            # set() 唤醒所有阻塞在 _resume_event.wait() 的工作线程
            self._resume_event.set()

    def is_paused(self) -> bool:
        """是否处于暂停状态。"""
        return self._paused

    def attach_checkpoint(self, mgr: CheckpointManager | None) -> None:
        """绑定断点续传管理器。

        绑定后，每个任务完成时会自动调用 ``mark_completed`` / ``mark_failed``
        更新 checkpoint；全部完成时自动清除 checkpoint。

        Args:
            mgr: :class:`CheckpointManager` 实例，``None`` 解绑。
        """
        self._checkpoint = mgr

    def emergency_save_checkpoint(self) -> None:
        """紧急保存 checkpoint（用于程序崩溃前调用）。

        线程安全，可从异常 hook 中调用。若未绑定 checkpoint 则 no-op。
        """
        if self._checkpoint is not None:
            self._checkpoint.save_snapshot()
            logger.info("已紧急保存断点续传记录")

    def submit(self, tasks: list[BaseToolTask]) -> None:
        """提交一批任务到线程池。

        Args:
            tasks: :class:`BaseToolTask` 子类实例列表，可在同一批次中混合
                不同工具的任务（如 ``BalconTask`` 与 blb2txt 任务）。

        Raises:
            RuntimeError: 已有任务在运行时调用。
        """
        if self._is_running:
            raise RuntimeError("已有任务在运行")

        self._total = len(tasks)
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._start_time = time.time()
        self._is_running = True
        self._tasks = list(tasks)
        self._task_by_filename.clear()
        self._runnables = []
        self._finished_filenames.clear()

        for task in self._tasks:
            self._task_by_filename[os.path.basename(task.input_file)] = task
            task.signals.started.connect(self.task_started.emit)
            task.signals.finished.connect(self._on_task_finished)
            task.signals.log.connect(self.task_log.emit)
            task.signals.error.connect(self.task_error.emit)
            # 包装为 _PausableRunnable：工作线程取出任务后先在恢复事件上
            # 等待，暂停时阻塞新任务开始，恢复后继续按顺序执行。
            runnable = _PausableRunnable(task, self._resume_event)
            self._runnables.append(runnable)
            self._thread_pool.start(runnable)

    def cancel_all(self) -> None:
        """取消所有任务：清除未启动任务，并对已运行任务请求取消。

        暂停状态下调用时，先设置 ``_resume_event`` 释放被阻塞的工作线程，
        否则已出队但阻塞在 ``wait()`` 的任务会因无法检查取消标志而死锁
        （修复 paused+cancel 死锁）。

        对于被 ``QThreadPool.clear()`` 清除的未出队任务，发射合成
        ``finished`` 信号（returncode=-1, stderr="已取消"），确保
        ``_completed`` 能达到 ``_total``，``all_finished`` 信号能正常触发。
        已出队的任务（``_dequeued=True``）会通过 ``task.run()`` 自然完成
        并发射真实 ``finished`` 信号。``_on_task_finished`` 中的
        ``_finished_filenames`` 幂等防护确保不会双重计数。
        """
        # 修复 paused+cancel 死锁：释放暂停状态下阻塞在 _resume_event.wait()
        # 的工作线程，使其能继续执行并检查取消标志。
        self._paused = False
        self._resume_event.set()

        self._thread_pool.clear()
        for task in self._tasks:
            task.cancel()

        # 对未出队的任务（被 clear() 清除）发射合成 finished 信号。
        # 已出队的任务（_dequeued=True）会通过 task.run() 自然完成。
        for runnable in self._runnables:
            if not runnable._dequeued:
                filename = os.path.basename(runnable._task.input_file)
                self._on_task_finished(filename, -1, "已取消", 0.0)

        logger.info("已请求取消全部 %d 个任务", len(self._tasks))

    @Slot(str, int, str, float)
    def _on_task_finished(
        self,
        filename: str,
        returncode: int,
        stderr: str,
        elapsed: float,
    ) -> None:
        """单个任务完成槽：累加计数、转发信号、更新 checkpoint。

        幂等防护：通过 ``_finished_filenames`` 集合确保同一文件名的完成
        信号只被计数一次。``cancel_all()`` 对未出队任务发射合成 finished
        后，若该任务随后又通过 ``task.run()`` 发射真实 finished（极端竞态），
        第二次调用会因文件名已在集合中而提前返回，避免双重计数。
        """
        if filename in self._finished_filenames:
            return
        self._finished_filenames.add(filename)

        self._completed += 1
        if returncode == 0:
            self._succeeded += 1
        else:
            self._failed += 1

        # 断点续传：标记完成/失败
        if self._checkpoint is not None:
            try:
                # 通过文件名反查 input_file
                task = self._find_task_by_filename(filename)
                if task is not None:
                    input_file = task.input_file
                    if returncode == 0:
                        self._checkpoint.mark_completed(input_file)
                    else:
                        self._checkpoint.mark_failed(input_file)
            except Exception as exc:  # noqa: BLE001
                logger.warning("更新 checkpoint 失败: %s", exc)

        # 从索引中移除已完成的任务，避免内存泄漏
        self._task_by_filename.pop(filename, None)

        self.progress_updated.emit(
            self._completed, self._total, self._succeeded, self._failed
        )
        # Task 17：通过独立信号发射队列深度（避免修改 progress_updated 4 参数签名）
        self.queue_depth_changed.emit(self.queue_depth)
        self.task_finished.emit(filename, returncode, stderr, elapsed)

        if self._completed >= self._total:
            self._finish_all()

    def _find_task_by_filename(self, filename: str) -> BaseToolTask | None:
        """根据文件名（basename）反查任务对象（O(1) dict 查找）。

        Args:
            filename: 任务完成信号中的文件名（通常为 basename）。

        Returns:
            匹配的 :class:`BaseToolTask`，未找到返回 ``None``。
        """
        return self._task_by_filename.get(filename)

    def _finish_all(self) -> None:
        """全部任务完成时调用：复位运行状态、清除 checkpoint、发射 all_finished。"""
        self._is_running = False
        total_elapsed = time.time() - self._start_time
        # 全部完成时清除 checkpoint（无未完成任务，无需恢复）
        if self._checkpoint is not None:
            try:
                self._checkpoint.clear()
            except Exception as exc:  # noqa: BLE001
                logger.warning("清除 checkpoint 失败: %s", exc)
        # 释放 runnable 引用与完成记录，避免跨批次内存泄漏
        self._runnables = []
        self._finished_filenames.clear()
        self.all_finished.emit(self._succeeded, self._failed, total_elapsed)


__all__ = ["TaskScheduler"]
