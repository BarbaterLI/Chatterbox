"""VoiceTab 单元测试。

验证 :class:`VoiceTab` 的元信息、SliderSpinDial 控件使用、QDial 旋钮、
QGroupBox 静音设置子组，以及 ``collect_config`` / ``apply_config`` 往返一致性。

Task 4b 新增覆盖：
- 7 个数值参数使用 SliderSpinDial（QSlider + QSpinBox 联动）
- 音量参数包含 QDial 旋钮（三向联动）
- 静音参数被 QGroupBox「静音设置」包裹
- 吸收原 SilenceTab 的 silence_begin / silence_end 字段
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QLineEdit,
)

from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.voice_tab import VoiceTab
from balcon_batch_tts.gui.widgets.slider_spin_dial import SliderSpinDial


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 元信息测试
# ---------------------------------------------------------------------------
class TestTabMetadata:
    """VoiceTab 元信息方法返回值。"""

    def test_tab_id(self) -> None:
        assert VoiceTab.tab_id() == "voice"

    def test_tab_title(self) -> None:
        """Task 4b：tab_title 改为「语音与静音」（吸收 SilenceTab）。"""
        assert VoiceTab.tab_title() == "语音与静音"

    def test_tab_group(self) -> None:
        assert VoiceTab.tab_group() == "语音音频"

    def test_tab_tool(self) -> None:
        assert VoiceTab.tab_tool() is ToolType.BALCON


# ---------------------------------------------------------------------------
# 控件存在性测试：7 个 SliderSpinDial + QDial
# ---------------------------------------------------------------------------
class TestSliderSpinDialWidgets:
    """验证 7 个数值参数使用 SliderSpinDial 复合控件。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> VoiceTab:
        return VoiceTab()

    def test_rate_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """语速 (-s) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.rate_widget, SliderSpinDial)

    def test_pitch_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """音调 (-p) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.pitch_widget, SliderSpinDial)

    def test_volume_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """音量 (-v) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.volume_widget, SliderSpinDial)

    def test_sentence_pause_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """句间停顿 (-e) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.sentence_pause_widget, SliderSpinDial)

    def test_paragraph_pause_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """段间停顿 (-a) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.paragraph_pause_widget, SliderSpinDial)

    def test_silence_begin_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """起始静音 (--silence-begin) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.silence_begin_widget, SliderSpinDial)

    def test_silence_end_widget_is_slider_spin_dial(
        self, tab: VoiceTab
    ) -> None:
        """结尾静音 (--silence-end) SHALL 使用 SliderSpinDial。"""
        assert isinstance(tab.silence_end_widget, SliderSpinDial)


# ---------------------------------------------------------------------------
# QDial 旋钮测试
# ---------------------------------------------------------------------------
class TestVolumeDial:
    """验证音量参数包含 QDial 旋钮（三向联动）。"""

    def test_volume_widget_has_dial(self, qapp: QApplication) -> None:
        """音量 SliderSpinDial SHALL 包含 QDial 旋钮。"""
        tab = VoiceTab()
        assert tab.volume_widget.dial is not None, (
            "音量参数 SHALL 包含 QDial 旋钮（with_dial=True）"
        )

    def test_other_widgets_no_dial(self, qapp: QApplication) -> None:
        """非音量参数 SHALL NOT 包含 QDial 旋钮。"""
        tab = VoiceTab()
        assert tab.rate_widget.dial is None
        assert tab.pitch_widget.dial is None
        assert tab.sentence_pause_widget.dial is None
        assert tab.paragraph_pause_widget.dial is None
        assert tab.silence_begin_widget.dial is None
        assert tab.silence_end_widget.dial is None

    def test_volume_dial_notches_visible(
        self, qapp: QApplication
    ) -> None:
        """音量 QDial 旋钮 SHALL 显示刻度（setNotchesVisible=True）。"""
        tab = VoiceTab()
        assert tab.volume_widget.dial is not None
        assert tab.volume_widget.dial.notchesVisible() is True


# ---------------------------------------------------------------------------
# 静音设置 QGroupBox 测试
# ---------------------------------------------------------------------------
class TestSilenceGroupBox:
    """验证静音参数被 QGroupBox「静音设置」包裹。"""

    def test_has_silence_groupbox(self, qapp: QApplication) -> None:
        """VoiceTab SHALL 包含标题为「静音设置」的 QGroupBox。"""
        tab = VoiceTab()
        groups = tab.findChildren(QGroupBox)
        silence_groups = [g for g in groups if g.title() == "静音设置"]
        assert len(silence_groups) == 1, (
            f"应有 1 个标题为 '静音设置' 的 QGroupBox，"
            f"实际 {len(silence_groups)}"
        )

    def test_silence_groupbox_contains_two_widgets(
        self, qapp: QApplication
    ) -> None:
        """静音设置 QGroupBox SHALL 包含 2 个 SliderSpinDial。"""
        tab = VoiceTab()
        groups = tab.findChildren(QGroupBox)
        silence_group = next(g for g in groups if g.title() == "静音设置")
        sliders = silence_group.findChildren(SliderSpinDial)
        assert len(sliders) == 2, (
            f"静音设置组应有 2 个 SliderSpinDial，实际 {len(sliders)}"
        )


# ---------------------------------------------------------------------------
# voice_combo / langid_edit 控件存在性
# ---------------------------------------------------------------------------
class TestBasicWidgets:
    """验证 voice_combo 与 langid_edit 控件类型保持兼容。"""

    def test_voice_combo_is_combobox(self, qapp: QApplication) -> None:
        tab = VoiceTab()
        assert isinstance(tab.voice_combo, QComboBox)

    def test_langid_edit_is_lineedit(self, qapp: QApplication) -> None:
        tab = VoiceTab()
        assert isinstance(tab.langid_edit, QLineEdit)


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致性
# ---------------------------------------------------------------------------
class TestCollectApplyRoundTrip:
    """``collect_config`` 与 ``apply_config`` 的往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> VoiceTab:
        return VoiceTab()

    def test_default_round_trip(self, tab: VoiceTab) -> None:
        """默认值往返：apply 默认 cfg 后 collect 应得到全 None/默认字段。"""
        cfg = BalconConfig.create_default()
        tab.apply_config(cfg)
        out = BalconConfig.create_default()
        tab.collect_config(out)
        assert out.n_voice is None
        assert out.id_langid is None
        assert out.s_rate is None
        assert out.p_pitch is None
        assert out.v_volume == 100  # volume default
        assert out.e_sentence_pause is None
        assert out.a_paragraph_pause is None
        assert out.silence_begin is None
        assert out.silence_end is None

    def test_full_round_trip(self, tab: VoiceTab) -> None:
        """设置全部字段后往返，应保持一致（含 silence_begin/end）。"""
        cfg = BalconConfig.create_default()
        cfg.n_voice = "TestVoice"
        cfg.id_langid = 1033
        cfg.s_rate = 5
        cfg.p_pitch = -3
        cfg.v_volume = 80
        cfg.e_sentence_pause = 500
        cfg.a_paragraph_pause = 1000
        cfg.silence_begin = 200
        cfg.silence_end = 300

        tab.apply_config(cfg)
        out = BalconConfig.create_default()
        tab.collect_config(out)

        assert out.n_voice == "TestVoice"
        assert out.id_langid == 1033
        assert out.s_rate == 5
        assert out.p_pitch == -3
        assert out.v_volume == 80
        assert out.e_sentence_pause == 500
        assert out.a_paragraph_pause == 1000
        assert out.silence_begin == 200
        assert out.silence_end == 300

    def test_zero_rate_to_none(self, tab: VoiceTab) -> None:
        """语速 0 SHALL 转为 None（避免冗余 -s 0）。"""
        tab.rate_widget.setValue(0)
        out = BalconConfig.create_default()
        tab.collect_config(out)
        assert out.s_rate is None

    def test_zero_silence_to_none(self, tab: VoiceTab) -> None:
        """静音 0 SHALL 转为 None（避免冗余 --silence-begin 0）。"""
        tab.silence_begin_widget.setValue(0)
        tab.silence_end_widget.setValue(0)
        out = BalconConfig.create_default()
        tab.collect_config(out)
        assert out.silence_begin is None
        assert out.silence_end is None

    def test_nonzero_silence_preserved(self, tab: VoiceTab) -> None:
        """非零静音值 SHALL 原样写入 cfg。"""
        tab.silence_begin_widget.setValue(500)
        tab.silence_end_widget.setValue(800)
        out = BalconConfig.create_default()
        tab.collect_config(out)
        assert out.silence_begin == 500
        assert out.silence_end == 800

    def test_apply_none_restores_default(
        self, tab: VoiceTab
    ) -> None:
        """apply None 字段时控件应还原到默认值。"""
        cfg = BalconConfig.create_default()
        cfg.s_rate = None
        cfg.p_pitch = None
        cfg.e_sentence_pause = None
        cfg.a_paragraph_pause = None
        cfg.silence_begin = None
        cfg.silence_end = None
        cfg.v_volume = None
        tab.apply_config(cfg)
        # v_volume 为 None 时还原到 100（schema default）
        assert tab.volume_widget.value() == 100
        # 其他字段为 None 时还原到 0
        assert tab.rate_widget.value() == 0
        assert tab.pitch_widget.value() == 0
        assert tab.sentence_pause_widget.value() == 0
        assert tab.paragraph_pause_widget.value() == 0
        assert tab.silence_begin_widget.value() == 0
        assert tab.silence_end_widget.value() == 0


# ---------------------------------------------------------------------------
# 三向联动：slider / spinbox / dial 同步
# ---------------------------------------------------------------------------
class TestThreeWaySync:
    """验证 SliderSpinDial 在 VoiceTab 中的三向联动行为。"""

    def test_volume_slider_change_syncs_dial(
        self, qapp: QApplication
    ) -> None:
        """音量 slider 变化 SHALL 同步到 dial。"""
        tab = VoiceTab()
        tab.volume_widget.slider.setValue(75)
        assert tab.volume_widget.dial is not None
        assert tab.volume_widget.dial.value() == 75
        assert tab.volume_widget.spinbox.value() == 75

    def test_volume_dial_change_syncs_slider(
        self, qapp: QApplication
    ) -> None:
        """音量 dial 变化 SHALL 同步到 slider。"""
        tab = VoiceTab()
        assert tab.volume_widget.dial is not None
        tab.volume_widget.dial.setValue(42)
        assert tab.volume_widget.slider.value() == 42
        assert tab.volume_widget.spinbox.value() == 42

    def test_rate_spinbox_change_syncs_slider(
        self, qapp: QApplication
    ) -> None:
        """语速 spinbox 变化 SHALL 同步到 slider。"""
        tab = VoiceTab()
        tab.rate_widget.spinbox.setValue(7)
        assert tab.rate_widget.slider.value() == 7
        assert tab.rate_widget.value() == 7
