"""字典选项卡模块。

提供 :class:`DictionaryTab`，封装 balcon ``-d`` 字典文件列表的 GUI 控件，
支持通过文件对话框添加多个字典文件、移除选中项与清空全部。

约束：
- 使用 PySide6（QListWidget、QPushButton、QFileDialog、QVBoxLayout、
  QHBoxLayout、QAbstractItemView、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)

# 字典文件过滤器
_DICT_FILTER = "字典文件 (*.bxd *.dic *.rex);;所有文件 (*.*)"


class DictionaryTab(AbstractTab):
    """字典选项卡。

    封装 ``-d`` 字段（多文件列表）的 GUI 控件，支持多文件添加、
    移除选中与清空操作。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "dictionary"

    @classmethod
    def tab_title(cls) -> str:
        return "字典"

    @classmethod
    def tab_group(cls) -> str:
        return "输入输出"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("输入输出")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "字典文件参数。"
            "字典文件 (-d, 多文件, 支持 .bxd / .dic / .rex 格式)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """遍历 QListWidget items，收集路径得到 ``list[str]`` 赋值 ``cfg.d_dicts``。

        路径优先从 ``Qt.UserRole`` 读取（绝对路径）；为空时回退到项文本，
        保持向后兼容。
        """
        files: list[str] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(Qt.UserRole)
            if not path:
                path = item.text()
            if path:
                files.append(path)
        cfg.d_dicts = files

    def apply_config(self, cfg: BalconConfig) -> None:
        """清空 QListWidget，对 ``cfg.d_dicts`` 每个元素添加 item（含 tooltip 与 UserRole）。"""
        self.list_widget.clear()
        for path in cfg.d_dicts:
            if path:
                self._add_item(path)
        self._update_empty_state()
        self._update_count()

    def _build_ui(self) -> None:
        """构建字典选项卡界面。"""
        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.itemChanged.connect(lambda: self._emit_changed())

        # 空状态提示（SubTask 14.1）：居中灰色文本，通过 QPalette 着色（非 QSS）
        self.empty_label = QLabel(
            "点击『添加』导入字典文件（.bxd .dic .rex）", self
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        palette = self.empty_label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("gray"))
        self.empty_label.setPalette(palette)

        # QStackedWidget 包装：page 0 = 空提示，page 1 = 列表
        self.stacked_widget = QStackedWidget(self)
        self.stacked_widget.addWidget(self.empty_label)  # index 0
        self.stacked_widget.addWidget(self.list_widget)  # index 1

        self.add_btn = QPushButton("添加", self)
        self.add_btn.setToolTip("添加字典文件 (-d)。支持 .bxd .dic .rex 格式")
        self.add_btn.clicked.connect(self._add_files_dialog)
        self.remove_btn = QPushButton("移除", self)
        self.remove_btn.setToolTip("移除选中的字典文件")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton("清空", self)
        self.clear_btn.setToolTip("清空所有字典文件")
        self.clear_btn.clicked.connect(self._clear_all)

        # 文件计数标签（SubTask 14.4）
        self.count_label = QLabel("共 0 个字典文件", self)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_btn)
        button_row.addWidget(self.remove_btn)
        button_row.addWidget(self.clear_btn)
        button_row.addStretch()
        button_row.addWidget(self.count_label)

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)

        # 初始化空状态与计数
        self._update_empty_state()
        self._update_count()

    # ----------------------------------------------------------------------
    # 内部辅助
    # ----------------------------------------------------------------------
    def _add_item(self, path: str) -> None:
        """添加单个字典文件项到列表。

        显示文本为原始路径，绝对路径存入 ``Qt.UserRole``，tooltip 显示
        完整绝对路径（SubTask 14.2）。
        """
        abs_path = os.path.abspath(path)
        item = QListWidgetItem()
        item.setText(path)
        item.setData(Qt.UserRole, abs_path)
        item.setToolTip(abs_path)
        self.list_widget.addItem(item)

    def _update_empty_state(self) -> None:
        """根据列表是否为空切换 QStackedWidget 当前页（SubTask 14.1）。"""
        if self.list_widget.count() == 0:
            self.stacked_widget.setCurrentIndex(0)
        else:
            self.stacked_widget.setCurrentIndex(1)

    def _update_count(self) -> None:
        """更新文件计数标签文本（SubTask 14.4）。"""
        self.count_label.setText(f"共 {self.list_widget.count()} 个字典文件")

    def _add_files_dialog(self) -> None:
        """打开多文件选择对话框，添加字典文件到列表。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择字典文件",
            "",
            _DICT_FILTER,
        )
        if not paths:
            return
        existing = {
            self.list_widget.item(i).data(Qt.UserRole)
            for i in range(self.list_widget.count())
        }
        for path in paths:
            if not path:
                continue
            abs_path = os.path.abspath(path)
            if abs_path in existing:
                continue
            existing.add(abs_path)
            self._add_item(path)
        self._update_empty_state()
        self._update_count()
        self._emit_changed()

    def _remove_selected(self) -> None:
        """移除列表中选中的项。"""
        items = self.list_widget.selectedItems()
        if not items:
            return
        for item in items:
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_empty_state()
        self._update_count()
        self._emit_changed()

    def _clear_all(self) -> None:
        """清空整个列表（有内容时弹确认对话框，SubTask 14.3）。"""
        if self.list_widget.count() == 0:
            return
        reply = QMessageBox.question(
            self,
            "确认",
            "清空所有字典文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.list_widget.clear()
        self._update_empty_state()
        self._update_count()
        self._emit_changed()


__all__ = ["DictionaryTab"]
