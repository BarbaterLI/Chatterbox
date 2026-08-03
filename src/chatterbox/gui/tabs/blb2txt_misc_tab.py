"""blb2txt 其他参数分组 Tab 模块。

提供 blb2txt.exe 杂项参数的 GUI 编辑：``-dp`` (禁用提示) 与
``-cfg`` (配置文件路径)。

约束：
- 使用 PySide6（QWidget、QCheckBox、QLineEdit、QPushButton）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt 原版样式。
- 控件值变化时调用 :meth:`AbstractTab._emit_changed` 发射
  :attr:`config_changed` 信号。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtMiscTab(AbstractTab):
    """blb2txt 其他参数分组 Tab。

    编辑 blb2txt 杂项 2 个参数：``-dp`` (禁用提示)、``-cfg`` (配置文件
    路径)。

    :meth:`collect_config` / :meth:`apply_config` 操作 :class:`Blb2txtConfig`，
    字段名与配置类声明完全一致（``dp_no_prompt``、``cfg_file``）。
    ``cfg_file`` 为 ``str | None``，控件空字符串映射到 ``None``（避免冗余
    参数）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_misc"

    @classmethod
    def tab_title(cls) -> str:
        return "其他（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "高级"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("其他")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 其他参数。"
            "禁用提示 (-dp, 布尔)、"
            "配置文件路径 (-cfg, 用于加载预定义配置)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从控件读取值，写入 :class:`Blb2txtConfig` 对应字段。"""
        cfg.dp_no_prompt = self.dp_check.isChecked()
        cfg.cfg_file = self.cfg_edit.text().strip() or None

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 :class:`Blb2txtConfig` 读取值，还原控件状态。"""
        self.dp_check.setChecked(cfg.dp_no_prompt)
        self.cfg_edit.setText(cfg.cfg_file or "")

    def refresh_voices(self, voices: list[str]) -> None:
        """Blb2txtMiscTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """Blb2txtMiscTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # -dp 禁用提示
        self.dp_check = QCheckBox("禁用提示 (-dp)")
        self.dp_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.dp_check)

        # -cfg 配置文件路径
        cfg_row = QHBoxLayout()
        self.cfg_edit = QLineEdit()
        self.cfg_edit.setPlaceholderText("选择配置文件……")
        self.cfg_edit.textChanged.connect(lambda: self._emit_changed())
        cfg_browse = QPushButton("浏览…")
        cfg_browse.clicked.connect(self._on_browse_cfg_clicked)
        cfg_row.addWidget(self.cfg_edit, 1)
        cfg_row.addWidget(cfg_browse)
        layout.addRow("配置文件 (-cfg)：", cfg_row)

        self.setLayout(layout)

    def _on_browse_cfg_clicked(self) -> None:
        """-cfg 浏览按钮：选择配置文件。"""
        current = self.cfg_edit.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择配置文件",
            current or "",
            "配置文件 (*.cfg);;所有文件 (*.*)",
        )
        if path:
            self.cfg_edit.setText(path)


__all__ = ["Blb2txtMiscTab"]
