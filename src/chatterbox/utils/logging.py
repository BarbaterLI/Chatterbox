"""日志配置：控制台 + 文件轮转 + GUI 信号。

提供 ``setup_logging`` 配置标准库 ``logging``，输出到控制台与轮转日志文件；
``GuiLogHandler`` 通过回调机制将日志记录转发到 GUI（典型场景：Qt 信号）。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Callable

logger = logging.getLogger(__name__)

LOG_FILE_NAME = "chatterbox.log"
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2MB
LOG_BACKUP_COUNT = 3

# 模块级缓存：当前日志文件的完整路径，由 setup_logging 设置
_log_file_path: str = ""


def setup_logging(level: int = logging.INFO, log_dir: str | None = None) -> logging.Logger:
    """配置 root logger：控制台 + 文件轮转。

    Args:
        level: 日志级别，默认 ``logging.INFO``。
        log_dir: 日志文件目录。若为 ``None``，则优先使用用户目录下的
            ``.chatterbox/logs/``，不可用时回退到当前目录下的 ``logs/``。

    Returns:
        配置好的 root logger。
    """
    global _log_file_path

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清空已有 handler，避免重复添加导致重复输出
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler（按大小轮转）
    if log_dir is not None:
        log_directory = log_dir
    else:
        user_home = os.path.expanduser("~")
        if user_home and user_home != "~":
            log_directory = os.path.join(user_home, ".chatterbox", "logs")
        else:
            log_directory = os.path.join(os.getcwd(), "logs")

    os.makedirs(log_directory, exist_ok=True)
    log_file_path = os.path.join(log_directory, LOG_FILE_NAME)
    _log_file_path = log_file_path

    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 若 GuiLogHandler 单例已存在（之前调用过 get_instance），重新附加到 root logger，
    # 保证 setup_logging 清空 handler 后日志仍能转发到 GUI 回调
    if GuiLogHandler._instance is not None:
        GuiLogHandler.get_instance()

    logger.debug("日志系统已初始化，日志文件：%s", log_file_path)
    return root_logger


class GuiLogHandler(logging.Handler):
    """将日志记录转发给注册的回调（用于 GUI 日志面板订阅）。

    通过 ``register`` 注册回调函数，``emit`` 时将格式化后的日志文本传给每个回调。
    回调异常会被捕获并忽略，避免日志系统因回调故障而崩溃。
    """

    _instance: GuiLogHandler | None = None

    def __init__(self) -> None:
        super().__init__()
        self._callbacks: list[Callable[[str], None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        """格式化 record 并调用所有回调，捕获并忽略回调异常。"""
        try:
            formatted_text = self.format(record)
        except Exception:
            return
        for callback in list(self._callbacks):
            try:
                callback(formatted_text)
            except Exception:
                # 忽略回调异常，避免日志系统崩溃
                pass

    def register(self, callback: Callable[[str], None]) -> None:
        """注册回调。重复注册同一回调会被忽略。"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback: Callable[[str], None]) -> None:
        """注销回调。"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    @classmethod
    def get_instance(cls) -> GuiLogHandler:
        """返回单例。

        首次调用时创建实例、设置格式器并添加到 root logger。
        后续调用若发现实例未附加到 root logger（例如 ``setup_logging`` 清空过
        handler），会重新附加，确保日志始终能转发到回调。
        """
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root_logger = logging.getLogger()
        if cls._instance not in root_logger.handlers:
            root_logger.addHandler(cls._instance)
        return cls._instance


def get_log_file_path() -> str:
    """返回当前日志文件的完整路径。

    若 ``setup_logging`` 尚未调用，返回空字符串。
    """
    return _log_file_path
