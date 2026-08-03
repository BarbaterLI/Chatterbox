"""快捷键帮助对话框。

提供 :class:`ShortcutsDialog`，以分组树形列表展示应用快捷键：

- 顶部搜索框支持按 ``key`` 或 ``description`` 子串模糊匹配（不区分大小写）
- 中间 :class:`QTreeWidget` 按 ``group`` 作为顶层节点分组展示
- 顶层分组节点不可编辑、不可选中，仅作展开/收起
- 默认所有分组展开
- 列头可点击按 ``key`` 或 ``description`` 字母序排序，默认按分组顺序展示
- 底部「关闭」按钮触发 ``accept()`` 关闭对话框

使用 Qt6 原生风格，不引入自定义 QSS。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ShortcutItem:
    """快捷键项数据模型。

    Args:
        key: 快捷键文本（如 ``"Ctrl+Shift+P"``）。
        description: 说明（如 ``"打开命令面板"``）。
        group: 分组（如 ``"导航"``、``"文件"``、``"执行控制"``、``"主题"``）。
    """

    key: str
    description: str
    group: str = "其他"


class ShortcutsDialog(QDialog):
    """快捷键帮助对话框。

    以分组树形列表展示快捷键，支持搜索过滤与列头排序。

    Args:
        shortcuts: 快捷键项列表，按 ``group`` 字段分组展示；
            分组顺序按首次出现顺序保留。
        parent: 父窗口。
    """

    def __init__(
        self,
        shortcuts: list[ShortcutItem],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键帮助")
        self.setModal(True)
        self.resize(500, 500)

        self._shortcuts: list[ShortcutItem] = list(shortcuts)

        # 顶部搜索框
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("搜索快捷键…")
        self._search_box.textChanged.connect(self._apply_filter)

        # 中间树形列表
        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["快捷键", "说明"])
        self._tree.setColumnWidth(0, 160)
        header = self._tree.header()
        header.setStretchLastSection(True)
        # 列头可点击排序：手动处理点击，避免 setSortingEnabled 在构建后
        # 自动按列排序而破坏默认的分组插入顺序
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)

        # 底部关闭按钮
        self._close_button = QPushButton("关闭", self)
        self._close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_box)
        layout.addWidget(self._tree)
        layout.addLayout(button_row)

        # 构建树（保持分组与项的插入顺序，默认按 group 分组展示）
        self._build_tree()

    # ------------------------------------------------------------------
    # 树形构建
    # ------------------------------------------------------------------
    def _build_tree(self) -> None:
        """按 ``group`` 分组构建树形列表，保留分组首次出现顺序。"""
        self._tree.clear()

        # 按 group 分组，保留首次出现顺序
        groups: dict[str, list[ShortcutItem]] = {}
        for item in self._shortcuts:
            groups.setdefault(item.group, []).append(item)

        for group_name, items in groups.items():
            group_item = QTreeWidgetItem(self._tree)
            group_item.setText(0, group_name)
            # 顶层分组节点：仅启用（可展开/收起），不可选中、不可编辑
            group_item.setFlags(Qt.ItemIsEnabled)
            for sc in items:
                child = QTreeWidgetItem(group_item)
                child.setText(0, sc.key)
                child.setText(1, sc.description)
                child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            # 默认所有分组展开
            group_item.setExpanded(True)

    # ------------------------------------------------------------------
    # 列头排序
    # ------------------------------------------------------------------
    def _on_header_clicked(self, column: int) -> None:
        """点击列头按该列字母序排序树节点。

        同列再次点击切换升序/降序；切换列时默认升序。
        排序通过 :meth:`QTreeWidget.sortByColumn` 在各层级内进行：
        顶层分组节点按组名相互排序，各分组内子节点按对应列排序。

        Args:
            column: 被点击的列索引（0=快捷键，1=说明）。
        """
        header = self._tree.header()
        if header.sortIndicatorSection() == column:
            new_order = (
                Qt.DescendingOrder
                if header.sortIndicatorOrder() == Qt.AscendingOrder
                else Qt.AscendingOrder
            )
        else:
            new_order = Qt.AscendingOrder
        header.setSortIndicator(column, new_order)
        self._tree.sortByColumn(column, new_order)

    # ------------------------------------------------------------------
    # 搜索过滤
    # ------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        """根据搜索文本过滤树节点。

        按 ``key`` 或 ``description`` 子串匹配（不区分大小写）。
        不匹配的子节点隐藏；组内全部隐藏时分组节点也隐藏；
        搜索框清空时恢复全部显示。

        Args:
            text: 搜索框当前文本。
        """
        query = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(i)
            visible_count = 0
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                key = child.text(0).lower()
                desc = child.text(1).lower()
                if not query or query in key or query in desc:
                    child.setHidden(False)
                    visible_count += 1
                else:
                    child.setHidden(True)
            # 组内全部隐藏时，分组节点也隐藏
            group_item.setHidden(visible_count == 0)
