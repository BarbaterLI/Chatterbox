"""状态栏增强测试（T-C6 + T-D2）。

T-C6 验证：
- 状态栏中段 balcon 路径标签为 ``_ClickableLabel``，支持点击复制与 Ctrl+Click
  打开资源管理器
- 并发数标签为 ``_ClickableLabel``，点击打开设置对话框
- ``_open_path_in_explorer`` 在资源管理器中打开所在目录
- ``_on_copy_balcon_path`` 复制路径到剪贴板

T-D2 验证：
- 状态栏中段路径校验指示器（``InlineIndicator``）在路径无效时显示红色✗
- 点击指示器调用 ``_on_settings`` 打开设置对话框
- ``_validate_balcon_path`` / ``_validate_blb2txt_path`` 更新指示器与按钮状态
  （不弹 QMessageBox）

测试在 offscreen Qt 平台下运行。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.main_window import MainWindow, _ClickableLabel
from balcon_batch_tts.gui.widgets.inline_indicator import InlineIndicator
from balcon_batch_tts.persistence.settings import AppSettings


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
def _make_fake_exe(tmp_path, name: str) -> str:
    """在 tmp_path 下创建一个空文件作为伪可执行文件，返回绝对路径。"""
    fake = tmp_path / name
    fake.write_text("")
    return str(fake)


@pytest.fixture
def fake_settings(tmp_path) -> AppSettings:
    """返回三个路径均有效的 AppSettings 实例。"""
    return AppSettings(
        balcon_path=_make_fake_exe(tmp_path, "balcon.exe"),
        blb2txt_path=_make_fake_exe(tmp_path, "blb2txt.exe"),
        blb2txt_lite_path=_make_fake_exe(tmp_path, "blb2txt_lite.exe"),
        max_concurrency=2,
    )


@pytest.fixture
def main_window(
    qapp: QApplication,
    fake_settings: AppSettings,
    monkeypatch,
) -> MainWindow:
    """构造一个 MainWindow 实例，禁用弹窗与枚举。"""
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.warning", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.critical", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.information", lambda *a, **k: 0
    )
    monkeypatch.setattr(MainWindow, "_refresh_voices_devices", lambda self: None)
    monkeypatch.setattr(
        AppSettings, "load", classmethod(lambda cls, path=None: fake_settings)
    )
    return MainWindow()


# ---------------------------------------------------------------------------
# T-C6：_ClickableLabel 信号
# ---------------------------------------------------------------------------
class TestClickableLabelSignals:
    """``_ClickableLabel`` 的 clicked 与 ctrl_clicked 信号。"""

    def test_balcon_path_label_is_clickable_label(
        self, main_window: MainWindow
    ) -> None:
        """状态栏中段标签应为 _ClickableLabel 实例。"""
        assert isinstance(main_window._balcon_path_label, _ClickableLabel)

    def test_concurrency_label_is_clickable_label(
        self, main_window: MainWindow
    ) -> None:
        """并发数标签应为 _ClickableLabel 实例。"""
        assert isinstance(main_window._concurrency_label, _ClickableLabel)

    def test_clickable_label_has_clicked_signal(
        self, main_window: MainWindow
    ) -> None:
        """_ClickableLabel 应有 clicked 信号。"""
        assert hasattr(main_window._balcon_path_label, "clicked")

    def test_clickable_label_has_ctrl_clicked_signal(
        self, main_window: MainWindow
    ) -> None:
        """_ClickableLabel 应有 ctrl_clicked 信号。"""
        assert hasattr(main_window._balcon_path_label, "ctrl_clicked")


# ---------------------------------------------------------------------------
# T-C6：点击复制路径
# ---------------------------------------------------------------------------
class TestCopyBalconPath:
    """``_on_copy_balcon_path`` 复制路径到剪贴板。"""

    def test_copy_balcon_path_to_clipboard(
        self, main_window: MainWindow
    ) -> None:
        """点击 balcon 路径标签应复制路径到剪贴板。"""
        # balcon 模式
        main_window._on_copy_balcon_path()
        clipboard_text = QGuiApplication.clipboard().text()
        assert clipboard_text == main_window._settings.balcon_path

    def test_copy_blb2txt_path_to_clipboard(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 模式下点击应复制 blb2txt 路径。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window._on_copy_balcon_path()
        clipboard_text = QGuiApplication.clipboard().text()
        assert clipboard_text == main_window._settings.blb2txt_path

    def test_copy_empty_path_shows_status(
        self, main_window: MainWindow
    ) -> None:
        """路径为空时不应复制，应在状态栏显示提示。"""
        main_window._settings.balcon_path = ""
        # 不应抛异常
        main_window._on_copy_balcon_path()
        # 剪贴板不应包含空路径
        # （不严格断言剪贴板内容，仅验证不抛异常）


# ---------------------------------------------------------------------------
# T-C6：Ctrl+Click 打开资源管理器
# ---------------------------------------------------------------------------
class TestOpenPathInExplorer:
    """``_open_path_in_explorer`` 在资源管理器中打开所在目录。"""

    def test_open_balcon_path_directory(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """Ctrl+Click 应调用 os.startfile 打开 balcon 所在目录。"""
        startfile_calls: list = []
        monkeypatch.setattr(
            "os.startfile", lambda path: startfile_calls.append(path)
        )
        main_window._open_path_in_explorer()
        assert len(startfile_calls) == 1
        # 应打开 balcon 路径所在目录
        expected_dir = os.path.dirname(main_window._settings.balcon_path)
        assert startfile_calls[0] == expected_dir

    def test_open_blb2txt_path_directory(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """blb2txt 模式下应打开 blb2txt 所在目录。"""
        startfile_calls: list = []
        monkeypatch.setattr(
            "os.startfile", lambda path: startfile_calls.append(path)
        )
        main_window.tool_combo.setCurrentIndex(1)
        main_window._open_path_in_explorer()
        assert len(startfile_calls) == 1
        expected_dir = os.path.dirname(main_window._settings.blb2txt_path)
        assert startfile_calls[0] == expected_dir

    def test_empty_path_shows_status(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """路径为空时不应调用 os.startfile。"""
        startfile_calls: list = []
        monkeypatch.setattr(
            "os.startfile", lambda path: startfile_calls.append(path)
        )
        main_window._settings.balcon_path = ""
        main_window._open_path_in_explorer()
        assert len(startfile_calls) == 0


# ---------------------------------------------------------------------------
# T-C6：并发数标签点击打开设置
# ---------------------------------------------------------------------------
class TestConcurrencyLabelClick:
    """并发数标签点击应打开设置对话框。"""

    def test_click_concurrency_label_opens_settings(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """点击并发数标签应调用 _on_settings。"""
        settings_called: list = []
        monkeypatch.setattr(
            main_window, "_on_settings", lambda: settings_called.append(True)
        )
        main_window._concurrency_label.clicked.emit()
        assert len(settings_called) == 1


# ---------------------------------------------------------------------------
# T-D2：路径校验内联指示器
# ---------------------------------------------------------------------------
class TestPathIndicator:
    """状态栏路径校验指示器行为。"""

    def test_path_indicator_is_inline_indicator(
        self, main_window: MainWindow
    ) -> None:
        """状态栏应包含 InlineIndicator 路径指示器。"""
        assert isinstance(main_window._path_indicator, InlineIndicator)

    def test_valid_path_hides_indicator(
        self, main_window: MainWindow
    ) -> None:
        """路径有效时指示器应为 hidden 状态。"""
        main_window._validate_balcon_path()
        assert main_window._path_indicator._state == "hidden"

    def test_invalid_path_shows_error_indicator(
        self, main_window: MainWindow
    ) -> None:
        """路径无效时指示器应为 error 状态。"""
        main_window._settings.balcon_path = "C:/nonexistent/balcon.exe"
        main_window._validate_balcon_path()
        assert main_window._path_indicator._state == "error"

    def test_indicator_clicked_opens_settings(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """点击路径指示器应调用 _on_settings。"""
        settings_called: list = []
        monkeypatch.setattr(
            main_window, "_on_settings", lambda: settings_called.append(True)
        )
        main_window._path_indicator.clicked.emit()
        assert len(settings_called) == 1

    def test_update_path_indicator_valid(
        self, main_window: MainWindow
    ) -> None:
        """``_update_path_indicator(valid=True, ...)`` 应隐藏指示器。"""
        main_window._update_path_indicator(True, "balcon")
        assert main_window._path_indicator._state == "hidden"

    def test_update_path_indicator_invalid(
        self, main_window: MainWindow
    ) -> None:
        """``_update_path_indicator(valid=False, ...)`` 应显示 error。"""
        main_window._update_path_indicator(False, "balcon")
        assert main_window._path_indicator._state == "error"

    def test_update_path_indicator_error_text_contains_tool_name(
        self, main_window: MainWindow
    ) -> None:
        """error 状态的指示器文本应包含工具名。"""
        main_window._update_path_indicator(False, "balcon")
        # 通过 _label 文本间接验证（包含 "balcon 路径无效"）
        label_text = main_window._path_indicator._label.text()
        assert "balcon" in label_text


# ---------------------------------------------------------------------------
# T-D2：_validate_balcon_path 不弹 QMessageBox
# ---------------------------------------------------------------------------
class TestValidateBalconPathNoDialog:
    """``_validate_balcon_path`` 不弹 QMessageBox（改为内联指示器）。"""

    def test_invalid_path_does_not_show_messagebox(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """路径无效时不应调用 QMessageBox.warning/critical。"""
        warning_calls: list = []
        critical_calls: list = []
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.warning",
            lambda *a, **k: warning_calls.append(a) or 0,
        )
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.critical",
            lambda *a, **k: critical_calls.append(a) or 0,
        )
        main_window._settings.balcon_path = "C:/nonexistent/balcon.exe"
        main_window._validate_balcon_path()
        assert len(warning_calls) == 0
        assert len(critical_calls) == 0

    def test_valid_path_enables_start_button(
        self, main_window: MainWindow
    ) -> None:
        """路径有效时开始按钮应启用。"""
        main_window._validate_balcon_path()
        assert main_window.start_action.isEnabled() is True

    def test_invalid_path_disables_start_button(
        self, main_window: MainWindow
    ) -> None:
        """路径无效时开始按钮应禁用。"""
        main_window._settings.balcon_path = "C:/nonexistent/balcon.exe"
        main_window._validate_balcon_path()
        assert main_window.start_action.isEnabled() is False

    def test_returns_bool(self, main_window: MainWindow) -> None:
        """``_validate_balcon_path`` 应返回 bool。"""
        result = main_window._validate_balcon_path()
        assert isinstance(result, bool)
        assert result is True  # fake_settings 路径有效

    def test_returns_false_for_invalid(self, main_window: MainWindow) -> None:
        """路径无效时应返回 False。"""
        main_window._settings.balcon_path = "C:/nonexistent/balcon.exe"
        result = main_window._validate_balcon_path()
        assert result is False


# ---------------------------------------------------------------------------
# T-D2：_validate_blb2txt_path
# ---------------------------------------------------------------------------
class TestValidateBlb2txtPath:
    """``_validate_blb2txt_path`` 行为。"""

    def test_valid_path_no_indicator(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 路径有效时不应显示指示器（在 blb2txt 模式下）。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window._validate_blb2txt_path()
        assert main_window._path_indicator._state == "hidden"

    def test_invalid_path_shows_indicator(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 路径无效时应显示 error 指示器。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window._settings.blb2txt_path = "C:/nonexistent/blb2txt.exe"
        main_window._validate_blb2txt_path()
        assert main_window._path_indicator._state == "error"

    def test_invalid_path_disables_start(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 路径无效时开始按钮应禁用。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window._settings.blb2txt_path = "C:/nonexistent/blb2txt.exe"
        main_window._validate_blb2txt_path()
        assert main_window.start_action.isEnabled() is False

    def test_no_messagebox_on_invalid(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """blb2txt 路径无效时不弹 QMessageBox。"""
        warning_calls: list = []
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.warning",
            lambda *a, **k: warning_calls.append(a) or 0,
        )
        main_window.tool_combo.setCurrentIndex(1)
        main_window._settings.blb2txt_path = "C:/nonexistent/blb2txt.exe"
        main_window._validate_blb2txt_path()
        assert len(warning_calls) == 0


# ---------------------------------------------------------------------------
# T-D2：状态栏三段式布局
# ---------------------------------------------------------------------------
class TestStatusBarLayout:
    """状态栏三段式布局验证。"""

    def test_status_label_exists(self, main_window: MainWindow) -> None:
        """状态栏应包含 _status_label。"""
        assert main_window._status_label is not None

    def test_balcon_path_label_exists(self, main_window: MainWindow) -> None:
        """状态栏应包含 _balcon_path_label。"""
        assert main_window._balcon_path_label is not None

    def test_concurrency_label_exists(self, main_window: MainWindow) -> None:
        """状态栏应包含 _concurrency_label。"""
        assert main_window._concurrency_label is not None

    def test_concurrency_label_text_format(
        self, main_window: MainWindow
    ) -> None:
        """并发数标签文本应包含「并发」与「语音」。"""
        text = main_window._concurrency_label.text()
        assert "并发" in text
        assert "语音" in text

    def test_balcon_path_label_text_format(
        self, main_window: MainWindow
    ) -> None:
        """balcon 路径标签文本应以 'balcon:' 开头。"""
        text = main_window._balcon_path_label.text()
        assert text.startswith("balcon:")

    def test_concurrency_label_clickable(
        self, main_window: MainWindow
    ) -> None:
        """并发数标签应有点击 cursor。"""
        from PySide6.QtCore import Qt
        assert (
            main_window._concurrency_label.cursor().shape()
            == Qt.CursorShape.PointingHandCursor
        )

    def test_balcon_path_label_clickable(
        self, main_window: MainWindow
    ) -> None:
        """balcon 路径标签应有点击 cursor。"""
        from PySide6.QtCore import Qt
        assert (
            main_window._balcon_path_label.cursor().shape()
            == Qt.CursorShape.PointingHandCursor
        )
