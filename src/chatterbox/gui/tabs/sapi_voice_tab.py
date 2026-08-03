"""SAPI5 语音与参数选项卡模块。"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.sapi_config import SapiConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider
from chatterbox.gui.widgets.slider_spin_dial import SliderSpinDial

logger = logging.getLogger(__name__)


class SapiVoiceTab(AbstractTab):
    """SAPI5 语音与参数分组 Tab。

    编辑 4 个 SAPI5 参数：语音名称、语速、音量、音调。
    3 个数值参数使用 :class:`SliderSpinDial` 三向联动复合控件，
    音量参数额外增加 QDial 旋钮。语音名称列表由主窗口通过
    :meth:`refresh_voices` 注入。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "sapi_voice"

    @classmethod
    def tab_title(cls) -> str:
        return "语音与参数"

    @classmethod
    def tab_group(cls) -> str:
        return "语音音频"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.SAPI

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("语音音频")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "SAPI5 语音参数。"
            "语音名称（空=系统默认）、"
            "语速（范围 -10~10, 默认 0, 正值加快、负值减慢）、"
            "音量（范围 0~100, 默认 100）、"
            "音调（范围 -10~10, 默认 0, 通过 SAPI5 XML 标记实现）"
        )

    def collect_config(self, cfg: SapiConfig) -> None:
        """从控件读取值，写入 :class:`SapiConfig`。"""
        cfg.voice_name = self.voice_combo.currentData() or ""
        cfg.rate = self.rate_widget.value()
        cfg.volume = self.volume_widget.value()
        cfg.pitch = self.pitch_widget.value()
        cfg.audio_format = self.audio_format_combo.currentData()

    def apply_config(self, cfg: SapiConfig) -> None:
        """从 :class:`SapiConfig` 读取值，还原控件状态。"""
        if cfg.voice_name:
            idx = self.voice_combo.findData(cfg.voice_name)
            if idx >= 0:
                self.voice_combo.setCurrentIndex(idx)
            else:
                # 语音不在列表中：回退到默认项
                self.voice_combo.setCurrentIndex(0)
        else:
            self.voice_combo.setCurrentIndex(0)
        self.rate_widget.setValue(cfg.rate)
        self.volume_widget.setValue(cfg.volume)
        self.pitch_widget.setValue(cfg.pitch)
        # 音频格式：在 combo 中查找匹配的 itemData，未命中则保持默认项
        for i in range(self.audio_format_combo.count()):
            if self.audio_format_combo.itemData(i) == cfg.audio_format:
                self.audio_format_combo.setCurrentIndex(i)
                break

    def refresh_voices(self, voices: list[str]) -> None:
        """刷新语音下拉列表，保留首个「系统默认」项。

        Args:
            voices: SAPI5 系统可用语音名称列表。
        """
        # 记录当前选择，刷新后尝试还原
        current_data = self.voice_combo.currentData()
        # 清空，仅保留第一个"系统默认"项
        while self.voice_combo.count() > 1:
            self.voice_combo.removeItem(self.voice_combo.count() - 1)
        for v in voices:
            self.voice_combo.addItem(v, v)
        # 还原选择
        if current_data:
            idx = self.voice_combo.findData(current_data)
            if idx >= 0:
                self.voice_combo.setCurrentIndex(idx)
            else:
                self.voice_combo.setCurrentIndex(0)
        else:
            self.voice_combo.setCurrentIndex(0)

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """SapiVoiceTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建 SAPI5 语音与参数界面。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        # 语音选择：空字符串 = 系统默认
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(80)
        self.voice_combo.addItem("（系统默认语音）", "")
        self.voice_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        form.addRow("语音：", self.voice_combo)

        # 语速
        self.rate_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.rate_widget.setDescription(
            "语速。范围 -10 到 10，默认 0，正值加快、负值减慢"
        )
        form.addRow("语速：", self.rate_widget)

        # 音量（含 QDial 旋钮）
        self.volume_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=100,
            value=100,
            tick_interval=10,
            step=1,
            with_dial=True,
        )
        self.volume_widget.setDescription(
            "音量。范围 0 到 100，默认 100"
        )
        form.addRow("音量：", self.volume_widget)

        # 音调
        self.pitch_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.pitch_widget.setDescription(
            "音调。范围 -10 到 10，默认 0，通过 SAPI5 XML 标记实现"
        )
        form.addRow("音调：", self.pitch_widget)

        # 音频格式：SAPI5 SpeechAudioFormatType 枚举值
        self.audio_format_combo = QComboBox(self)
        self.audio_format_combo.addItem("16kHz/16bit/Mono", 22)
        self.audio_format_combo.addItem("22.05kHz/16bit/Mono", 21)
        self.audio_format_combo.addItem("44.1kHz/16bit/Stereo", 31)
        self.audio_format_combo.addItem("48kHz/16bit/Stereo", 32)
        self.audio_format_combo.setCurrentIndex(0)
        self.audio_format_combo.setMinimumWidth(80)
        self.audio_format_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        form.addRow("音频格式：", self.audio_format_combo)

        outer.addLayout(form)
        outer.addStretch(1)

        self.setLayout(outer)

    def _make_slider_spin_dial(
        self,
        minimum: int,
        maximum: int,
        value: int,
        tick_interval: int,
        step: int,
        with_dial: bool = False,
    ) -> SliderSpinDial:
        """创建 SliderSpinDial 复合控件并配置参数。

        Args:
            minimum: 最小值。
            maximum: 最大值。
            value: 初始值。
            tick_interval: slider 刻度间隔。
            step: 单步增量。
            with_dial: 是否包含 QDial 旋钮（音量参数为 True）。
        """
        widget = SliderSpinDial(with_dial=with_dial, parent=self)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setTickInterval(tick_interval)
        widget.slider.setMinimumWidth(40)
        widget.valueChanged.connect(lambda _: self._emit_changed())
        return widget


__all__ = ["SapiVoiceTab"]
