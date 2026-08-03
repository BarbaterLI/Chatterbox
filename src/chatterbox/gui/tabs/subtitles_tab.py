"""字幕分组 Tab 模块。

提供字幕处理开关、字幕格式、自动适配语速、SoundTouch 适配与最大语速率
等参数的 GUI 编辑。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class SubtitlesTab(AbstractTab):
    """字幕参数分组 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "subtitles"

    @classmethod
    def tab_title(cls) -> str:
        return "字幕"

    @classmethod
    def tab_group(cls) -> str:
        return "字幕歌词"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("字幕歌词")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "字幕通用参数。"
            "将输入作为字幕处理 (-sub, 布尔)、"
            "字幕格式 (--sub-format, 可选 srt/lrc/ssa/ass/smi/vtt, 默认自动)、"
            "自动提高语速适配时间间隔 (--sub-fit, 布尔)、"
            "使用 SoundTouch 适配 (--sub-fit-lib, 布尔, 依赖 --sub-fit)、"
            "最大语速率 (--sub-max, 范围 -10~200, 默认 0 = 不限制, "
            "单位百分比, 100=1倍速 / 200=2倍速)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        cfg.sub = self.sub_check.isChecked()
        fmt = self.format_combo.currentData()
        cfg.sub_format = fmt if fmt else None
        cfg.sub_fit = self.sub_fit_check.isChecked()
        cfg.sub_fit_lib = self.sub_fit_lib_check.isChecked()
        # 标准模式：值 0 → None
        cfg.sub_max = (
            None if self.sub_max_spin.value() == 0 else self.sub_max_spin.value()
        )

    def apply_config(self, cfg: BalconConfig) -> None:
        self.sub_check.setChecked(cfg.sub)
        if cfg.sub_format is None:
            self.format_combo.setCurrentIndex(0)
        else:
            idx = self.format_combo.findData(cfg.sub_format)
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            else:
                self.format_combo.setCurrentIndex(0)
        self.sub_fit_check.setChecked(cfg.sub_fit)
        self.sub_fit_lib_check.setChecked(cfg.sub_fit_lib)
        self.sub_max_spin.setValue(
            cfg.sub_max if cfg.sub_max is not None else 0
        )

    def refresh_voices(self, voices: list[str]) -> None:
        """SubtitlesTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """SubtitlesTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # === GroupBox 1: 字幕格式 ===
        fmt_group = QGroupBox("字幕格式")
        fmt_layout = QFormLayout(fmt_group)

        self.sub_check = QCheckBox("将输入作为字幕处理 (-sub)")
        self.sub_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        fmt_layout.addRow(self.sub_check)

        # schema choices=["srt","lrc","ssa","ass","smi","vtt"]
        self.format_combo = QComboBox()
        self.format_combo.addItem("自动", None)
        for v in ["srt", "lrc", "ssa", "ass", "smi", "vtt"]:
            self.format_combo.addItem(v.upper(), v)
        # SubTask 11.4: 「自动」项 tooltip + 整体 tooltip
        self.format_combo.setItemData(
            0,
            "按输入文件扩展名自动选择（.srt→SRT，.lrc→LRC 等）",
            Qt.ToolTipRole,
        )
        self.format_combo.setToolTip(
            "字幕格式 (--sub-format)。自动 = 按扩展名判定"
        )
        self.format_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        fmt_layout.addRow("字幕格式 (--sub-format)：", self.format_combo)

        fmt_group.setLayout(fmt_layout)
        layout.addRow(fmt_group)

        # === GroupBox 2: 语速适配 ===
        fit_group = QGroupBox("语速适配")
        fit_layout = QFormLayout(fit_group)

        self.sub_fit_check = QCheckBox(
            "自动提高语速适配时间间隔 (--sub-fit)"
        )
        self.sub_fit_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        fit_layout.addRow(self.sub_fit_check)

        self.sub_fit_lib_check = QCheckBox("使用 SoundTouch 适配 (--sub-fit-lib)")
        # SubTask 11.5: SoundTouch 库 tooltip
        self.sub_fit_lib_check.setToolTip(
            "使用 SoundTouch 库适配语速（比内置适配质量更高，需 balcon 编译时包含）"
        )
        self.sub_fit_lib_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        # SubTask 11.3: sub_fit_lib_check 依赖 sub_fit_check 联动启用/禁用
        self.sub_fit_lib_check.setEnabled(self.sub_fit_check.isChecked())
        self.sub_fit_check.toggled.connect(self.sub_fit_lib_check.setEnabled)
        fit_layout.addRow(self.sub_fit_lib_check)

        self.sub_max_spin = QSpinBox()
        self.sub_max_spin.setRange(-10, 200)
        self.sub_max_spin.setValue(0)
        # SubTask 11.2: 最大语速提升率 tooltip
        self.sub_max_spin.setToolTip(
            "最大语速提升率 (--sub-max)。百分比：100=1倍速，200=2倍速，0=不限制"
        )
        self.sub_max_spin.valueChanged.connect(
            lambda: self._emit_changed()
        )
        fit_layout.addRow("最大语速率 (--sub-max)：", self.sub_max_spin)

        fit_group.setLayout(fit_layout)
        layout.addRow(fit_group)

        self.setLayout(layout)


__all__ = ["SubtitlesTab"]
