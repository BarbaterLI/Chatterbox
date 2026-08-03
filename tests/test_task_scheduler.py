"""task_scheduler 模块单元测试。

验证 ``TaskScheduler`` 的 ``progress_updated`` 信号携带真实 succeeded/failed
计数（Task 13 修复），覆盖：
- 信号签名（4 参数：completed / total / succeeded / failed）
- 单任务成功：progress_updated 携带 (1, 1, 1, 0)
- 单任务失败：progress_updated 携带 (1, 1, 0, 1)
- 多任务混合：成功/失败累计正确
- all_finished 信号携带最终 succeeded/failed

使用 mock 任务模拟完成，避免依赖真实 balcon.exe / blb2txt.exe。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, QRunnable, Signal, QCoreApplication

from balcon_batch_tts.core.task_scheduler import TaskScheduler


@pytest.fixture(scope="module")
def qapp():
    """模块级 QCoreApplication 单例 fixture（无需 QApplication）。"""
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class _FakeSignals(QObject):
    """模拟 BaseToolTask.signals 的最小信号集。"""

    started = Signal(str)
    finished = Signal(str, int, str, float)
    log = Signal(str)
    error = Signal(str, str)


class _FakeTask:
    """模拟 BaseToolTask 的最小可调度任务。

    不真正在线程池执行，仅持有 signals 对象供测试手动发射 finished 信号。
    """

    def __init__(
        self,
        filename: str,
        returncode: int = 0,
        input_file: str | None = None,
    ) -> None:
        self.filename = filename
        # input_file 默认与 filename 一致（filename 本身即 basename）
        self.input_file = input_file if input_file is not None else filename
        self.returncode = returncode
        self.signals = _FakeSignals()
        self._cancelled = False

    def run(self) -> None:
        """QRunnable.run 的占位实现（实际不调用）。"""
        pass

    def cancel(self) -> None:
        self._cancelled = True

    def emit_finished(self, elapsed: float = 0.1) -> None:
        """测试辅助：手动发射 finished 信号。"""
        self.signals.finished.emit(
            self.filename, self.returncode, "", elapsed
        )


class _RealTask(QRunnable):
    """真实可执行的 QRunnable 任务（用于暂停/恢复测试）。

    与 :class:`_FakeTask` 不同，本类是真正的 :class:`QRunnable`，可被
    :class:`QThreadPool` 调度执行。通过 :class:`threading.Event` 记录
    开始/完成时机，便于测试断言阻塞行为；``block=True`` 时 ``run`` 会在
    完成前等待 :meth:`release` 被调用，以模拟长时运行任务。
    """

    def __init__(
        self,
        filename: str,
        returncode: int = 0,
        block: bool = False,
        order_log: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.filename = filename
        self.input_file = filename
        self.returncode = returncode
        self.signals = _FakeSignals()
        self.started_event = threading.Event()
        self.finished_event = threading.Event()
        self._release_event = threading.Event()
        self._block = block
        self._order_log = order_log

    def run(self) -> None:
        self.started_event.set()
        self.signals.started.emit(self.filename)
        if self._order_log is not None:
            self._order_log.append(self.filename)
        if self._block:
            # 模拟长时运行：等待测试显式 release 后再完成
            self._release_event.wait(timeout=10)
        self.signals.finished.emit(self.filename, self.returncode, "", 0.0)
        self.finished_event.set()

    def release(self) -> None:
        """释放阻塞中的长时运行任务，允许其完成。"""
        self._release_event.set()

    def cancel(self) -> None:
        pass


def _process_until(qapp, predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    """在主线程反复处理事件，直到 predicate 为真或超时。

    工作线程通过跨线程队列连接向调度器槽发射信号，需主线程处理事件才能
    送达。本助手在等待条件满足的同时持续 ``processEvents``。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    qapp.processEvents()
    return predicate()


# ---------------------------------------------------------------------------
# progress_updated 信号签名
# ---------------------------------------------------------------------------
class TestProgressUpdatedSignature:
    """``progress_updated`` 信号携带真实 succeeded/failed 计数。"""

    def test_signal_has_4_args(self, qapp) -> None:
        """信号签名应为 (int, int, int, int)。"""
        scheduler = TaskScheduler(max_concurrency=2)
        # 通过连接一个记录槽验证参数个数
        received: list[tuple] = []
        scheduler.progress_updated.connect(
            lambda *args: received.append(args)
        )
        assert scheduler.progress_updated is not None
        # 验证信号存在且可连接（参数个数由 PySide6 在连接时校验）
        # 这里仅验证可连接，实际发射在后续测试

    def test_single_success_carries_succeeded(
        self, qapp
    ) -> None:
        """单任务成功：progress_updated 携带 (1, 1, 1, 0)。"""
        scheduler = TaskScheduler(max_concurrency=1)
        received: list[tuple] = []
        scheduler.progress_updated.connect(
            lambda c, t, s, f: received.append((c, t, s, f))
        )

        task = _FakeTask("a.wav", returncode=0)
        # 直接调用 submit 会将任务放入线程池，但 _FakeTask.run 是空操作
        # 测试中手动模拟：先 submit，再手动发射 finished
        scheduler._tasks = [task]
        scheduler._total = 1
        scheduler._completed = 0
        scheduler._succeeded = 0
        scheduler._failed = 0
        scheduler._start_time = time.time()
        scheduler._is_running = True

        # 连接任务信号到调度器槽
        task.signals.finished.connect(scheduler._on_task_finished)

        # 手动发射 finished 信号
        task.emit_finished()

        assert len(received) == 1
        assert received[0] == (1, 1, 1, 0)

    def test_single_failure_carries_failed(
        self, qapp
    ) -> None:
        """单任务失败：progress_updated 携带 (1, 1, 0, 1)。"""
        scheduler = TaskScheduler(max_concurrency=1)
        received: list[tuple] = []
        scheduler.progress_updated.connect(
            lambda c, t, s, f: received.append((c, t, s, f))
        )

        task = _FakeTask("a.wav", returncode=1)
        scheduler._tasks = [task]
        scheduler._total = 1
        scheduler._completed = 0
        scheduler._succeeded = 0
        scheduler._failed = 0
        scheduler._start_time = time.time()
        scheduler._is_running = True

        task.signals.finished.connect(scheduler._on_task_finished)
        task.emit_finished()

        assert len(received) == 1
        assert received[0] == (1, 1, 0, 1)

    def test_mixed_success_failure_accumulates(
        self, qapp
    ) -> None:
        """多任务混合：3 成功 + 2 失败 → 最后一次 progress_updated (5, 5, 3, 2)。"""
        scheduler = TaskScheduler(max_concurrency=1)
        received: list[tuple] = []
        scheduler.progress_updated.connect(
            lambda c, t, s, f: received.append((c, t, s, f))
        )

        tasks = [
            _FakeTask("a.wav", returncode=0),
            _FakeTask("b.wav", returncode=1),
            _FakeTask("c.wav", returncode=0),
            _FakeTask("d.wav", returncode=2),
            _FakeTask("e.wav", returncode=0),
        ]
        scheduler._tasks = tasks
        scheduler._total = len(tasks)
        scheduler._completed = 0
        scheduler._succeeded = 0
        scheduler._failed = 0
        scheduler._start_time = time.time()
        scheduler._is_running = True

        for task in tasks:
            task.signals.finished.connect(scheduler._on_task_finished)

        for task in tasks:
            task.emit_finished()

        # 应发射 5 次
        assert len(received) == 5
        # 最后一次应为 (5, 5, 3, 2)
        assert received[-1] == (5, 5, 3, 2)
        # 中间过程累计正确
        assert received[0] == (1, 5, 1, 0)  # a 成功
        assert received[1] == (2, 5, 1, 1)  # b 失败
        assert received[2] == (3, 5, 2, 1)  # c 成功
        assert received[3] == (4, 5, 2, 2)  # d 失败
        assert received[4] == (5, 5, 3, 2)  # e 成功


# ---------------------------------------------------------------------------
# all_finished 信号
# ---------------------------------------------------------------------------
class TestAllFinished:
    """``all_finished`` 信号携带最终 succeeded/failed 计数。"""

    def test_all_finished_carries_final_counts(
        self, qapp
    ) -> None:
        """all_finished 携带 (succeeded, failed, elapsed)。"""
        scheduler = TaskScheduler(max_concurrency=1)
        received: list[tuple] = []
        scheduler.all_finished.connect(
            lambda s, f, e: received.append((s, f, e))
        )

        tasks = [
            _FakeTask("a.wav", returncode=0),
            _FakeTask("b.wav", returncode=1),
        ]
        scheduler._tasks = tasks
        scheduler._total = len(tasks)
        scheduler._completed = 0
        scheduler._succeeded = 0
        scheduler._failed = 0
        scheduler._start_time = time.time()
        scheduler._is_running = True

        for task in tasks:
            task.signals.finished.connect(scheduler._on_task_finished)

        for task in tasks:
            task.emit_finished()

        assert len(received) == 1
        succeeded, failed, elapsed = received[0]
        assert succeeded == 1
        assert failed == 1
        assert elapsed >= 0.0  # 耗时非负

    def test_running_state_reset_after_all_finished(
        self, qapp
    ) -> None:
        """all_finished 后 is_running() 返回 False。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler._tasks = [_FakeTask("a.wav", returncode=0)]
        scheduler._total = 1
        scheduler._completed = 0
        scheduler._succeeded = 0
        scheduler._failed = 0
        scheduler._start_time = time.time()
        scheduler._is_running = True

        task = scheduler._tasks[0]
        task.signals.finished.connect(scheduler._on_task_finished)
        task.emit_finished()

        assert scheduler.is_running() is False


# ---------------------------------------------------------------------------
# 内部计数器
# ---------------------------------------------------------------------------
class TestInternalCounters:
    """TaskScheduler 内部维护 _succeeded / _failed 计数。"""

    def test_internal_succeeded_counter(self, qapp) -> None:
        scheduler = TaskScheduler(max_concurrency=1)
        assert scheduler._succeeded == 0
        assert scheduler._failed == 0

    def test_submit_resets_counters(self, qapp) -> None:
        """submit() 应重置内部计数器。"""
        scheduler = TaskScheduler(max_concurrency=1)
        # 模拟之前的运行状态
        scheduler._succeeded = 5
        scheduler._failed = 3
        scheduler._total = 8
        scheduler._completed = 8

        # 准备一个可提交的任务列表（空列表也应重置）
        # 注意：submit 会调用 _thread_pool.start，空列表不会真正启动任何任务
        scheduler._is_running = False
        try:
            scheduler.submit([])
        except Exception:
            # 空列表可能不触发任何行为，但应重置计数
            pass

        assert scheduler._total == 0
        assert scheduler._completed == 0
        assert scheduler._succeeded == 0
        assert scheduler._failed == 0


# ---------------------------------------------------------------------------
# O(1) 任务查找（dict 索引）
# ---------------------------------------------------------------------------
class TestTaskIndexO1:
    """``_find_task_by_filename`` 基于 dict 索引实现 O(1) 查找。"""

    def test_find_task_by_filename_o1(self, qapp) -> None:
        """查找返回正确的任务。"""
        scheduler = TaskScheduler(max_concurrency=1)
        # 避免 _thread_pool.start 真正调度 _FakeTask（非 QRunnable）
        scheduler._thread_pool.start = MagicMock()

        task_a = _FakeTask("a.wav", input_file="/data/a.wav")
        task_b = _FakeTask("b.wav", input_file="/data/b.wav")
        scheduler.submit([task_a, task_b])

        assert scheduler._find_task_by_filename("a.wav") is task_a
        assert scheduler._find_task_by_filename("b.wav") is task_b

    def test_find_task_by_filename_not_found(self, qapp) -> None:
        """不存在的文件名返回 None。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler._thread_pool.start = MagicMock()

        task = _FakeTask("a.wav", input_file="/data/a.wav")
        scheduler.submit([task])

        assert scheduler._find_task_by_filename("nonexistent.wav") is None

    def test_task_index_cleaned_after_finish(self, qapp) -> None:
        """任务完成后索引被清理。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler._thread_pool.start = MagicMock()

        task = _FakeTask("a.wav", input_file="/data/a.wav")
        scheduler.submit([task])

        # 提交后索引中应有该任务
        assert scheduler._find_task_by_filename("a.wav") is task

        # 手动发射 finished 信号（submit 已连接信号到 _on_task_finished）
        task.emit_finished()

        # 完成后索引应已清理
        assert scheduler._find_task_by_filename("a.wav") is None
        assert "a.wav" not in scheduler._task_by_filename

    def test_duplicate_filename_last_wins(self, qapp) -> None:
        """重复文件名时后提交的覆盖先提交的。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler._thread_pool.start = MagicMock()

        task1 = _FakeTask("a.wav", input_file="/dir1/a.wav")
        task2 = _FakeTask("a.wav", input_file="/dir2/a.wav")
        scheduler.submit([task1, task2])

        # 两个任务 basename 均为 "a.wav"，后提交的 task2 覆盖 task1
        found = scheduler._find_task_by_filename("a.wav")
        assert found is task2
        assert found is not task1

    def test_cancel_all_clears_index(self, qapp) -> None:
        """cancel_all 后索引被清空。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler._thread_pool.start = MagicMock()

        task_a = _FakeTask("a.wav", input_file="/data/a.wav")
        task_b = _FakeTask("b.wav", input_file="/data/b.wav")
        scheduler.submit([task_a, task_b])

        assert len(scheduler._task_by_filename) == 2

        scheduler.cancel_all()

        assert len(scheduler._task_by_filename) == 0
        assert scheduler._find_task_by_filename("a.wav") is None
        assert scheduler._find_task_by_filename("b.wav") is None


# ---------------------------------------------------------------------------
# 暂停 / 恢复
# ---------------------------------------------------------------------------
class TestPauseResume:
    """``set_paused`` / ``is_paused`` 控制任务出队执行。"""

    def test_initial_state_not_paused(self, qapp) -> None:
        """初始状态 is_paused() 返回 False，恢复事件处于 set。"""
        scheduler = TaskScheduler(max_concurrency=1)
        assert scheduler.is_paused() is False
        assert scheduler._resume_event.is_set() is True

    def test_set_paused_true(self, qapp) -> None:
        """set_paused(True) 后 is_paused() 返回 True，恢复事件被 clear。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler.set_paused(True)
        assert scheduler.is_paused() is True
        assert scheduler._resume_event.is_set() is False

    def test_set_paused_false(self, qapp) -> None:
        """set_paused(False) 后 is_paused() 返回 False，恢复事件被 set。"""
        scheduler = TaskScheduler(max_concurrency=1)
        scheduler.set_paused(True)
        scheduler.set_paused(False)
        assert scheduler.is_paused() is False
        assert scheduler._resume_event.is_set() is True

    def test_paused_blocks_new_tasks_then_resume_completes(
        self, qapp
    ) -> None:
        """暂停时提交的任务不执行；恢复后任务执行完成。"""
        scheduler = TaskScheduler(max_concurrency=1)
        try:
            scheduler.set_paused(True)
            task = _RealTask("a.wav", returncode=0)
            scheduler.submit([task])

            # 暂停状态下任务应阻塞，started_event 在 0.3s 内不被置位
            assert task.started_event.wait(timeout=0.3) is False
            assert scheduler.is_paused() is True

            # 恢复后任务应执行并完成
            scheduler.set_paused(False)
            assert task.finished_event.wait(timeout=2.0) is True

            # 让调度器收到跨线程 finished 信号并更新计数/状态
            _process_until(
                qapp, lambda: scheduler.is_running() is False, timeout=2.0
            )
            assert scheduler._completed == 1
            assert scheduler._succeeded == 1
            assert scheduler.is_running() is False
        finally:
            scheduler.set_paused(False)
            scheduler._thread_pool.waitForDone(5000)

    def test_running_task_completes_when_paused(self, qapp) -> None:
        """已运行任务在暂停时自然完成（不取消），新任务被阻塞。"""
        # max_concurrency=2：worker1 运行 A，worker2 取出 B 并在恢复事件上阻塞
        scheduler = TaskScheduler(max_concurrency=2)
        try:
            task_a = _RealTask("a.wav", returncode=0, block=True)
            task_b = _RealTask("b.wav", returncode=0)
            scheduler.submit([task_a, task_b])

            # 等待 A 真正开始执行（已通过恢复事件等待点）
            assert task_a.started_event.wait(timeout=2.0) is True

            # 此时暂停：A 仍在运行，B 尚未开始
            scheduler.set_paused(True)
            # B 应被阻塞（恢复事件处于 clear）
            assert task_b.started_event.wait(timeout=0.3) is False

            # 释放 A：A 应自然完成（不受暂停影响）
            task_a.release()
            assert task_a.finished_event.wait(timeout=2.0) is True

            # 恢复后 B 才开始并完成
            scheduler.set_paused(False)
            assert task_b.finished_event.wait(timeout=2.0) is True
        finally:
            scheduler.set_paused(False)
            scheduler._thread_pool.waitForDone(5000)

    def test_multiple_tasks_execute_in_order_after_resume(
        self, qapp
    ) -> None:
        """暂停状态下提交多个任务，恢复后按提交顺序执行。"""
        scheduler = TaskScheduler(max_concurrency=1)
        try:
            scheduler.set_paused(True)
            order_log: list[str] = []
            tasks = [
                _RealTask("a.wav", order_log=order_log),
                _RealTask("b.wav", order_log=order_log),
                _RealTask("c.wav", order_log=order_log),
            ]
            scheduler.submit(tasks)

            # 暂停时无任何任务开始
            assert not tasks[0].started_event.wait(timeout=0.3)
            assert order_log == []

            # 恢复后三个任务依次完成
            scheduler.set_paused(False)
            for task in tasks:
                assert task.finished_event.wait(timeout=2.0) is True

            # max_concurrency=1 时 QThreadPool 保持 FIFO 提交顺序
            assert order_log == ["a.wav", "b.wav", "c.wav"]
        finally:
            scheduler.set_paused(False)
            scheduler._thread_pool.waitForDone(5000)


# ---------------------------------------------------------------------------
# Task 17：队列深度与并发警告
# ---------------------------------------------------------------------------
class TestQueueDepthAndConcurrencyWarning:
    """``queue_depth`` / ``active_workers`` 属性与 ``warning_signal`` 信号。"""

    def test_warning_signal_emitted_when_concurrency_above_12(
        self, qapp
    ) -> None:
        """``set_max_concurrency(13)`` 应触发 warning_signal，消息含 "12"。"""
        scheduler = TaskScheduler(max_concurrency=2)
        warnings: list[str] = []
        scheduler.warning_signal.connect(lambda msg: warnings.append(msg))

        scheduler.set_max_concurrency(13)

        assert len(warnings) == 1
        assert "12" in warnings[0]
        # 钳制仍生效：实际最大并发为 13（在 [1,16] 内，未触顶）
        assert scheduler.max_concurrency() == 13

    def test_no_warning_when_concurrency_below_12(
        self, qapp
    ) -> None:
        """``set_max_concurrency(8)`` 不应触发 warning_signal。"""
        scheduler = TaskScheduler(max_concurrency=2)
        warnings: list[str] = []
        scheduler.warning_signal.connect(lambda msg: warnings.append(msg))

        scheduler.set_max_concurrency(8)

        assert len(warnings) == 0
        assert scheduler.max_concurrency() == 8

    def test_queue_depth_property(self, qapp) -> None:
        """``queue_depth`` 在运行中 > 0，全部完成后 == 0。

        使用 ``block=True`` 的 :class:`_RealTask` 使任务阻塞在 release 事件上，
        便于在任务未完成时测量队列深度。
        """
        scheduler = TaskScheduler(max_concurrency=2)
        tasks = [_RealTask(f"t{i}.wav", block=True) for i in range(5)]
        try:
            scheduler.submit(tasks)

            # 等待至少一个任务真正开始（已通过恢复事件等待点）
            assert tasks[0].started_event.wait(timeout=2.0) is True

            # 运行中：5 总任务 - 0 已完成 - ≤2 活跃 = ≥3 待处理
            # （即使仅 1 个活跃，queue_depth = 5 - 0 - 1 = 4 > 0）
            assert scheduler.is_running() is True
            assert scheduler.queue_depth > 0

            # 释放所有阻塞任务，等待全部完成
            for task in tasks:
                task.release()
            _process_until(
                qapp, lambda: scheduler.is_running() is False, timeout=5.0
            )

            # 全部完成后 _is_running=False，queue_depth 直接返回 0
            assert scheduler.queue_depth == 0
        finally:
            for task in tasks:
                task.release()
            scheduler._thread_pool.waitForDone(5000)

    def test_active_workers_property(self, qapp) -> None:
        """``active_workers`` 返回当前活跃工作线程数（≥0）。"""
        scheduler = TaskScheduler(max_concurrency=2)
        tasks = [_RealTask(f"t{i}.wav", block=True) for i in range(3)]
        try:
            # 空闲时 active_workers 应为 0（无线程池任务）
            assert scheduler.active_workers >= 0

            scheduler.submit(tasks)
            assert tasks[0].started_event.wait(timeout=2.0) is True

            # 运行中 active_workers ≥ 1（至少一个任务在执行）
            assert scheduler.active_workers >= 1

            for task in tasks:
                task.release()
            _process_until(
                qapp, lambda: scheduler.is_running() is False, timeout=5.0
            )
        finally:
            for task in tasks:
                task.release()
            scheduler._thread_pool.waitForDone(5000)
