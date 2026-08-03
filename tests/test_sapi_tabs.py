"""SAPI5 GUI 选项卡单元测试。

验证 :class:`SapiVoiceTab` 与 :class:`SapiOutputTab` 的元信息（tab_id /
tab_tool）、``collect_config`` / ``apply_config`` 往返一致性、
``refresh_voices`` 语音列表刷新，以及输出设置属性。

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.audio_encoder import AudioFormat
from balcon_batch_tts.core.sapi_config import SapiConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.sapi_output_tab import SapiOutputTab
from balcon_batch_tts.gui.tabs.sapi_voice_tab import SapiVoiceTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# SapiVoiceTab
# ---------------------------------------------------------------------------
class TestSapiVoiceTabMetadata:
    """``SapiVoiceTab`` 元信息方法。"""

    def test_sapi_voice_tab_tab_id(self) -> None:
        assert SapiVoiceTab.tab_id() == "sapi_voice"

    def test_sapi_voice_tab_tab_tool(self) -> None:
        assert SapiVoiceTab.tab_tool() is ToolType.SAPI

    def test_sapi_voice_tab_tab_title(self) -> None:
        assert SapiVoiceTab.tab_title() == "语音与参数"

    def test_sapi_voice_tab_tab_group(self) -> None:
        assert SapiVoiceTab.tab_group() == "语音音频"


class TestSapiVoiceTabCollectApply:
    """``SapiVoiceTab.collect_config`` / ``apply_config`` 往返一致性。"""

    def test_sapi_voice_tab_collect_config(
        self, qapp: QApplication
    ) -> None:
        """``collect_config`` 正确写入 SapiConfig。"""
        tab = SapiVoiceTab()
        tab.rate_widget.setValue(5)
        tab.volume_widget.setValue(80)
        tab.pitch_widget.setValue(-3)
        # voice_name 保持默认（空字符串 = 系统默认）

        cfg = SapiConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.voice_name == ""
        assert cfg.rate == 5
        assert cfg.volume == 80
        assert cfg.pitch == -3

    def test_sapi_voice_tab_apply_config(
        self, qapp: QApplication
    ) -> None:
        """``apply_config`` 正确还原控件。"""
        tab = SapiVoiceTab()
        # 先添加语音，再 apply 一个存在的语音名
        tab.refresh_voices(["Voice A", "Voice B"])

        cfg = SapiConfig(voice_name="Voice B", rate=3, volume=75, pitch=-2)
        tab.apply_config(cfg)

        assert tab.voice_combo.currentData() == "Voice B"
        assert tab.rate_widget.value() == 3
        assert tab.volume_widget.value() == 75
        assert tab.pitch_widget.value() == -2

    def test_sapi_voice_tab_apply_default_voice(
        self, qapp: QApplication
    ) -> None:
        """voice_name 为空时 apply_config 应还原到「系统默认」项。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Voice A"])
        # 先选中 Voice A
        tab.voice_combo.setCurrentIndex(1)

        cfg = SapiConfig(voice_name="", rate=0, volume=100, pitch=0)
        tab.apply_config(cfg)

        assert tab.voice_combo.currentIndex() == 0
        assert tab.voice_combo.currentData() == ""

    def test_sapi_voice_tab_apply_unknown_voice(
        self, qapp: QApplication
    ) -> None:
        """voice_name 不在列表中时应回退到默认项。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Voice A", "Voice B"])

        cfg = SapiConfig(voice_name="Missing Voice", rate=0, volume=100, pitch=0)
        tab.apply_config(cfg)

        assert tab.voice_combo.currentIndex() == 0

    def test_sapi_voice_tab_roundtrip(
        self, qapp: QApplication
    ) -> None:
        """collect → apply → collect 往返应保持一致。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Voice A", "Voice B", "Voice C"])

        original = SapiConfig(voice_name="Voice C", rate=-5, volume=50, pitch=7)
        tab.apply_config(original)
        restored = SapiConfig.create_default()
        tab.collect_config(restored)

        assert restored.voice_name == "Voice C"
        assert restored.rate == -5
        assert restored.volume == 50
        assert restored.pitch == 7

    def test_sapi_voice_tab_collect_audio_format(
        self, qapp: QApplication
    ) -> None:
        """``collect_config`` 应将 combo 的 currentData 写入 ``cfg.audio_format``。"""
        tab = SapiVoiceTab()
        # 切到第 3 项（44.1kHz/16bit/Stereo = 31）
        tab.audio_format_combo.setCurrentIndex(2)

        cfg = SapiConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.audio_format == tab.audio_format_combo.currentData()
        assert cfg.audio_format == 31

    def test_sapi_voice_tab_apply_audio_format(
        self, qapp: QApplication
    ) -> None:
        """``apply_config`` 应将 ``cfg.audio_format`` 还原到 combo。"""
        tab = SapiVoiceTab()
        cfg = SapiConfig(audio_format=31)
        tab.apply_config(cfg)

        assert tab.audio_format_combo.currentData() == 31


class TestSapiVoiceTabRefreshVoices:
    """``SapiVoiceTab.refresh_voices`` 应更新下拉框。"""

    def test_sapi_voice_tab_refresh_voices(
        self, qapp: QApplication
    ) -> None:
        """``refresh_voices`` 应在保留「系统默认」项的基础上追加语音。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Voice A", "Voice B"])

        # 第一项为「系统默认」（data=""），后两项为 Voice A / Voice B
        assert tab.voice_combo.count() == 3
        assert tab.voice_combo.itemData(0) == ""
        assert tab.voice_combo.itemText(1) == "Voice A"
        assert tab.voice_combo.itemData(1) == "Voice A"
        assert tab.voice_combo.itemText(2) == "Voice B"
        assert tab.voice_combo.itemData(2) == "Voice B"

    def test_refresh_voices_empty_list(
        self, qapp: QApplication
    ) -> None:
        """空语音列表应仅保留「系统默认」项。"""
        tab = SapiVoiceTab()
        tab.refresh_voices([])
        assert tab.voice_combo.count() == 1
        assert tab.voice_combo.itemData(0) == ""

    def test_refresh_voices_preserves_selection(
        self, qapp: QApplication
    ) -> None:
        """刷新后应尝试还原之前选择的语音。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Voice A", "Voice B"])
        # 选中 Voice B
        tab.voice_combo.setCurrentIndex(2)
        assert tab.voice_combo.currentData() == "Voice B"

        # 再次刷新（包含 Voice B），应还原选择
        tab.refresh_voices(["Voice A", "Voice B", "Voice C"])
        assert tab.voice_combo.currentData() == "Voice B"

    def test_refresh_voices_replaces_old_list(
        self, qapp: QApplication
    ) -> None:
        """刷新应替换旧的语音列表。"""
        tab = SapiVoiceTab()
        tab.refresh_voices(["Old Voice"])
        assert tab.voice_combo.count() == 2

        tab.refresh_voices(["New Voice 1", "New Voice 2"])
        assert tab.voice_combo.count() == 3
        assert tab.voice_combo.itemText(1) == "New Voice 1"
        assert tab.voice_combo.itemText(2) == "New Voice 2"
        # Old Voice 不应再存在
        assert tab.voice_combo.findText("Old Voice") == -1


# ---------------------------------------------------------------------------
# SapiOutputTab
# ---------------------------------------------------------------------------
class TestSapiOutputTabMetadata:
    """``SapiOutputTab`` 元信息方法。"""

    def test_sapi_output_tab_tab_id(self) -> None:
        assert SapiOutputTab.tab_id() == "sapi_output"

    def test_sapi_output_tab_tab_tool(self) -> None:
        assert SapiOutputTab.tab_tool() is ToolType.SAPI

    def test_sapi_output_tab_tab_title(self) -> None:
        assert SapiOutputTab.tab_title() == "输出设置"

    def test_sapi_output_tab_tab_group(self) -> None:
        assert SapiOutputTab.tab_group() == "输入输出"


class TestSapiOutputTabProperties:
    """``SapiOutputTab`` 属性应正确读取控件值。"""

    def test_sapi_output_tab_properties(
        self, qapp: QApplication
    ) -> None:
        """output_dir / filename_template / output_format / ffmpeg_path 属性。"""
        tab = SapiOutputTab()
        tab.output_dir_edit.setText("/tmp/output")
        tab.template_edit.setText("{name}.mp3")
        tab.format_combo.setCurrentIndex(1)  # MP3
        tab.ffmpeg_edit.setText("/usr/bin/ffmpeg")

        assert tab.output_dir == "/tmp/output"
        assert tab.filename_template == "{name}.mp3"
        assert tab.output_format == AudioFormat.MP3
        assert tab.ffmpeg_path == "/usr/bin/ffmpeg"

    def test_output_format_wav_default(
        self, qapp: QApplication
    ) -> None:
        """默认输出格式应为 WAV。"""
        tab = SapiOutputTab()
        assert tab.output_format == AudioFormat.WAV

    def test_output_format_ogg(
        self, qapp: QApplication
    ) -> None:
        """切换到 OGG 格式。"""
        tab = SapiOutputTab()
        tab.format_combo.setCurrentIndex(2)  # OGG
        assert tab.output_format == AudioFormat.OGG

    def test_output_format_flac(
        self, qapp: QApplication
    ) -> None:
        """切换到 FLAC 格式。"""
        tab = SapiOutputTab()
        tab.format_combo.setCurrentIndex(3)  # FLAC
        assert tab.output_format == AudioFormat.FLAC

    def test_output_dir_default_empty(
        self, qapp: QApplication
    ) -> None:
        """默认输出目录应为空字符串。"""
        tab = SapiOutputTab()
        assert tab.output_dir == ""

    def test_ffmpeg_path_default_empty(
        self, qapp: QApplication
    ) -> None:
        """默认 ffmpeg 路径应为空字符串。"""
        tab = SapiOutputTab()
        assert tab.ffmpeg_path == ""


class TestSapiOutputTabCollectApply:
    """``SapiOutputTab.collect_config`` / ``apply_config`` 往返。"""

    def test_sapi_output_tab_collect_config(
        self, qapp: QApplication
    ) -> None:
        """``collect_config`` 应写入 ``input_encoding``。"""
        tab = SapiOutputTab()
        tab.encoding_edit.setText("gbk")

        cfg = SapiConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.input_encoding == "gbk"

    def test_sapi_output_tab_apply_config(
        self, qapp: QApplication
    ) -> None:
        """``apply_config`` 应还原 ``input_encoding``。"""
        tab = SapiOutputTab()
        cfg = SapiConfig(input_encoding="big5")
        tab.apply_config(cfg)

        assert tab.encoding_edit.text() == "big5"

    def test_sapi_output_tab_collect_empty_falls_back_to_utf8(
        self, qapp: QApplication
    ) -> None:
        """编码为空时 ``collect_config`` 应回退到 utf-8。"""
        tab = SapiOutputTab()
        tab.encoding_edit.setText("")

        cfg = SapiConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.input_encoding == "utf-8"

    def test_sapi_output_tab_collect_whitespace_falls_back_to_utf8(
        self, qapp: QApplication
    ) -> None:
        """编码仅含空白时 ``collect_config`` 应回退到 utf-8。"""
        tab = SapiOutputTab()
        tab.encoding_edit.setText("   ")

        cfg = SapiConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.input_encoding == "utf-8"

    def test_sapi_output_tab_roundtrip(
        self, qapp: QApplication
    ) -> None:
        """collect → apply → collect 往返应保持一致。"""
        tab = SapiOutputTab()

        original = SapiConfig(input_encoding="latin-1")
        tab.apply_config(original)
        restored = SapiConfig.create_default()
        tab.collect_config(restored)

        assert restored.input_encoding == "latin-1"
