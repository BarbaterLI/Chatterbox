"""MainWindow 集成测试。

验证 Task 24-26 的主窗口集成：
- Task 24：工具选择器（balcon / blb2txt）位于工具栏首位，切换时正确
  清空与重建 Tab 集合。
- Task 25：``_on_start`` 与 ``_on_preview`` 按当前工具分支，
  blb2txt 模式下根据 PDF 扩展名选用主版本或精简版路径。
- Task 26：SettingsDialog 新增 blb2txt 路径行，``_on_settings`` 保存
  blb2txt 路径到 AppSettings。

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换 QMessageBox、
QFileDialog、dialog.exec() 与调度器，避免真实交互与子进程执行。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.blb2txt_worker import Blb2txtTask
from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.main_window import MainWindow, SettingsDialog
from balcon_batch_tts.persistence.settings import AppSettings


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 测试辅助：构造可用路径的 settings（避免路径校验弹窗阻塞）
# ---------------------------------------------------------------------------
def _make_fake_exe(tmp_path, name: str) -> str:
    """在 tmp_path 下创建一个空文件作为伪可执行文件，返回绝对路径。"""
    fake = tmp_path / name
    fake.write_text("")
    return str(fake)


@pytest.fixture
def fake_settings(tmp_path) -> AppSettings:
    """返回三个路径均有效的 AppSettings 实例（避免路径无效弹窗）。"""
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
    """构造一个 MainWindow 实例，禁用 QMessageBox 弹窗与枚举工作者。"""
    # 禁用 QMessageBox 警告（路径校验失败时调用）
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.warning", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.critical", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.information", lambda *a, **k: 0
    )
    # 禁用启动时的语音/设备枚举（避免后台线程触发未定义行为）
    monkeypatch.setattr(MainWindow, "_refresh_voices_devices", lambda self: None)
    # AppSettings.load 默认从磁盘读取，替换为 fake_settings
    monkeypatch.setattr(AppSettings, "load", classmethod(lambda cls, path=None: fake_settings))
    return MainWindow()


# ---------------------------------------------------------------------------
# Task 24：工具选择器
# ---------------------------------------------------------------------------
class TestToolSelector:
    """工具选择器 QComboBox 行为。"""

    def test_tool_combo_has_three_items(self, main_window: MainWindow) -> None:
        """工具选择器应包含 3 项（balcon / blb2txt / sapi）。"""
        assert main_window.tool_combo.count() == 3

    def test_tool_combo_first_item_is_balcon(
        self, main_window: MainWindow
    ) -> None:
        """首项为 balcon TTS。

        注意：PySide6 QVariant 会将 ToolType(str, Enum) 降级为 str，
        因此使用 == 比较（ToolType 继承自 str，``'balcon' == ToolType.BALCON``
        为 True）。
        """
        assert main_window.tool_combo.itemData(0) == ToolType.BALCON

    def test_tool_combo_second_item_is_blb2txt(
        self, main_window: MainWindow
    ) -> None:
        """第二项为 blb2txt 文本提取。

        注意：PySide6 QVariant 会将 ToolType(str, Enum) 降级为 str，
        因此使用 == 比较。
        """
        assert main_window.tool_combo.itemData(1) == ToolType.BLB2TXT

    def test_tool_combo_third_item_is_sapi(
        self, main_window: MainWindow
    ) -> None:
        """第三项为 SAPI5 直达 TTS。

        注意：PySide6 QVariant 会将 ToolType(str, Enum) 降级为 str，
        因此使用 == 比较。
        """
        assert main_window.tool_combo.itemData(2) == ToolType.SAPI

    def test_initial_tool_is_balcon(self, main_window: MainWindow) -> None:
        """启动时默认工具为 balcon。"""
        assert main_window._current_tool is ToolType.BALCON

    def test_tool_combo_displays_display_name(
        self, main_window: MainWindow
    ) -> None:
        """comboBox 文本应使用 ToolType.display_name。"""
        assert main_window.tool_combo.itemText(0) == ToolType.BALCON.display_name
        assert main_window.tool_combo.itemText(1) == ToolType.BLB2TXT.display_name
        assert main_window.tool_combo.itemText(2) == ToolType.SAPI.display_name


# ---------------------------------------------------------------------------
# Task 24：工具切换
# ---------------------------------------------------------------------------
class TestToolSwitching:
    """``_on_tool_changed`` 切换行为。"""

    def test_switch_to_blb2txt_loads_blb2txt_tabs(
        self, main_window: MainWindow
    ) -> None:
        """切换到 blb2txt 后侧边栏应加载 blb2txt Tab 集合。"""
        main_window.tool_combo.setCurrentIndex(1)
        assert main_window._current_tool is ToolType.BLB2TXT
        # blb2txt 模式下 _tabs 非空
        assert len(main_window._tabs) > 0
        # 所有已加载 Tab 的 tab_tool() 均为 BLB2TXT
        for tab in main_window._tabs:
            assert type(tab).tab_tool() is ToolType.BLB2TXT

    def test_switch_back_to_balcon_loads_balcon_tabs(
        self, main_window: MainWindow
    ) -> None:
        """切换到 blb2txt 再切回 balcon 后应加载 balcon Tab 集合。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window.tool_combo.setCurrentIndex(0)
        assert main_window._current_tool is ToolType.BALCON
        # balcon 模式下 _tabs 应为 12 个（Task 4b 合并 SilenceTab 入 VoiceTab）
        assert len(main_window._tabs) == 12
        for tab in main_window._tabs:
            assert type(tab).tab_tool() is ToolType.BALCON

    def test_switch_preserves_balcon_config_state(
        self, main_window: MainWindow
    ) -> None:
        """balcon → blb2txt → balcon 往返后 OutputTab 状态应保留。"""
        output_tab = main_window._tabs_by_id.get("output")
        assert output_tab is not None
        original_dir = "C:/test_output_dir"
        original_template = "{name}_{i}.wav"
        output_tab.set_output_dir(original_dir)
        output_tab.set_filename_template(original_template)

        # 切换到 blb2txt 再切回
        main_window.tool_combo.setCurrentIndex(1)
        main_window.tool_combo.setCurrentIndex(0)

        output_tab_after = main_window._tabs_by_id.get("output")
        assert output_tab_after is not None
        assert output_tab_after.get_output_dir() == original_dir
        assert output_tab_after.get_filename_template() == original_template

    def test_switch_updates_file_list_filter(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """切换工具时 file_list_widget.set_tool 应被调用。"""
        calls: list[ToolType] = []
        original = main_window.file_list_widget.set_tool

        def spy(tool: ToolType) -> None:
            calls.append(tool)
            original(tool)

        monkeypatch.setattr(main_window.file_list_widget, "set_tool", spy)
        main_window.tool_combo.setCurrentIndex(1)
        assert calls[-1] is ToolType.BLB2TXT
        main_window.tool_combo.setCurrentIndex(0)
        assert calls[-1] is ToolType.BALCON

    def test_status_prefix_reflects_current_tool(
        self, main_window: MainWindow
    ) -> None:
        """``_status_prefix`` 在 blb2txt 模式返回 ``"[文本提取] "``。"""
        assert main_window._status_prefix() == ""
        main_window.tool_combo.setCurrentIndex(1)
        assert main_window._status_prefix() == "[文本提取] "

    def test_status_bar_label_reflects_current_tool(
        self, main_window: MainWindow
    ) -> None:
        """状态栏中段标签在 blb2txt 模式显示 blb2txt 路径。"""
        main_window.tool_combo.setCurrentIndex(1)
        text = main_window._balcon_path_label.text()
        assert text.startswith("blb2txt:")
        main_window.tool_combo.setCurrentIndex(0)
        text = main_window._balcon_path_label.text()
        assert text.startswith("balcon:")


# ---------------------------------------------------------------------------
# Task 25：blb2txt 路径自动选用
# ---------------------------------------------------------------------------
class TestBlb2txtPathSelection:
    """``_on_start_blb2txt`` 与 ``_on_preview_blb2txt`` 路径选用逻辑。"""

    def test_pdf_file_uses_main_path(self, main_window: MainWindow) -> None:
        """PDF 文件应使用 blb2txt_path（主版本）。"""
        main_window.tool_combo.setCurrentIndex(1)
        # 添加一个 PDF 文件到列表
        main_window.file_list_widget.add_files(["C:/input/sample.pdf"])

        captured_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            captured_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        assert len(captured_tasks) == 1
        task = captured_tasks[0]
        assert isinstance(task, Blb2txtTask)
        # PDF 文件应使用主版本路径（fake_settings.blb2txt_path）
        assert task._blb2txt_path == main_window._settings.blb2txt_path

    def test_non_pdf_file_uses_lite_path(self, main_window: MainWindow) -> None:
        """非 PDF 文件且 lite_path 非空时使用 blb2txt_lite_path。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window.file_list_widget.add_files(["C:/input/sample.docx"])

        captured_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            captured_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        assert len(captured_tasks) == 1
        task = captured_tasks[0]
        assert isinstance(task, Blb2txtTask)
        # 非 PDF 文件应使用精简版路径
        assert task._blb2txt_path == main_window._settings.blb2txt_lite_path

    def test_lite_path_empty_falls_back_to_main(
        self, main_window: MainWindow
    ) -> None:
        """``blb2txt_lite_path`` 为空时非 PDF 文件回退到主版本。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window._settings.blb2txt_lite_path = ""
        main_window.file_list_widget.add_files(["C:/input/sample.docx"])

        captured_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            captured_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        assert len(captured_tasks) == 1
        task = captured_tasks[0]
        assert task._blb2txt_path == main_window._settings.blb2txt_path


# ---------------------------------------------------------------------------
# Task 25：blb2txt 预览
# ---------------------------------------------------------------------------
class TestBlb2txtPreview:
    """``_on_preview_blb2txt`` 行为。"""

    def test_preview_blb2txt_builds_command(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """blb2txt 模式预览应构建以 blb2txt.exe 开头的命令字符串。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window.file_list_widget.add_files(["C:/input/sample.pdf"])

        captured: dict = {}

        class FakeDialog:
            def __init__(self, command, parent=None):
                captured["command"] = command
                captured["title"] = None

            def setWindowTitle(self, title):
                captured["title"] = title

            def exec(self):
                return 1  # QDialog.Accepted

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window._PreviewDialog", FakeDialog
        )
        main_window._on_preview()
        assert "command" in captured
        # 命令字符串应包含 blb2txt.exe 路径
        assert main_window._settings.blb2txt_path in captured["command"]
        # 应包含 -f 参数（f_files = [sample.pdf]）
        assert "-f" in captured["command"]
        assert "sample.pdf" in captured["command"]

    def test_preview_balcon_uses_balcon_runner(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """balcon 模式预览应使用 balcon 路径。"""
        main_window.file_list_widget.add_files(["C:/input/sample.txt"])

        captured: dict = {}

        class FakeDialog:
            def __init__(self, command, parent=None):
                captured["command"] = command

            def setWindowTitle(self, title):
                pass

            def exec(self):
                return 1

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window._PreviewDialog", FakeDialog
        )
        main_window._on_preview()
        assert "command" in captured
        assert main_window._settings.balcon_path in captured["command"]


# ---------------------------------------------------------------------------
# Task 26：SettingsDialog
# ---------------------------------------------------------------------------
class TestSettingsDialogBlb2txt:
    """``SettingsDialog`` 新增 blb2txt 路径配置行。"""

    def test_dialog_has_blb2txt_path_edit(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """``SettingsDialog`` 应包含 blb2txt_path_edit QLineEdit。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.blb2txt_path_edit, QLineEdit)

    def test_dialog_has_blb2txt_lite_path_edit(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """``SettingsDialog`` 应包含 blb2txt_lite_path_edit QLineEdit。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.blb2txt_lite_path_edit, QLineEdit)

    def test_blb2txt_path_edit_initial_value(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt_path_edit 初始值应为 settings.blb2txt_path。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.blb2txt_path_edit.text() == fake_settings.blb2txt_path

    def test_blb2txt_lite_path_edit_initial_value(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt_lite_path_edit 初始值应为 settings.blb2txt_lite_path。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.blb2txt_lite_path_edit.text() == fake_settings.blb2txt_lite_path

    def test_get_blb2txt_path_returns_stripped(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """``get_blb2txt_path`` 返回去除首尾空白的路径。"""
        dialog = SettingsDialog(fake_settings)
        dialog.blb2txt_path_edit.setText("  C:/path/blb2txt.exe  ")
        assert dialog.get_blb2txt_path() == "C:/path/blb2txt.exe"

    def test_get_blb2txt_lite_path_returns_stripped(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """``get_blb2txt_lite_path`` 返回去除首尾空白的路径。"""
        dialog = SettingsDialog(fake_settings)
        dialog.blb2txt_lite_path_edit.setText("  C:/path/lite/blb2txt.exe  ")
        assert dialog.get_blb2txt_lite_path() == "C:/path/lite/blb2txt.exe"

    def test_dialog_still_has_balcon_path_edit(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """既有 balcon 路径配置行应保持不变。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.path_edit, QLineEdit)
        assert dialog.path_edit.text() == fake_settings.balcon_path

    def test_dialog_still_has_concurrency_spin(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """既有并发数配置应保持不变。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.concurrency_spin, QSpinBox)
        assert dialog.concurrency_spin.value() == fake_settings.max_concurrency


# ---------------------------------------------------------------------------
# Task 26：_on_settings 保存 blb2txt 路径
# ---------------------------------------------------------------------------
class TestOnSettingsSavesBlb2txt:
    """``_on_settings`` 应保存 blb2txt 路径到 settings。"""

    def test_on_settings_saves_blb2txt_paths(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """用户在 SettingsDialog 修改 blb2txt 路径后应写入 AppSettings。"""
        new_blb2txt = "C:/new/blb2txt.exe"
        new_lite = "C:/new/lite/blb2txt.exe"

        class FakeDialog:
            def __init__(self, settings, parent=None):
                pass

            def exec(self):
                return 1  # QDialog.Accepted

            def get_balcon_path(self):
                return main_window._settings.balcon_path

            def get_concurrency(self):
                return main_window._settings.max_concurrency

            def get_process_priority(self):
                return main_window._settings.process_priority

            def get_blb2txt_path(self):
                return new_blb2txt

            def get_blb2txt_lite_path(self):
                return new_lite

            def get_theme(self):
                return main_window._settings.theme

            def get_density(self):
                return main_window._settings.density

            def get_font_scale(self):
                return main_window._settings.font_scale

            def get_disable_animations(self):
                return main_window._settings.disable_animations

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.SettingsDialog", FakeDialog
        )
        # 禁用磁盘保存（避免污染真实 settings.json）
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        # 禁用路径校验触发
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.warning", lambda *a, **k: 0
        )

        main_window._on_settings()
        assert main_window._settings.blb2txt_path == new_blb2txt
        assert main_window._settings.blb2txt_lite_path == new_lite

    def test_on_settings_no_change_keeps_paths(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """用户未修改 blb2txt 路径时 settings 应保持不变。"""
        original_blb2txt = main_window._settings.blb2txt_path
        original_lite = main_window._settings.blb2txt_lite_path

        class FakeDialog:
            def __init__(self, settings, parent=None):
                self._settings = settings

            def exec(self):
                return 1

            def get_balcon_path(self):
                return main_window._settings.balcon_path

            def get_concurrency(self):
                return main_window._settings.max_concurrency

            def get_process_priority(self):
                return main_window._settings.process_priority

            def get_blb2txt_path(self):
                return main_window._settings.blb2txt_path

            def get_blb2txt_lite_path(self):
                return main_window._settings.blb2txt_lite_path

            def get_theme(self):
                return main_window._settings.theme

            def get_density(self):
                return main_window._settings.density

            def get_font_scale(self):
                return main_window._settings.font_scale

            def get_disable_animations(self):
                return main_window._settings.disable_animations

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.SettingsDialog", FakeDialog
        )
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)

        main_window._on_settings()
        assert main_window._settings.blb2txt_path == original_blb2txt
        assert main_window._settings.blb2txt_lite_path == original_lite


# ---------------------------------------------------------------------------
# Task 25：_on_start 分支
# ---------------------------------------------------------------------------
class TestOnStartBranching:
    """``_on_start`` 按当前工具分支创建对应任务类型。"""

    def test_balcon_mode_creates_balcon_tasks(
        self, main_window: MainWindow
    ) -> None:
        """balcon 模式下 _on_start 应创建 BalconTask 列表。"""
        main_window.file_list_widget.add_files(["C:/input/sample.txt"])

        captured_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            captured_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        assert len(captured_tasks) >= 1
        from balcon_batch_tts.core.worker import BalconTask

        for task in captured_tasks:
            assert isinstance(task, BalconTask)

    def test_blb2txt_mode_creates_blb2txt_tasks(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 模式下 _on_start 应创建 Blb2txtTask 列表。"""
        main_window.tool_combo.setCurrentIndex(1)
        main_window.file_list_widget.add_files(["C:/input/sample.pdf"])

        captured_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            captured_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        assert len(captured_tasks) >= 1
        for task in captured_tasks:
            assert isinstance(task, Blb2txtTask)

    def test_no_files_shows_warning(self, main_window: MainWindow, monkeypatch):
        """文件列表为空时 _on_start 应弹警告且不提交任务。"""
        warning_calls: list = []
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.warning",
            lambda *a, **k: warning_calls.append(a) or 0,
        )

        submitted: list = []
        main_window._scheduler.submit = lambda tasks: submitted.extend(tasks)  # type: ignore[assignment]
        main_window._on_start()
        assert len(warning_calls) == 1
        assert len(submitted) == 0


# ---------------------------------------------------------------------------
# Task 25：状态栏工具前缀
# ---------------------------------------------------------------------------
class TestStatusBarToolPrefix:
    """状态栏与工具前缀相关行为。"""

    def test_status_label_has_prefix_in_blb2txt_mode(
        self, main_window: MainWindow
    ) -> None:
        """blb2txt 模式下 _status_label 文本应以 "[文本提取] " 开头。"""
        main_window.tool_combo.setCurrentIndex(1)
        # 触发一次状态更新（_on_tool_changed 已设置）
        assert main_window._status_label.text().startswith("[文本提取] ")

    def test_status_label_no_prefix_in_balcon_mode(
        self, main_window: MainWindow
    ) -> None:
        """balcon 模式下 _status_label 文本不应有前缀。"""
        main_window.tool_combo.setCurrentIndex(0)
        text = main_window._status_label.text()
        assert not text.startswith("[文本提取]")


# ---------------------------------------------------------------------------
# Task 25：blb2txt 路径校验
# ---------------------------------------------------------------------------
class TestBlb2txtPathValidation:
    """``_blb2txt_path_valid`` 与 ``_validate_blb2txt_path`` 行为。"""

    def test_blb2txt_path_valid_returns_true_for_existing_file(
        self, main_window: MainWindow
    ) -> None:
        assert main_window._blb2txt_path_valid() is True

    def test_blb2txt_path_valid_returns_false_for_missing_file(
        self, main_window: MainWindow
    ) -> None:
        main_window._settings.blb2txt_path = "C:/nonexistent/blb2txt.exe"
        assert main_window._blb2txt_path_valid() is False

    def test_blb2txt_path_valid_returns_false_for_empty(
        self, main_window: MainWindow
    ) -> None:
        main_window._settings.blb2txt_path = ""
        assert main_window._blb2txt_path_valid() is False

    def test_start_action_enabled_state_reflects_tool(
        self, main_window: MainWindow
    ) -> None:
        """切换工具后开始按钮启用状态应反映当前工具路径有效性。"""
        # balcon 模式：路径有效，按钮应启用
        main_window.tool_combo.setCurrentIndex(0)
        assert main_window.start_action.isEnabled() is True

        # 切换到 blb2txt：路径有效，按钮应启用
        main_window.tool_combo.setCurrentIndex(1)
        assert main_window.start_action.isEnabled() is True

        # blb2txt 路径无效：按钮应禁用
        main_window._settings.blb2txt_path = "C:/nonexistent/blb2txt.exe"
        main_window.tool_combo.setCurrentIndex(0)
        main_window.tool_combo.setCurrentIndex(1)
        assert main_window.start_action.isEnabled() is False


# ---------------------------------------------------------------------------
# Task 24：closeEvent 在 blb2txt 模式下的行为
# ---------------------------------------------------------------------------
class TestCloseEventToolAware:
    """``closeEvent`` 在不同工具模式下正确保存状态。"""

    def test_close_in_balcon_mode_saves_output_state(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """balcon 模式关闭时 OutputTab 状态应写入 settings。"""
        output_tab = main_window._tabs_by_id.get("output")
        assert output_tab is not None
        output_tab.set_output_dir("C:/close_test")
        output_tab.set_filename_template("{name}_close.wav")

        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        from PySide6.QtGui import QCloseEvent

        event = QCloseEvent()
        main_window.closeEvent(event)
        assert main_window._settings.last_output_dir == "C:/close_test"
        assert main_window._settings.filename_template == "{name}_close.wav"

    def test_close_in_blb2txt_mode_preserves_balcon_state(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """blb2txt 模式关闭时 settings 应保留 balcon 状态（不污染）。"""
        # 先在 balcon 模式设置 OutputTab 状态
        output_tab = main_window._tabs_by_id.get("output")
        assert output_tab is not None
        output_tab.set_output_dir("C:/balcon_state")
        output_tab.set_filename_template("{name}_balcon.wav")

        # 切换到 blb2txt
        main_window.tool_combo.setCurrentIndex(1)

        # 关闭窗口
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        from PySide6.QtGui import QCloseEvent

        event = QCloseEvent()
        main_window.closeEvent(event)
        # settings 应保留 balcon 状态（_balcon_output_dir 已切换时保存）
        assert main_window._settings.last_output_dir == "C:/balcon_state"
        assert main_window._settings.filename_template == "{name}_balcon.wav"


# ---------------------------------------------------------------------------
# 断点续传：启动检测与恢复
# ---------------------------------------------------------------------------
class TestCheckpointDetection:
    """``_check_for_pending_checkpoint`` 启动时检测行为。"""

    def test_no_checkpoint_when_output_dir_empty(
        self, main_window: MainWindow
    ) -> None:
        """last_output_dir 为空时不应检测 checkpoint。"""
        main_window._settings.last_output_dir = ""
        # 不应抛异常
        main_window._check_for_pending_checkpoint()

    def test_no_checkpoint_when_dir_not_exist(
        self, main_window: MainWindow
    ) -> None:
        """last_output_dir 目录不存在时不应检测。"""
        main_window._settings.last_output_dir = "C:/nonexistent_dir_12345"
        main_window._check_for_pending_checkpoint()

    def test_no_checkpoint_when_no_file(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """目录存在但无 checkpoint 文件时不应恢复。"""
        main_window._settings.last_output_dir = str(tmp_path)
        main_window._check_for_pending_checkpoint()
        # 文件列表应为空
        assert main_window.file_list_widget.get_files() == []

    def test_clears_checkpoint_when_no_pending(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """checkpoint 存在但无待处理文件时应清除残留记录。"""
        from balcon_batch_tts.core.checkpoint import (
            CheckpointManager,
            CheckpointState,
        )

        # 创建一个全部已完成的 checkpoint
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            input_files=["a.txt"],
            completed_files=["a.txt"],
        )
        mgr.create(state)
        assert mgr.exists()

        main_window._settings.last_output_dir = str(tmp_path)
        main_window._check_for_pending_checkpoint()

        # 残留 checkpoint 应被清除
        assert not mgr.exists()

    def test_dialog_shown_when_pending_exists(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """有待处理文件时应弹出对话框，用户拒绝则不恢复。"""
        from balcon_batch_tts.core.checkpoint import (
            CheckpointManager,
            CheckpointState,
        )

        # 创建包含待处理文件的 checkpoint
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            input_files=["a.txt", "b.txt"],
            completed_files=["a.txt"],
        )
        mgr.create(state)

        main_window._settings.last_output_dir = str(tmp_path)

        # 模拟用户点击"否"（reject）
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QDialog.exec",
            lambda self: 0,  # QDialog.Rejected
        )

        main_window._check_for_pending_checkpoint()
        # 用户拒绝，文件列表应仍为空
        assert main_window.file_list_widget.get_files() == []

    def test_restores_files_when_accepted(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """用户接受恢复时，待处理文件应添加到文件列表。"""
        from balcon_batch_tts.core.checkpoint import (
            CheckpointManager,
            CheckpointState,
        )

        # 创建两个临时文件（模拟真实输入文件）
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("content a")
        file_b.write_text("content b")

        # 创建 checkpoint（a 已完成，b 待处理）
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            input_files=[str(file_a), str(file_b)],
            completed_files=[str(file_a)],
        )
        mgr.create(state)

        main_window._settings.last_output_dir = str(tmp_path)

        # 模拟用户点击"是"（accept），不恢复参数
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QDialog.exec",
            lambda self: 1,  # QDialog.Accepted
        )
        # QCheckBox.isChecked 返回 False（不恢复参数）
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QCheckBox.isChecked",
            lambda self: False,
        )

        main_window._check_for_pending_checkpoint()

        # b.txt 应在文件列表中，a.txt 不在（已完成）
        files = main_window.file_list_widget.get_files()
        assert str(file_b) in files
        assert str(file_a) not in files


class TestCheckpointConfigSnapshot:
    """``config_snapshot`` 保存与恢复。"""

    def test_balcon_start_saves_config_snapshot(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """balcon 模式开始任务时应在 checkpoint 中保存 config_snapshot。"""
        from balcon_batch_tts.core.checkpoint import CheckpointManager

        # 准备输入文件
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello")
        main_window.file_list_widget.add_files([str(input_file)])

        # 设置输出目录
        output_tab = main_window._tabs_by_id.get("output")
        assert output_tab is not None
        output_tab.set_output_dir(str(tmp_path))

        # 禁用调度器提交（避免真实执行）
        monkeypatch.setattr(
            main_window._scheduler, "submit", lambda tasks: None
        )

        # 执行开始
        main_window._on_start_balcon()

        # 验证 checkpoint 包含 config_snapshot
        mgr = CheckpointManager(str(tmp_path))
        state = mgr.load()
        assert state is not None
        assert state.has_config_snapshot()
        # config_snapshot 应包含 BalconConfig 的字段
        assert isinstance(state.config_snapshot, dict)

    def test_apply_config_snapshot_restores_to_tabs(
        self, main_window: MainWindow
    ) -> None:
        """``_apply_config_snapshot`` 应将配置应用到当前 Tab。"""
        # 构造一个包含 n_voice 的 snapshot
        snapshot = {"n_voice": "Heather"}
        # BalconConfig.from_dict 会用默认值填充缺失字段
        main_window._apply_config_snapshot(snapshot, ToolType.BALCON)

        # 验证 _balcon_config 已更新
        assert main_window._balcon_config.n_voice == "Heather"

    def test_apply_config_snapshot_empty_is_noop(
        self, main_window: MainWindow
    ) -> None:
        """空 snapshot 不应影响配置。"""
        original_voice = main_window._balcon_config.n_voice
        main_window._apply_config_snapshot({}, ToolType.BALCON)
        assert main_window._balcon_config.n_voice == original_voice

    def test_load_checkpoint_state_restores_config(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """``_load_checkpoint_state`` 在 restore_config=True 时恢复参数。"""
        from balcon_batch_tts.core.checkpoint import (
            CheckpointManager,
            CheckpointState,
        )

        # 创建临时输入文件
        file_b = tmp_path / "b.txt"
        file_b.write_text("content")

        # 构造含 config_snapshot 的 checkpoint
        snapshot = main_window._balcon_config.to_dict()
        snapshot["n_voice"] = "TestVoice"
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            tool_type="balcon",
            input_files=[str(file_b)],
            output_dir=str(tmp_path),
            config_snapshot=snapshot,
        )
        mgr.create(state)

        # 执行恢复
        main_window._load_checkpoint_state(state, restore_config=True, mgr=mgr)

        # 验证配置已恢复
        assert main_window._balcon_config.n_voice == "TestVoice"
        # 验证文件已添加
        assert str(file_b) in main_window.file_list_widget.get_files()

    def test_load_checkpoint_state_skips_missing_files(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """``_load_checkpoint_state`` 应跳过已不存在的文件。"""
        from balcon_batch_tts.core.checkpoint import (
            CheckpointManager,
            CheckpointState,
        )

        # 创建一个不存在的文件路径
        missing_file = str(tmp_path / "nonexistent.txt")

        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            tool_type="balcon",
            input_files=[missing_file],
            output_dir=str(tmp_path),
        )
        mgr.create(state)

        main_window._load_checkpoint_state(state, restore_config=False, mgr=mgr)

        # 不存在的文件不应出现在文件列表中
        files = main_window.file_list_widget.get_files()
        assert missing_file not in files
        assert files == []
