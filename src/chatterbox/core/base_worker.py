"""工具任务基类模块。

定义 :class:`BaseToolTask`，封装单个外部工具任务的通用执行框架，继承自
:class:`PySide6.QtCore.QRunnable`。采用模板方法模式，子类只需实现
:meth:`BaseToolTask._build_args` 与 :meth:`BaseToolTask._exec` 即可接入
统一的信号发射、取消与日志机制。
"""

from __future__ import annotations

import os
import threading
import time
from abc import abstractmethod

from PySide6.QtCore import QRunnable

from chatterbox.utils.signals import TaskSignals


class BaseToolTask(QRunnable):
    """单个外部工具任务的 QRunnable 基类（模板方法模式）。

    子类必须实现 :meth:`_build_args` 与 :meth:`_exec`。基类 :meth:`run`
    负责统一的开始/结束信号发射、日志记录与耗时统计。

    取消通过 :class:`threading.Event` 实现，子类在 :meth:`_exec` 中轮询
    ``self._cancel_event`` 以便及时终止长时运行的外部进程。

    Attributes:
        input_file: 输入文件路径。
        output_path: 输出文件路径。
        index: 任务在批次中的序号（便于外部追踪）。
        signals: 任务信号对象。
    """

    def __init__(
        self,
        input_file: str,
        output_path: str | None,
        index: int = 0,
    ) -> None:
        super().__init__()
        self._input_file = input_file
        self._output_path = output_path
        self._index = index
        self.signals = TaskSignals()
        self._cancel_event = threading.Event()

    @property
    def input_file(self) -> str:
        return self._input_file

    @property
    def output_path(self) -> str | None:
        return self._output_path

    @property
    def index(self) -> int:
        return self._index

    def cancel(self) -> None:
        """请求取消任务。

        设置取消事件，通知 :meth:`_exec` 中的轮询循环及时退出。
        """
        self._cancel_event.set()

    def run(self) -> None:
        """QRunnable 入口：在子线程中执行任务（模板方法）。

        流程：发射 ``started`` 信号 → 调用 :meth:`_build_args` 构建参数 →
        调用 :meth:`_exec` 执行 → 按返回码发射 ``finished`` 信号。
        """
        start_time = time.time()
        filename = os.path.basename(self._input_file)

        self.signals.started.emit(filename)
        self.signals.log.emit(f"开始处理: {self._input_file}")

        args = self._build_args()
        returncode, _stdout, stderr = self._exec(args)

        elapsed = time.time() - start_time
        stderr_summary = stderr.replace("\n", " ").replace("\r", " ")[:200]

        self.signals.finished.emit(filename, returncode, stderr_summary, elapsed)
        self.signals.log.emit(
            f"完成: {filename} 返回码={returncode} 耗时={elapsed:.1f}s"
        )

    @abstractmethod
    def _build_args(self) -> list[str]:
        """构建工具命令行参数列表（不含可执行文件路径本身）。

        Returns:
            参数列表，如 ``['-n', 'Emma', '-s', '2']``。
        """
        raise NotImplementedError

    @abstractmethod
    def _exec(self, args: list[str]) -> tuple[int, str, str]:
        """执行工具命令。

        子类应在此方法内调用具体的外部工具，并负责捕获自身抛出的异常
        （发射 ``signals.error`` 信号后返回非零返回码），以确保基类
        :meth:`run` 模板流程不被打断。

        Args:
            args: 由 :meth:`_build_args` 生成的参数列表。

        Returns:
            ``(returncode, stdout, stderr)`` 元组。执行失败时返回码应为非零。
        """
        raise NotImplementedError


__all__ = ["BaseToolTask"]
