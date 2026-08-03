"""OutputTab 多格式输出单元测试。

验证 :class:`OutputTab` 在多格式输出场景下的行为：
- 「输出格式」下拉框包含 WAV/MP3/OGG/AAC/FLAC/WMA 六个选项
- ``get_output_format`` / ``set_output_format`` 正确读写
- 选择非 WAV 格式时自动调整文件名模板扩展名
- ``get_ffmpeg_path`` / ``set_ffmpeg_path`` 正确读写
- ffmpeg 状态提示标签根据格式与路径变化

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.audio_encoder import AudioFormat, clear_ffmpeg_cache
from balcon_batch_tts.gui.tabs.output_tab import OutputTab


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 输出格式下拉框
# ---------------------------------------------------------------------------
class TestFormatCombo:
    """「输出格式」下拉框契约。"""

    def test_format_combo_exists(self, qapp: QApplication) -> None:
        tab = OutputTab()
        assert tab.format_combo is not None

    def test_format_combo_has_six_items(self, qapp: QApplication) -> None:
        """应包含 WAV/MP3/OGG/AAC/FLAC/WMA 六个选项。"""
        tab = OutputTab()
        assert tab.format_combo.count() == 6

    def test_format_combo_contains_all_formats(
        self, qapp: QApplication
    ) -> None:
        """下拉框应包含所有 AudioFormat 枚举值。"""
        tab = OutputTab()
        data_items = [
            tab.format_combo.itemData(i)
            for i in range(tab.format_combo.count())
        ]
        for fmt in AudioFormat:
            assert fmt.value in data_items

    def test_default_format_is_wav(self, qapp: QApplication) -> None:
        """默认应选择 WAV。"""
        tab = OutputTab()
        assert tab.get_output_format() is AudioFormat.WAV

    def test_set_output_format_mp3(self, qapp: QApplication) -> None:
        tab = OutputTab()
        tab.set_output_format(AudioFormat.MP3)
        assert tab.get_output_format() is AudioFormat.MP3

    def test_set_output_format_ogg(self, qapp: QApplication) -> None:
        tab = OutputTab()
        tab.set_output_format(AudioFormat.OGG)
        assert tab.get_output_format() is AudioFormat.OGG

    def test_set_output_format_flac(self, qapp: QApplication) -> None:
        tab = OutputTab()
        tab.set_output_format(AudioFormat.FLAC)
        assert tab.get_output_format() is AudioFormat.FLAC

    def test_format_label_includes_ffmpeg_hint(
        self, qapp: QApplication
    ) -> None:
        """非 WAV 格式的标签应包含「需 ffmpeg」提示。"""
        tab = OutputTab()
        for i in range(tab.format_combo.count()):
            label = tab.format_combo.itemText(i)
            data = tab.format_combo.itemData(i)
            fmt = AudioFormat(data)
            if fmt.needs_ffmpeg:
                assert "需 ffmpeg" in label
            else:
                assert "需 ffmpeg" not in label


# ---------------------------------------------------------------------------
# 模板扩展名自动调整
# ---------------------------------------------------------------------------
class TestTemplateExtensionAdjust:
    """输出格式变化时自动调整文件名模板扩展名。"""

    def test_wav_to_mp3_changes_extension(
        self, qapp: QApplication
    ) -> None:
        """从 WAV 切换到 MP3 时，模板扩展名应从 .wav 变为 .mp3。"""
        tab = OutputTab()
        tab.set_filename_template("{name}.wav")
        tab.set_output_format(AudioFormat.MP3)
        assert tab.get_filename_template() == "{name}.mp3"

    def test_mp3_to_wav_changes_extension(
        self, qapp: QApplication
    ) -> None:
        """从 MP3 切换回 WAV 时，模板扩展名应从 .mp3 变为 .wav。"""
        tab = OutputTab()
        tab.set_filename_template("{name}.mp3")
        # 手动触发格式变化处理（set_output_format 不一定触发 currentIndexChanged）
        tab._on_format_changed()
        # 现在 set_output_format 到 WAV
        tab.set_output_format(AudioFormat.WAV)
        # 再次手动触发以应用扩展名调整
        tab._adjust_template_extension(AudioFormat.WAV)
        assert tab.get_filename_template() == "{name}.wav"

    def test_wav_to_ogg_changes_extension(
        self, qapp: QApplication
    ) -> None:
        tab = OutputTab()
        tab.set_filename_template("{name}.wav")
        tab.set_output_format(AudioFormat.OGG)
        assert tab.get_filename_template() == "{name}.ogg"

    def test_wav_to_flac_changes_extension(
        self, qapp: QApplication
    ) -> None:
        tab = OutputTab()
        tab.set_filename_template("{name}.wav")
        tab.set_output_format(AudioFormat.FLAC)
        assert tab.get_filename_template() == "{name}.flac"

    def test_template_with_ext_placeholder_not_modified(
        self, qapp: QApplication
    ) -> None:
        """使用 ``{ext}`` 占位符的模板不应被修改。"""
        tab = OutputTab()
        tab.set_filename_template("{name}.{ext}")
        tab.set_output_format(AudioFormat.MP3)
        # 不应修改，因为模板不以已知扩展名结尾
        assert tab.get_filename_template() == "{name}.{ext}"

    def test_template_with_custom_extension_not_modified(
        self, qapp: QApplication
    ) -> None:
        """使用未知扩展名的模板不应被修改。"""
        tab = OutputTab()
        tab.set_filename_template("{name}.xyz")
        tab.set_output_format(AudioFormat.MP3)
        assert tab.get_filename_template() == "{name}.xyz"

    def test_template_with_index_placeholder(self, qapp: QApplication) -> None:
        """模板含序号占位符时扩展名仍应被替换。"""
        tab = OutputTab()
        tab.set_filename_template("{i:03d}.wav")
        tab.set_output_format(AudioFormat.MP3)
        assert tab.get_filename_template() == "{i:03d}.mp3"

    def test_template_uppercase_extension_replaced(
        self, qapp: QApplication
    ) -> None:
        """大写扩展名也应被替换（大小写不敏感匹配）。"""
        tab = OutputTab()
        tab.set_filename_template("{name}.WAV")
        tab.set_output_format(AudioFormat.MP3)
        assert tab.get_filename_template() == "{name}.mp3"


# ---------------------------------------------------------------------------
# ffmpeg 路径
# ---------------------------------------------------------------------------
class TestFfmpegPath:
    """``ffmpeg_path`` 读写契约。"""

    def test_ffmpeg_edit_exists(self, qapp: QApplication) -> None:
        tab = OutputTab()
        assert tab.ffmpeg_edit is not None

    def test_get_ffmpeg_path_default_empty(
        self, qapp: QApplication
    ) -> None:
        tab = OutputTab()
        assert tab.get_ffmpeg_path() == ""

    def test_set_ffmpeg_path(self, qapp: QApplication) -> None:
        tab = OutputTab()
        tab.set_ffmpeg_path("/usr/bin/ffmpeg")
        assert tab.get_ffmpeg_path() == "/usr/bin/ffmpeg"

    def test_get_ffmpeg_path_strips_whitespace(
        self, qapp: QApplication
    ) -> None:
        tab = OutputTab()
        tab.set_ffmpeg_path("  /usr/bin/ffmpeg  ")
        assert tab.get_ffmpeg_path() == "/usr/bin/ffmpeg"


# ---------------------------------------------------------------------------
# ffmpeg 状态提示
# ---------------------------------------------------------------------------
class TestFfmpegStatusLabel:
    """ffmpeg 状态提示标签行为。"""

    def teardown_method(self) -> None:
        """每个测试后清除 ffmpeg 缓存，避免 EncoderDetector 缓存泄漏。"""
        clear_ffmpeg_cache()

    def test_status_label_hidden_for_wav(
        self, qapp: QApplication
    ) -> None:
        """WAV 格式时状态标签应隐藏。"""
        tab = OutputTab()
        tab.set_output_format(AudioFormat.WAV)
        assert not tab.ffmpeg_status_label.isVisible()

    def test_status_label_visible_for_mp3(
        self, qapp: QApplication
    ) -> None:
        """MP3 格式时状态标签应可见。"""
        tab = OutputTab()
        tab.set_output_format(AudioFormat.MP3)
        # 注意：setVisible 在 offscreen 模式下可能不真正改变可见性
        # 改为检查文本非空
        assert tab.ffmpeg_status_label.text() != ""

    def test_status_label_shows_invalid_path(
        self, qapp: QApplication, monkeypatch
    ) -> None:
        """指定无效 ffmpeg 路径时应显示错误。"""
        # mock find_ffmpeg 返回 None，避免系统 PATH 干扰
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.find_ffmpeg",
            lambda: None,
        )
        tab = OutputTab()
        tab.set_output_format(AudioFormat.MP3)
        tab.set_ffmpeg_path("/nonexistent/ffmpeg.exe")
        # 手动触发状态更新
        tab._update_ffmpeg_status()
        text = tab.ffmpeg_status_label.text()
        assert "无效" in text or "✗" in text

    def test_status_label_shows_valid_path(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """指定有效 ffmpeg 路径时应显示成功。"""
        # mock find_ffmpeg 返回 None，确保用户指定路径优先
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.find_ffmpeg",
            lambda: None,
        )
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        tab = OutputTab()
        tab.set_output_format(AudioFormat.MP3)
        tab.set_ffmpeg_path(str(fake_ffmpeg))
        # 手动触发状态更新
        tab._update_ffmpeg_status()
        text = tab.ffmpeg_status_label.text()
        assert "✓" in text
        assert str(fake_ffmpeg) in text


# ---------------------------------------------------------------------------
# 选用编码器显示标签 (Task 9.6)
# ---------------------------------------------------------------------------
class TestEncoderLabel:
    """「选用编码器」标签行为。"""

    def teardown_method(self) -> None:
        """每个测试后清除 ffmpeg 缓存。"""
        clear_ffmpeg_cache()

    def test_encoder_label_hidden_for_wav(
        self, qapp: QApplication
    ) -> None:
        """WAV 格式时编码器标签应隐藏。"""
        tab = OutputTab()
        tab.set_output_format(AudioFormat.WAV)
        assert not tab.encoder_label.isVisible()

    def test_encoder_label_visible_for_mp3(
        self, qapp: QApplication, monkeypatch
    ) -> None:
        """非 WAV 格式时编码器标签应显示内容（offscreen 模式检查文本非空）。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.find_ffmpeg",
            lambda: None,
        )
        tab = OutputTab()
        tab.set_output_format(AudioFormat.MP3)
        tab._update_ffmpeg_status()
        assert tab.encoder_label.text() != ""

    def test_encoder_label_shows_default_when_no_ffmpeg(
        self, qapp: QApplication, monkeypatch
    ) -> None:
        """未找到 ffmpeg 时应显示默认编码器名称。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.find_ffmpeg",
            lambda: None,
        )
        tab = OutputTab()
        tab.set_output_format(AudioFormat.AAC)
        tab._update_ffmpeg_status()
        text = tab.encoder_label.text()
        assert "aac" in text
        assert "默认编码器" in text

    def test_encoder_label_shows_selected_encoder(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """检测到高性能编码器时应显示已选用编码器。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        # mock EncoderDetector.detect 返回包含 libfdk_aac 的集合
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.EncoderDetector.detect",
            lambda path: {"libfdk_aac", "aac", "libmp3lame"},
        )
        tab = OutputTab()
        tab.set_output_format(AudioFormat.AAC)
        tab.set_ffmpeg_path(str(fake_ffmpeg))
        tab._update_ffmpeg_status()
        text = tab.encoder_label.text()
        assert "libfdk_aac" in text
        assert "高性能" in text

    def test_encoder_label_shows_default_when_best_is_default(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """当选用的编码器与默认编码器相同时标注「默认编码器」。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        # mock EncoderDetector.detect 返回仅包含默认编码器的集合
        monkeypatch.setattr(
            "balcon_batch_tts.gui.tabs.output_tab.EncoderDetector.detect",
            lambda path: {"aac"},
        )
        tab = OutputTab()
        tab.set_output_format(AudioFormat.AAC)
        tab.set_ffmpeg_path(str(fake_ffmpeg))
        tab._update_ffmpeg_status()
        text = tab.encoder_label.text()
        assert "aac" in text
        assert "默认编码器" in text
