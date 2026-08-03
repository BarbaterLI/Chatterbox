"""音频设备分组 Tab 模块。

提供音频输出设备索引与设备名称参数的 GUI 编辑。设备列表由主窗口通过
:meth:`refresh_devices` 注入。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLineEdit,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class DeviceTab(AbstractTab):
    """音频设备参数分组 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "device"

    @classmethod
    def tab_title(cls) -> str:
        return "音频设备"

    @classmethod
    def tab_group(cls) -> str:
        return "语音音频"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("语音音频")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "音频输出设备参数。"
            "输出设备索引 (-b, 默认 0 = 默认设备, 不传 -b)、"
            "设备名称 (-r, 优先于索引 -b)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        idx = self.device_combo.currentData()
        cfg.b_device_index = idx if (isinstance(idx, int) and idx > 0) else None

        name = self.device_name_edit.text().strip()
        cfg.r_device_name = name if name else None

    def apply_config(self, cfg: BalconConfig) -> None:
        if cfg.b_device_index is not None and cfg.b_device_index > 0:
            idx = self.device_combo.findData(cfg.b_device_index)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        else:
            self.device_combo.setCurrentIndex(0)

        self.device_name_edit.setText(
            cfg.r_device_name if cfg.r_device_name is not None else ""
        )

    def refresh_voices(self, voices: list[str]) -> None:
        """DeviceTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """刷新设备下拉列表。

        首项固定为 "默认设备（不指定 -b）"（userData=0），随后按 ``devices``
        顺序追加每一项，显示为 ``"索引: 名称"``，userData 为设备索引。
        """
        self.device_combo.clear()
        self.device_combo.addItem("默认设备（不指定 -b）", 0)
        for idx, name in devices:
            self.device_combo.addItem(f"{idx}: {name}", idx)

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        self.device_combo = QComboBox()
        self.device_combo.addItem("默认设备（不指定 -b）", 0)
        self.device_combo.setToolTip(
            "音频输出设备索引 (-b)。0 = 默认设备（不传 -b）。"
            "设备名称 (-r) 优先于此索引"
        )
        self.device_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("输出设备 (-b)：", self.device_combo)

        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("如 'Speakers (Realtek)'")
        self.device_name_edit.setToolTip("设备名称 (-r)，优先于索引 (-b)")
        self.device_name_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("设备名称 (-r)：", self.device_name_edit)

        self.setLayout(layout)


__all__ = ["DeviceTab"]
