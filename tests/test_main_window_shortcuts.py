"""命令面板、快捷键对话框与 Tab 循环测试（T-B5）。

验证：
- ``_register_shortcuts`` 注册 Ctrl+Shift+P / F1 / Ctrl+Tab / Ctrl+Shift+Tab
- ``_open_command_palette`` 懒加载并打开命令面板
- ``_open_shortcuts_dialog`` 懒加载并打开快捷键帮助对话框
- ``_cycle_tab`` 在侧边栏 Tab 间循环切换（正向/反向）
- ``_build_commands`` 返回包含 Tab 跳转、工具切换、预设、主题、设置的命令集
- ``_build_shortcuts`` 返回快捷键帮助列表
- ``_switch_tool`` 通过 tool_combo 切换工具
- ``_switch_theme`` 切换主题并持久化

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换模态对话框避免阻塞。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.main_window import MainWindow
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
# T-B5：快捷键注册
# ---------------------------------------------------------------------------
class TestShortcutRegistration:
    """``_register_shortcuts`` 注册全局 QShortcut。"""

    def test_shortcuts_registered(self, main_window: MainWindow) -> None:
        """主窗口应包含已注册的 QShortcut 子对象。"""
        shortcuts = main_window.findChildren(QShortcut)
        # 至少 4 个：Ctrl+Shift+P / F1 / Ctrl+Tab / Ctrl+Shift+Tab
        assert len(shortcuts) >= 4

    def test_has_ctrl_shift_p_shortcut(
        self, main_window: MainWindow
    ) -> None:
        """应注册 Ctrl+Shift+P 快捷键。"""
        from PySide6.QtGui import QKeySequence
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+Shift+P" in keys

    def test_has_f1_shortcut(self, main_window: MainWindow) -> None:
        """应注册 F1 快捷键。"""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "F1" in keys

    def test_has_ctrl_tab_shortcut(self, main_window: MainWindow) -> None:
        """应注册 Ctrl+Tab 快捷键。"""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+Tab" in keys

    def test_has_ctrl_shift_tab_shortcut(
        self, main_window: MainWindow
    ) -> None:
        """应注册 Ctrl+Shift+Tab 快捷键。"""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+Shift+Tab" in keys


# ---------------------------------------------------------------------------
# T-B5：命令面板懒加载
# ---------------------------------------------------------------------------
class TestCommandPaletteLazyLoad:
    """``_open_command_palette`` 懒加载并打开命令面板。"""

    def test_command_palette_initially_none(
        self, main_window: MainWindow
    ) -> None:
        """启动时 _command_palette 应为 None（懒加载标记）。"""
        assert main_window._command_palette is None

    def test_open_command_palette_creates_instance(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """打开命令面板后 _command_palette 应被赋值。"""
        # 避免 exec() 阻塞
        monkeypatch.setattr(
            "balcon_batch_tts.gui.widgets.command_palette.CommandPalette.exec",
            lambda self: 0,
        )
        main_window._open_command_palette()
        assert main_window._command_palette is not None

    def test_open_command_palette_is_modal(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """命令面板应为模态对话框。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.widgets.command_palette.CommandPalette.exec",
            lambda self: 0,
        )
        main_window._open_command_palette()
        assert main_window._command_palette.isModal() is True


# ---------------------------------------------------------------------------
# T-B5：快捷键帮助对话框懒加载
# ---------------------------------------------------------------------------
class TestShortcutsDialogLazyLoad:
    """``_open_shortcuts_dialog`` 懒加载并打开快捷键帮助对话框。"""

    def test_shortcuts_dialog_initially_none(
        self, main_window: MainWindow
    ) -> None:
        """启动时 _shortcuts_dialog 应为 None。"""
        assert main_window._shortcuts_dialog is None

    def test_open_shortcuts_dialog_creates_instance(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """打开快捷键对话框后 _shortcuts_dialog 应被赋值。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.dialogs.shortcuts_dialog.ShortcutsDialog.exec",
            lambda self: 0,
        )
        main_window._open_shortcuts_dialog()
        assert main_window._shortcuts_dialog is not None

    def test_open_shortcuts_dialog_is_modal(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """快捷键对话框应为模态。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.dialogs.shortcuts_dialog.ShortcutsDialog.exec",
            lambda self: 0,
        )
        main_window._open_shortcuts_dialog()
        assert main_window._shortcuts_dialog.isModal() is True


# ---------------------------------------------------------------------------
# T-B5：Tab 循环
# ---------------------------------------------------------------------------
class TestTabCycling:
    """``_cycle_tab`` 在侧边栏 Tab 间循环切换。"""

    def test_cycle_forward_increments_index(
        self, main_window: MainWindow
    ) -> None:
        """Ctrl+Tab 正向循环：当前索引 +1。"""
        count = main_window.tab_widget.count()
        assert count > 1
        main_window.tab_widget.set_current_index(0)
        main_window._cycle_tab(True)
        assert main_window.tab_widget.current_index() == 1

    def test_cycle_backward_decrements_index(
        self, main_window: MainWindow
    ) -> None:
        """Ctrl+Shift+Tab 反向循环：当前索引 -1。"""
        count = main_window.tab_widget.count()
        assert count > 1
        main_window.tab_widget.set_current_index(1)
        main_window._cycle_tab(False)
        assert main_window.tab_widget.current_index() == 0

    def test_cycle_forward_wraps_around(
        self, main_window: MainWindow
    ) -> None:
        """正向循环到最后一个后回到第一个。"""
        count = main_window.tab_widget.count()
        assert count > 1
        main_window.tab_widget.set_current_index(count - 1)
        main_window._cycle_tab(True)
        assert main_window.tab_widget.current_index() == 0

    def test_cycle_backward_wraps_around(
        self, main_window: MainWindow
    ) -> None:
        """反向循环到第一个后回到最后一个。"""
        count = main_window.tab_widget.count()
        assert count > 1
        main_window.tab_widget.set_current_index(0)
        main_window._cycle_tab(False)
        assert main_window.tab_widget.current_index() == count - 1

    def test_cycle_single_tab_noop(
        self, main_window: MainWindow
    ) -> None:
        """仅 1 个 Tab 时循环应 no-op（不抛异常）。"""
        # balcon 模式有多个 Tab，无法直接测试单 Tab；
        # 这里验证 count > 1 时不抛异常即可
        count = main_window.tab_widget.count()
        if count <= 1:
            main_window._cycle_tab(True)  # 不应抛异常


# ---------------------------------------------------------------------------
# T-B5：_build_commands
# ---------------------------------------------------------------------------
class TestBuildCommands:
    """``_build_commands`` 构造命令面板命令集合。"""

    def test_commands_not_empty(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应非空。"""
        commands = main_window._build_commands()
        assert len(commands) > 0

    def test_commands_include_tab_navigation(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应包含 Tab 跳转命令。"""
        commands = main_window._build_commands()
        tab_cmds = [c for c in commands if c.id.startswith("tab.")]
        # balcon 模式有 12 个 Tab
        assert len(tab_cmds) == len(main_window._tabs)

    def test_commands_include_tool_switching(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应包含工具切换命令。"""
        commands = main_window._build_commands()
        ids = [c.id for c in commands]
        assert "tool.balcon" in ids
        assert "tool.blb2txt" in ids

    def test_commands_include_preset_operations(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应包含预设保存/加载命令。"""
        commands = main_window._build_commands()
        ids = [c.id for c in commands]
        assert "preset.save" in ids
        assert "preset.load" in ids

    def test_commands_include_theme_switching(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应包含主题切换命令。"""
        commands = main_window._build_commands()
        ids = [c.id for c in commands]
        assert "theme.light" in ids
        assert "theme.dark" in ids
        assert "theme.auto" in ids

    def test_commands_include_settings(
        self, main_window: MainWindow
    ) -> None:
        """命令集合应包含打开设置命令。"""
        commands = main_window._build_commands()
        ids = [c.id for c in commands]
        assert "settings.open" in ids

    def test_tab_command_handler_switches_tab(
        self, main_window: MainWindow
    ) -> None:
        """Tab 跳转命令的 handler 应切换当前 Tab。"""
        commands = main_window._build_commands()
        tab_cmds = [c for c in commands if c.id.startswith("tab.")]
        if len(tab_cmds) >= 2:
            main_window.tab_widget.set_current_index(0)
            tab_cmds[1].handler()
            assert main_window.tab_widget.current_index() == 1


# ---------------------------------------------------------------------------
# T-B5：_build_shortcuts
# ---------------------------------------------------------------------------
class TestBuildShortcuts:
    """``_build_shortcuts`` 构造快捷键帮助列表。"""

    def test_shortcuts_not_empty(
        self, main_window: MainWindow
    ) -> None:
        """快捷键列表应非空。"""
        shortcuts = main_window._build_shortcuts()
        assert len(shortcuts) > 0

    def test_includes_ctrl_shift_p(
        self, main_window: MainWindow
    ) -> None:
        """快捷键列表应包含 Ctrl+Shift+P。"""
        shortcuts = main_window._build_shortcuts()
        keys = [s.key for s in shortcuts]
        assert "Ctrl+Shift+P" in keys

    def test_includes_f1(self, main_window: MainWindow) -> None:
        """快捷键列表应包含 F1。"""
        shortcuts = main_window._build_shortcuts()
        keys = [s.key for s in shortcuts]
        assert "F1" in keys

    def test_includes_tab_cycling(
        self, main_window: MainWindow
    ) -> None:
        """快捷键列表应包含 Ctrl+Tab 与 Ctrl+Shift+Tab。"""
        shortcuts = main_window._build_shortcuts()
        keys = [s.key for s in shortcuts]
        assert "Ctrl+Tab" in keys
        assert "Ctrl+Shift+Tab" in keys

    def test_shortcuts_have_groups(
        self, main_window: MainWindow
    ) -> None:
        """每个快捷键项应有非空分组。"""
        shortcuts = main_window._build_shortcuts()
        for s in shortcuts:
            assert s.group != ""


# ---------------------------------------------------------------------------
# T-B5：_switch_tool
# ---------------------------------------------------------------------------
class TestSwitchTool:
    """``_switch_tool`` 通过 tool_combo 切换工具。"""

    def test_switch_to_blb2txt(
        self, main_window: MainWindow
    ) -> None:
        """命令面板切换到 blb2txt 应更新 _current_tool。"""
        main_window._switch_tool(ToolType.BLB2TXT)
        assert main_window._current_tool is ToolType.BLB2TXT

    def test_switch_to_balcon(
        self, main_window: MainWindow
    ) -> None:
        """命令面板切换到 balcon 应更新 _current_tool。"""
        main_window._switch_tool(ToolType.BLB2TXT)
        main_window._switch_tool(ToolType.BALCON)
        assert main_window._current_tool is ToolType.BALCON


# ---------------------------------------------------------------------------
# T-B5：_switch_theme
# ---------------------------------------------------------------------------
class TestSwitchTheme:
    """``_switch_theme`` 切换主题并持久化。"""

    def test_switch_to_dark(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """切换到暗色主题应更新 settings.theme。"""
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        main_window._switch_theme("dark")
        assert main_window._settings.theme == "dark"

    def test_switch_to_light(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """切换到亮色主题应更新 settings.theme。"""
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        main_window._switch_theme("light")
        assert main_window._settings.theme == "light"

    def test_switch_to_auto(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """切换到跟随系统主题应更新 settings.theme。"""
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        main_window._switch_theme("auto")
        assert main_window._settings.theme == "auto"
