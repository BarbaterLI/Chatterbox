"""音频格式分组 Tab 模块。

提供采样率、位深、声道数三个 choice 类型参数的 GUI 编辑。每项均含
"自动" 选项（对应 ``None``，使用 balcon 默认）。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class AudioFormatTab(AbstractTab):
    """音频格式参数分组 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "audio_format"

    @classmethod
    def tab_title(cls) -> str:
        return "音频格式"

    @classmethod
    def tab_group(cls) -> str:
        return "语音音频"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("语音音频")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "音频格式参数。"
            "采样率 (-fr, 可选 8/11/12/16/22/24/32/44/48 kHz, "
            "11=11025 Hz / 22=22050 Hz / 44=44100 Hz, 默认自动)、"
            "位深 (-bt, 可选 8/16, 默认 16)、"
            "声道数 (-ch, 可选 1=单声道 / 2=立体声, 默认 1)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        rate = self.sample_rate_combo.currentData()
        cfg.fr_sample_rate = str(rate) if rate else None

        depth = self.bit_depth_combo.currentData()
        cfg.bt_bit_depth = str(depth) if depth else None

        ch = self.channels_combo.currentData()
        cfg.ch_channels = str(ch) if ch else None

    def apply_config(self, cfg: BalconConfig) -> None:
        self._select_by_data(self.sample_rate_combo, cfg.fr_sample_rate)
        self._select_by_data(self.bit_depth_combo, cfg.bt_bit_depth)
        self._select_by_data(self.channels_combo, cfg.ch_channels)

    def refresh_voices(self, voices: list[str]) -> None:
        """AudioFormatTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """AudioFormatTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        auto_tooltip = "自动 = 使用 balcon 默认（通常 22050 Hz / 16 位 / 单声道）"

        # 采样率：schema choices=["8","11","12","16","22","24","32","44","48"]
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItem("自动", None)
        sample_rate_hz_map = {
            "8": "8000 Hz",
            "11": "11025 Hz",
            "12": "12000 Hz",
            "16": "16000 Hz",
            "22": "22050 Hz",
            "24": "24000 Hz",
            "32": "32000 Hz",
            "44": "44100 Hz",
            "48": "48000 Hz",
        }
        for v in ["8", "11", "12", "16", "22", "24", "32", "44", "48"]:
            self.sample_rate_combo.addItem(f"{v} kHz", v)
        # SubTask 10.1: ComboBox 整体 tooltip
        self.sample_rate_combo.setToolTip(
            "采样率 (-fr)。注意：11=11025 Hz，22=22050 Hz，44=44100 Hz"
            "（balcon 以 kHz 近似值表示）"
        )
        # SubTask 10.1: 各采样率项 tooltip 显示精确 Hz 值
        for i in range(1, self.sample_rate_combo.count()):
            v = self.sample_rate_combo.itemData(i)
            if v in sample_rate_hz_map:
                self.sample_rate_combo.setItemData(
                    i, sample_rate_hz_map[v], Qt.ToolTipRole
                )
        # SubTask 10.2: "自动" 项 tooltip
        self.sample_rate_combo.setItemData(0, auto_tooltip, Qt.ToolTipRole)
        self.sample_rate_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("采样率 (-fr)：", self.sample_rate_combo)

        # 位深：schema choices=["8","16"]
        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItem("自动", None)
        for v in ["8", "16"]:
            self.bit_depth_combo.addItem(f"{v} 位", v)
        # SubTask 10.3: 位深 ComboBox tooltip
        self.bit_depth_combo.setToolTip(
            "位深 (-bt)。可选 8/16，默认 16（balcon 默认）"
        )
        # SubTask 10.2: "自动" 项 tooltip
        self.bit_depth_combo.setItemData(0, auto_tooltip, Qt.ToolTipRole)
        self.bit_depth_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("位深 (-bt)：", self.bit_depth_combo)

        # 声道数：schema choices=["1","2"]
        self.channels_combo = QComboBox()
        self.channels_combo.addItem("自动", None)
        for v in ["1", "2"]:
            label = "单声道" if v == "1" else "立体声"
            self.channels_combo.addItem(f"{label} ({v})", v)
        # SubTask 10.3: 声道数 ComboBox tooltip
        self.channels_combo.setToolTip(
            "声道数 (-ch)。可选 1/2，默认 1（单声道，balcon 默认）"
        )
        # SubTask 10.2: "自动" 项 tooltip
        self.channels_combo.setItemData(0, auto_tooltip, Qt.ToolTipRole)
        self.channels_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("声道数 (-ch)：", self.channels_combo)

        self.setLayout(layout)

    @staticmethod
    def _select_by_data(combo: QComboBox, value: object) -> None:
        """根据 userData 选中对应项；``None`` 或未匹配时选中第 0 项。"""
        if value is None:
            combo.setCurrentIndex(0)
            return
        target = str(value)
        for i in range(combo.count()):
            data = combo.itemData(i)
            if data is not None and str(data) == target:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)


__all__ = ["AudioFormatTab"]
