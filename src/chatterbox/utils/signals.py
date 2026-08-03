"""Qt 信号定义：任务信号与日志信号。

- ``TaskSignals``：单个 balcon 任务执行过程中向主线程报告状态（开始/结束/日志/进度/错误）。
- ``LogSignals``：日志桥接信号，配合 ``utils.logging.GuiLogHandler`` 将标准库日志
  转发到 Qt 信号，便于 GUI 日志面板订阅。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from chatterbox.utils.logging import GuiLogHandler


class TaskSignals(QObject):
    """任务执行信号。

    由 ``core.worker.BalconTask`` 在子线程中发射，主窗口连接槽函数更新 UI。

    Signals:
        started(str): 任务开始，参数为输入文件名。
        finished(str, int, str, float): 任务结束，参数依次为文件名、返回码、
            stderr 摘要、耗时（秒）。
        log(str): 任务过程中的日志消息。
        progress(int, int): 进度更新，参数为已完成数与总数。
        error(str, str): 任务出错，参数为文件名与错误信息。
    """

    started = Signal(str)
    finished = Signal(str, int, str, float)
    log = Signal(str)
    progress = Signal(int, int)
    error = Signal(str, str)


class LogSignals(QObject):
    """日志信号：将日志记录通过 Qt 信号转发到 GUI。

    ``GuiLogHandler.emit`` 调用注册的回调，回调内通过 ``log_message`` 信号发射
    格式化后的日志文本，GUI 日志面板连接该信号即可实时显示日志。
    """

    _instance: LogSignals | None = None

    log_message = Signal(str)

    @classmethod
    def get_instance(cls) -> LogSignals:
        """返回单例，首次调用时创建。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def bridge_logging_to_signal() -> None:
    """将日志系统桥接到 Qt 信号。

    在 ``GuiLogHandler`` 单例上注册一个回调，回调内将格式化后的日志文本通过
    ``LogSignals.log_message`` 信号发射。应在 ``setup_logging`` 之后调用一次，
    此后所有 logger 输出都会被转发到 Qt 信号。
    """
    log_signals = LogSignals.get_instance()
    gui_handler = GuiLogHandler.get_instance()

    def _on_log(text: str) -> None:
        log_signals.log_message.emit(text)

    gui_handler.register(_on_log)
