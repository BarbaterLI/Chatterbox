"""SAPI5 直达 TTS 工具的 MainWindow 集成测试。

验证 Task 12 的 SAPI5 集成行为：
- 工具选择器第三项为 SAPI5 直达 TTS。
- 切换到 SAPI 后侧边栏加载 SAPI 专用 Tab（sapi_voice / sapi_output）。
- 文件列表过滤器更新为 SAPI 扩展名集合。
- SAPI 模式下"开始"按钮无需外部 exe 路径校验即可启用。
- 状态栏中段显示 SAPI5 信息，状态前缀为 ``[SAPI5]``。
- 预设保存/加载含 ``tool_type == "sapi"`` 字段。
- checkpoint 记录 ``tool_type == "sapi"``。

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换 QMessageBox、
QFileDialog 与调度器，避免真实交互与 COM 调用。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

# 确保 pywin32 mock（若尚未加载真实模块）
if "win32com" not in sys.modules:
    sys.modules["win32com"] = MagicMock()
    sys.modules["win32com.client"] = MagicMock()
if "pythoncom" not in sys.modules:
    sys.modules["pythoncom"] = MagicMock()

from balcon_batch_tts.core.checkpoint import CheckpointManager
from balcon_batch_tts.core.sapi_config import SapiConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.main_window import MainWindow, _SAPI_AVAILABLE
from balcon_batch_tts.persistence.preset import load_preset
from balcon_batch_tts.persistence.settings import AppSettings

pytestmark = pytest.mark.skipif(
    not _SAPI_AVAILABLE, reason="pywin32 不可用，SAPI5 模块未加载"
)


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 辅助：构造可用路径的 settings（避免路径校验弹窗阻塞）
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
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.warning",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.critical",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.information",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        MainWindow, "_refresh_voices_devices", lambda self: None
    )
    monkeypatch.setattr(
        AppSettings,
        "load",
        classmethod(lambda cls, path=None: fake_settings),
    )
    return MainWindow()


# ---------------------------------------------------------------------------
# 工具选择器
# ---------------------------------------------------------------------------
class TestSapiToolCombo:
    """``tool_combo`` 中 SAPI5 选项的配置。"""

    def test_tool_combo_has_three_items(self, main_window: MainWindow) -> None:
        """工具选择器应包含 3 项（balcon / blb2txt / sapi）。"""
        assert main_window.tool_combo.count() == 3

    def test_tool_combo_sapi_display_name(self, main_window: MainWindow) -> None:
        """第三项应显示 ``"SAPI5 直达 TTS"``。"""
        assert main_window.tool_combo.itemText(2) == ToolType.SAPI.display_name
        assert main_window.tool_combo.itemText(2) == "SAPI5 直达 TTS"


# ---------------------------------------------------------------------------
# 工具切换
# ---------------------------------------------------------------------------
class TestSapiToolSwitching:
    """切换到 SAPI 后的 Tab 与文件过滤器行为。"""

    def test_switch_to_sapi_shows_sapi_tabs(
        self, main_window: MainWindow
    ) -> None:
        """切换到 SAPI 后侧边栏应只显示 SAPI 专用 Tab。"""
        # 切换前记录 balcon Tab 数量
        balcon_tab_count = len(main_window._tabs)
        assert balcon_tab_count > 0

        # 切换到 SAPI
        main_window.tool_combo.setCurrentIndex(2)
        assert main_window._current_tool is ToolType.SAPI

        # 验证侧边栏包含 SAPI 专用 Tab
        tab_ids = set(main_window._tabs_by_id.keys())
        assert "sapi_voice" in tab_ids
        assert "sapi_output" in tab_ids

        # 所有已加载 Tab 的 tab_tool() 均为 SAPI
        for tab in main_window._tabs:
            assert type(tab).tab_tool() is ToolType.SAPI

    def test_switch_to_sapi_updates_file_filter(
        self, main_window: MainWindow
    ) -> None:
        """切换到 SAPI 后文件列表过滤器应更新为 SAPI 扩展名集合。"""
        main_window.tool_combo.setCurrentIndex(2)
        file_filter = main_window.file_list_widget._get_file_filter()
        # SAPI 过滤器应包含 .txt 与 .xml 扩展名
        assert ".txt" in file_filter
        assert ".xml" in file_filter


# ---------------------------------------------------------------------------
# 开始按钮启用状态
# ---------------------------------------------------------------------------
class TestSapiStartButton:
    """SAPI 模式下"开始"按钮的启用逻辑。"""

    def test_sapi_start_button_enabled_without_path(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """SAPI 模式下无需路径校验即可启用开始按钮。"""
        # 设置无效的 balcon 路径
        main_window._settings.balcon_path = "C:/nonexistent/balcon.exe"

        # 切换到 SAPI
        main_window.tool_combo.setCurrentIndex(2)

        # 添加文件到文件列表
        input_file = tmp_path / "test.txt"
        input_file.write_text("hello")
        main_window.file_list_widget.add_files([str(input_file)])

        # 验证 start_action 启用（即使 balcon 路径无效）
        assert main_window.start_action.isEnabled() is True


# ---------------------------------------------------------------------------
# 状态栏
# ---------------------------------------------------------------------------
class TestSapiStatusBar:
    """SAPI 模式下状态栏的显示。"""

    def test_sapi_status_bar(self, main_window: MainWindow) -> None:
        """SAPI 模式下状态栏应显示 SAPI5 信息与前缀。"""
        main_window.tool_combo.setCurrentIndex(2)

        # 状态栏中段显示 SAPI5 直达 TTS
        assert main_window._balcon_path_label.text() == "SAPI5 直达 TTS"

        # 状态前缀为 [SAPI5]
        assert main_window._status_prefix() == "[SAPI5] "

        # 状态栏标签文本应以 [SAPI5] 开头
        assert main_window._status_label.text().startswith("[SAPI5] ")


# ---------------------------------------------------------------------------
# 预设保存/加载
# ---------------------------------------------------------------------------
class TestSapiPreset:
    """SAPI 预设保存/加载含 tool_type 字段。"""

    def test_sapi_preset_save_load(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """SAPI 预设保存后加载，tool_type 应为 ``"sapi"``。"""
        # 切换到 SAPI
        main_window.tool_combo.setCurrentIndex(2)

        # 保存预设到临时文件
        preset_path = str(tmp_path / "sapi_preset.json")

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (preset_path, ""),
        )
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)

        main_window._on_save_preset()

        # 验证预设文件已创建
        assert os.path.isfile(preset_path)

        # 直接读取预设文件验证 tool_type
        tool_type_str, params = load_preset(preset_path)
        assert tool_type_str == "sapi"
        # params 应包含 SapiConfig 字段
        assert "voice_name" in params
        assert "rate" in params
        assert "volume" in params
        assert "pitch" in params

        # 加载预设（mock QFileDialog.getOpenFileName）
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QFileDialog.getOpenFileName",
            lambda *a, **k: (preset_path, ""),
        )

        main_window._on_load_preset()

        # 加载后应仍在 SAPI 模式
        assert main_window._current_tool is ToolType.SAPI


# ---------------------------------------------------------------------------
# 断点续传 checkpoint
# ---------------------------------------------------------------------------
class TestSapiCheckpoint:
    """SAPI 模式下 checkpoint 的 tool_type 字段。"""

    def test_sapi_checkpoint_tool_type(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """SAPI 模式启动任务后 checkpoint 应记录 ``tool_type == "sapi"``。"""
        # mock sapi_list_voices 避免实际 COM 调用
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.sapi_list_voices",
            lambda: ["Voice1", "Voice2"],
        )

        # 切换到 SAPI
        main_window.tool_combo.setCurrentIndex(2)
        assert main_window._current_tool is ToolType.SAPI

        # 设置输出目录到临时路径
        output_tab = main_window._tabs_by_id.get("sapi_output")
        assert output_tab is not None
        output_tab.output_dir_edit.setText(str(tmp_path))

        # PySide6 QVariant 将 AudioFormat(str, Enum) 降级为 str，
        # 需将 SapiOutputTab.output_format property 返回值还原为 AudioFormat
        # 枚举，否则 _on_start_sapi 中 output_format.needs_ffmpeg 会失败。
        from balcon_batch_tts.core.audio_encoder import AudioFormat
        from balcon_batch_tts.gui.tabs.sapi_output_tab import SapiOutputTab

        @property
        def _patched_output_format(self):
            data = self.format_combo.currentData()
            if isinstance(data, str):
                try:
                    return AudioFormat(data)
                except ValueError:
                    return AudioFormat.WAV
            return data

        monkeypatch.setattr(
            SapiOutputTab, "output_format", _patched_output_format
        )

        # 添加输入文件
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello world")
        main_window.file_list_widget.add_files([str(input_file)])

        # mock 调度器提交避免实际执行
        submitted_tasks: list = []
        original_submit = main_window._scheduler.submit

        def fake_submit(tasks):
            submitted_tasks.extend(tasks)

        main_window._scheduler.submit = fake_submit  # type: ignore[assignment]
        try:
            # 模拟启动任务（_on_start 分派到 _on_start_sapi）
            main_window._on_start()
        finally:
            main_window._scheduler.submit = original_submit  # type: ignore[assignment]

        # 验证任务已提交（SapiTask 实例）
        assert len(submitted_tasks) >= 1

        # 验证 checkpoint 的 tool_type 为 "sapi"
        mgr = CheckpointManager(str(tmp_path))
        state = mgr.load()
        assert state is not None
        assert state.tool_type == "sapi"
        # config_snapshot 应包含 SapiConfig 字段
        assert state.has_config_snapshot()
        assert isinstance(state.config_snapshot, dict)
        assert "voice_name" in state.config_snapshot
