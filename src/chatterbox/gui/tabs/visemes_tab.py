"""Visemes 视位选项卡模块。

提供 :class:`VisemesTab`，封装 balcon visemes 输出文件参数的 GUI 控件。

约束：
- 使用 PySide6（QLabel、QLineEdit、QPushButton、QFileDialog、QFormLayout、
  QHBoxLayout、QVBoxLayout、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class VisemesTab(AbstractTab):
    """Visemes 视位选项卡。

    封装 ``-vs`` 字段（visemes 输出文件）的 GUI 控件。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "visemes"

    @classmethod
    def tab_title(cls) -> str:
        return "Visemes 视位"

    @classmethod
    def tab_group(cls) -> str:
        return "高级"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("高级")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "Visemes 视位输出参数。"
            "visemes 输出文本文件 (-vs, "
            "每行含音素标识与时间戳, 用于口型同步动画)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """从控件读值，写入 ``cfg.vs_visemes``。

        - QLineEdit 空字符串 → None，否则 str
        """
        path = self.vs_edit.text().strip()
        cfg.vs_visemes = path if path else None

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg.vs_visemes`` 读值，还原控件状态。"""
        self.vs_edit.setText(cfg.vs_visemes or "")

    def _build_ui(self) -> None:
        """构建 Visemes 选项卡界面。"""
        # 顶部说明 QLabel
        self.desc_label = QLabel(
            "输出可视音素（visemes）文本，用于口型同步动画。每行包含音素标识与时间戳",
            self,
        )
        self.desc_label.setWordWrap(True)

        self.vs_edit = QLineEdit(self)
        self.vs_edit.setPlaceholderText("如 output.txt")
        self.vs_edit.textChanged.connect(lambda: self._emit_changed())
        self.vs_browse_btn = QPushButton("浏览", self)
        self.vs_browse_btn.clicked.connect(self._browse_vs_file)

        row = QHBoxLayout()
        row.addWidget(self.vs_edit, 1)
        row.addWidget(self.vs_browse_btn)
        container = QWidget(self)
        container.setLayout(row)

        form = QFormLayout()
        form.addRow("Visemes 输出文件 (-vs)：", container)

        outer = QVBoxLayout(self)
        outer.addWidget(self.desc_label)
        outer.addLayout(form)
        outer.addStretch()

    def _browse_vs_file(self) -> None:
        """打开保存文件对话框，选择 visemes 输出文件。"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择 visemes 输出文件",
            "",
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if path:
            self.vs_edit.setText(path)


__all__ = ["VisemesTab"]
