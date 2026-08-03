"""QApplication 初始化与异常兜底。"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from chatterbox.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def main(argv: Optional[list[str]] = None) -> int:
    """程序入口。

    Args:
        argv: 命令行参数，None 时使用 sys.argv。

    Returns:
        进程退出码。
    """
    if argv is None:
        argv = sys.argv

    setup_logging()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Chatterbox")
    app.setOrganizationName("chatterbox")

    # 全局异常兜底：未捕获的异常以对话框形式提示，避免静默崩溃
    _in_exception_hook = {"value": False}
    # 主窗口引用（异常 hook 中用于触发断点续传紧急保存）
    _main_window_ref = {"value": None}

    def _handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        # 防止异常 hook 内部再次抛异常导致无限递归
        if _in_exception_hook["value"]:
            return
        _in_exception_hook["value"] = True
        try:
            logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_tb))

            # 紧急保存断点续传记录（GUI 崩溃时立即记录进度）
            window = _main_window_ref["value"]
            if window is not None:
                try:
                    window.emergency_save_checkpoint()
                except Exception:  # noqa: BLE001
                    logger.warning("紧急保存断点续传失败", exc_info=True)

            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            QMessageBox.critical(
                None,
                "程序异常",
                f"程序遇到未处理的异常，将记录到日志：\n\n{exc_value}\n\n"
                "已尝试保存断点续传记录，下次启动时可恢复进度。\n"
                "详细信息见 chatterbox.log",
            )
        finally:
            _in_exception_hook["value"] = False

    sys.excepthook = _handle_exception

    # 延迟导入，确保日志先就绪
    from chatterbox.gui.main_window import MainWindow

    window = MainWindow()
    _main_window_ref["value"] = window
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
