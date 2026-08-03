"""侧边栏导航控件：左侧分组列表（支持分组折叠 + 搜索过滤）+ 右侧堆叠面板。

提供 :class:`SidebarTabWidget`，内部使用 ``QSplitter`` 布局：左侧
``QListWidget`` 作为分组导航（顶部内置 ``QLineEdit`` 搜索框，通过
``setViewportMargins`` 预留空间，使其视觉上位于列表上方且不引入额外
容器），右侧 ``QStackedWidget`` 承载各 Tab 页面。侧边栏宽度可通过
拖拽 Splitter 手柄调整（范围 ``_SIDEBAR_MIN_WIDTH`` ~
``_SIDEBAR_MAX_WIDTH``），初始为 ``_SIDEBAR_WIDTH``。

分组标题项不可选中（仅作为视觉分隔），点击分组标题可折叠/展开该分组
（前缀 ``▼`` 展开 / ``▶`` 折叠，折叠状态通过标题文本前缀判断）；
搜索框按 ``tab_title`` / ``tab_description`` 模糊匹配过滤 Tab 项
（150ms 防抖），与折叠状态协同（折叠组内项保持隐藏）。

约束：
- 使用 PySide6（QListWidget、QStackedWidget、QSplitter、QListWidgetItem、
  QLineEdit、QTimer 等）。
- 不写自定义 QSS，保留 Qt 原版样式；分组标题的小号灰色通过
  ``QListWidgetItem.setFont`` / ``setForeground`` 设置（非样式表）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QMouseEvent, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QWidget,
)

logger = logging.getLogger(__name__)

# 侧边栏宽度配置
_SIDEBAR_WIDTH = 180
_SIDEBAR_MIN_WIDTH = 100
_SIDEBAR_MAX_WIDTH = 400

# 分组标题项的 data key（区分分组标题与 Tab 项）
_GROUP_HEADER_ROLE = Qt.ItemDataRole.UserRole + 1
# 分组名 data key（标题项与 Tab 项均存储所属分组名，便于折叠/过滤查找）
_GROUP_NAME_ROLE = Qt.ItemDataRole.UserRole + 2
# Tab 标题 data key（用于搜索过滤）
_TAB_TITLE_ROLE = Qt.ItemDataRole.UserRole + 3
# Tab 描述 data key（用于搜索过滤）
_TAB_DESC_ROLE = Qt.ItemDataRole.UserRole + 4

# 折叠/展开前缀字符（展开 ▼ / 折叠 ▶）
_EXPANDED_PREFIX = "▼ "
_COLLAPSED_PREFIX = "▶ "

# 搜索过滤防抖延时（毫秒）
_FILTER_DEBOUNCE_MS = 150


class _SidebarListWidget(QListWidget):
    """侧边栏列表：内置搜索框 + 分组标题点击折叠。

    - 通过 ``setViewportMargins`` 在顶部预留空间放置 ``QLineEdit`` 搜索框，
      使其视觉上位于列表上方，同时保持 ``QListWidget`` 直接作为
      ``QSplitter`` 子部件（不引入额外容器，保留原生选中语义）。
    - 鼠标按下分组标题项时发射 :attr:`groupHeaderPressed` 信号以切换折叠，
      并消费事件（不触发原生选中切换）；其余点击交由父类处理，保留
      ``QListWidget`` 原生选中语义。

    Signals:
        groupHeaderPressed(int): 鼠标按下分组标题项时发射，参数为该标题行号。
    """

    groupHeaderPressed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("筛选选项卡…")
        self._search_height: int = max(
            self._search_edit.sizeHint().height(), 10
        )
        # 在顶部预留搜索框高度，使列表视口下移，避免首项被搜索框遮挡
        self.setViewportMargins(0, self._search_height, 0, 0)

    def search_edit(self) -> QLineEdit:
        """返回内置搜索框部件。"""
        return self._search_edit

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """重设搜索框几何以贴合列表顶部（保留边框宽度）。"""
        super().resizeEvent(event)
        fw = self.frameWidth()
        self._search_edit.setGeometry(
            fw, fw, max(self.width() - 2 * fw, 0), self._search_height
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """拦截分组标题项的左键点击，发射折叠信号并消费事件。

        非标题项或非左键点击交由父类处理，保留 ``QListWidget`` 原生选中语义。
        """
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item is not None and item.data(_GROUP_HEADER_ROLE):
                row = self.row(item)
                self.groupHeaderPressed.emit(row)
                event.accept()
                return
        super().mousePressEvent(event)


class SidebarTabWidget(QWidget):
    """侧边栏分组导航 + 堆叠面板。

    左侧 ``QListWidget`` 按分组展示 Tab 项（顶部内置搜索框），右侧
    ``QStackedWidget`` 承载对应页面。两者通过内部 ``QSplitter`` 布局，
    可拖拽调整侧边栏宽度（范围 ``_SIDEBAR_MIN_WIDTH`` ~
    ``_SIDEBAR_MAX_WIDTH``）。分组标题项不可选中，仅作视觉分隔；点击
    分组标题可折叠/展开该分组；搜索框按标题/描述模糊匹配过滤 Tab 项。

    Signals:
        currentChanged(int): 当前页索引改变（Tab 索引，非侧边栏行号）。
    """

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 侧边栏行号 → 堆叠面板索引
        self._row_to_stack: dict[int, int] = {}
        # 堆叠面板索引 → 侧边栏行号
        self._stack_to_row: dict[int, int] = {}
        # 分组名 → 分组标题所在行号（避免重复插入分组标题）
        self._group_rows: dict[str, int] = {}
        # 防止递归切换的标志
        self._updating: bool = False

        self._build_ui()

        # 搜索框信号 + 防抖定时器
        self._search_edit: QLineEdit = self.sidebar.search_edit()
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._on_filter_timeout)

        # 分组标题点击折叠：列表发射 groupHeaderPressed → 切换折叠
        self.sidebar.groupHeaderPressed.connect(self._toggle_group)

    # ----------------------------------------------------------------------
    # UI 构建
    # ----------------------------------------------------------------------
    def _build_ui(self) -> None:
        """构建侧边栏 + 堆叠面板布局（QSplitter，可拖拽调整侧边栏宽度）。"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 使用 QSplitter 让侧边栏可拖拽调整宽度（替代固定宽度）
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        # 侧边栏列表（内置搜索框：通过 setViewportMargins 预留顶部空间）
        self.sidebar = _SidebarListWidget(self._splitter)
        self.sidebar.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
        self.sidebar.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
        self.sidebar.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)

        # 堆叠面板
        self.stack = QStackedWidget(self._splitter)

        self._splitter.addWidget(self.sidebar)
        self._splitter.addWidget(self.stack)
        # 初始拉伸比例：侧边栏不拉伸，堆叠面板拉伸
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        # 设置侧边栏初始宽度（作为起始位置，仍可拖拽调整）
        self._splitter.setSizes([_SIDEBAR_WIDTH, 800])

        layout.addWidget(self._splitter)
        self.setLayout(layout)

    # ----------------------------------------------------------------------
    # 公开方法
    # ----------------------------------------------------------------------
    def add_tab(
        self,
        widget: QWidget,
        group: str,
        title: str,
        icon: QIcon | None = None,
        description: str | None = None,
    ) -> int:
        """添加一个 Tab 到指定分组。

        若该分组尚未出现，先插入一条不可选中的分组标题项（前缀 ``▼``
        表示展开），随后插入 Tab 项。Tab 项显示图标（若提供）与标题。

        Args:
            widget: Tab 页面部件。
            group: 分组名（如 ``"输入输出"``）。
            title: Tab 标题。
            icon: Tab 图标，``None`` 则不显示。
            description: 侧边栏 tooltip 文本，``None`` 则不设置。

        Returns:
            Tab 索引（堆叠面板索引）。
        """
        # 若分组标题尚未插入，先插入分组标题项
        if group not in self._group_rows:
            header_item = QListWidgetItem(_EXPANDED_PREFIX + group)
            header_item.setData(_GROUP_HEADER_ROLE, True)
            header_item.setData(_GROUP_NAME_ROLE, group)
            # 仅启用、不可选中：作为视觉分隔
            header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            # 文字小号加粗灰色（通过 item 属性设置，非 QSS）
            font = QFont(header_item.font())
            font.setBold(True)
            font.setPointSize(max(font.pointSize() - 1, 1))
            header_item.setFont(font)
            header_item.setForeground(
                self.sidebar.palette().color(QPalette.ColorRole.Mid)
            )
            self.sidebar.addItem(header_item)
            self._group_rows[group] = self.sidebar.count() - 1

        # 添加 Tab 项
        tab_item = QListWidgetItem(title)
        tab_item.setData(_GROUP_HEADER_ROLE, False)
        tab_item.setData(_GROUP_NAME_ROLE, group)
        tab_item.setData(_TAB_TITLE_ROLE, title)
        tab_item.setData(_TAB_DESC_ROLE, description or "")
        tab_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        if icon is not None and not icon.isNull():
            tab_item.setIcon(icon)
        if description is not None:
            tab_item.setToolTip(description)
        self.sidebar.addItem(tab_item)
        row = self.sidebar.count() - 1

        # 添加 widget 到堆叠面板
        stack_index = self.stack.addWidget(widget)
        self._row_to_stack[row] = stack_index
        self._stack_to_row[stack_index] = row

        # 若是第一个 Tab，默认选中
        if self.stack.count() == 1:
            self.sidebar.setCurrentRow(row)

        return stack_index

    def clear(self) -> None:
        """清空所有侧边栏项与堆叠页面。

        移除全部 ``QListWidget`` 项与 ``QStackedWidget`` 页面，并重置
        ``_row_to_stack`` / ``_stack_to_row`` / ``_group_rows`` 映射。
        用于工具切换时先清空再重新填充 Tab，避免残留旧项。

        Notes:
            - 幂等：对空状态调用不报错。
            - 不会调用 ``widget.deleteLater()``：widget 由调用方管理
              生命周期；``QStackedWidget.removeWidget`` 仅移除所有权。
        """
        # QListWidget.clear() 移除并删除所有项
        self.sidebar.clear()

        # QStackedWidget 无 clear() 方法，逐个移除（不删除 widget 本身）
        while self.stack.count() > 0:
            page = self.stack.widget(0)
            if page is not None:
                self.stack.removeWidget(page)

        # 重置内部映射与分组状态
        self._row_to_stack.clear()
        self._stack_to_row.clear()
        self._group_rows.clear()

    def count(self) -> int:
        """返回 Tab 总数。"""
        return self.stack.count()

    def current_index(self) -> int:
        """返回当前 Tab 索引（堆叠面板索引），无 Tab 时返回 -1。"""
        return self.stack.currentIndex()

    def set_current_index(self, index: int) -> None:
        """切换到指定 Tab 索引。

        Args:
            index: 目标 Tab 索引（堆叠面板索引）。
        """
        if index < 0 or index >= self.stack.count():
            return
        row = self._stack_to_row.get(index)
        if row is not None:
            self.sidebar.setCurrentRow(row)

    def widget(self, index: int) -> QWidget | None:
        """返回指定索引的 Tab 页面部件。

        Args:
            index: Tab 索引（堆叠面板索引）。

        Returns:
            对应的 QWidget；索引越界时返回 ``None``。
        """
        if index < 0 or index >= self.stack.count():
            return None
        return self.stack.widget(index)

    # ----------------------------------------------------------------------
    # 分组折叠（T-B1）
    # ----------------------------------------------------------------------
    def set_collapsed_groups(self, groups: list[str]) -> None:
        """批量设置折叠的分组名列表。

        更新所有分组标题前缀（``▼`` 展开 / ``▶`` 折叠），随后重新应用
        当前搜索过滤以使折叠状态与可见性一致。折叠状态通过标题文本
        前缀字符判断（不依赖外部存储），持久化由主窗口通过
        ``AppSettings.collapsed_groups`` 处理。

        Args:
            groups: 需折叠的分组名列表；未在列表中的分组会被展开。
        """
        target = set(groups)
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            if item is None or not item.data(_GROUP_HEADER_ROLE):
                continue
            group_name = item.data(_GROUP_NAME_ROLE)
            if group_name is None:
                continue
            if group_name in target:
                item.setText(_COLLAPSED_PREFIX + group_name)
            else:
                item.setText(_EXPANDED_PREFIX + group_name)
        # 一次性重新应用过滤（折叠 + 搜索协同）
        self._apply_filter(self._search_edit.text())

    def get_collapsed_groups(self) -> list[str]:
        """返回当前折叠的分组名列表（通过分组标题文本前缀判断）。"""
        result: list[str] = []
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            if item is None or not item.data(_GROUP_HEADER_ROLE):
                continue
            text = item.text()
            if text.startswith(_COLLAPSED_PREFIX):
                group_name = item.data(_GROUP_NAME_ROLE)
                if group_name is None:
                    group_name = text[len(_COLLAPSED_PREFIX):]
                result.append(group_name)
        return result

    def _toggle_group(self, header_row: int) -> None:
        """切换指定分组标题行的折叠状态（折叠↔展开）。

        Args:
            header_row: 分组标题所在行号。
        """
        item = self.sidebar.item(header_row)
        if item is None or not item.data(_GROUP_HEADER_ROLE):
            return
        group_name = item.data(_GROUP_NAME_ROLE)
        if group_name is None:
            return
        collapsed = item.text().startswith(_COLLAPSED_PREFIX)
        self._set_group_collapsed(group_name, not collapsed)

    def _set_group_collapsed(self, group_name: str, collapsed: bool) -> None:
        """设置单个分组的折叠状态（更新前缀并重新应用过滤）。"""
        header_item = self._find_header_item(group_name)
        if header_item is None:
            return
        if collapsed:
            header_item.setText(_COLLAPSED_PREFIX + group_name)
        else:
            header_item.setText(_EXPANDED_PREFIX + group_name)
        # 重新应用当前过滤（折叠 + 搜索协同）
        self._apply_filter(self._search_edit.text())

    def _find_header_item(self, group_name: str) -> QListWidgetItem | None:
        """返回指定分组的标题项；不存在时返回 ``None``。"""
        row = self._group_rows.get(group_name)
        if row is None:
            return None
        return self.sidebar.item(row)

    def _is_group_collapsed(self, group_name: str | None) -> bool:
        """判断指定分组是否折叠（通过标题文本前缀判断）。"""
        if group_name is None:
            return False
        header_item = self._find_header_item(group_name)
        if header_item is None:
            return False
        return header_item.text().startswith(_COLLAPSED_PREFIX)

    # ----------------------------------------------------------------------
    # 搜索过滤（T-B2）
    # ----------------------------------------------------------------------
    def _on_search_changed(self, text: str) -> None:
        """搜索框文本变化：停止上一个防抖定时器并重新启动 150ms 定时器。"""
        self._filter_timer.stop()
        self._filter_timer.start(_FILTER_DEBOUNCE_MS)

    def _on_filter_timeout(self) -> None:
        """防抖定时器触发：以搜索框当前文本执行过滤。"""
        self._apply_filter(self._search_edit.text())

    def _apply_filter(self, text: str) -> None:
        """按 ``tab_title`` / ``tab_description`` 模糊匹配过滤 Tab 项。

        - 不区分大小写、子串匹配。
        - 不匹配的 Tab 项 ``setHidden(True)``，匹配的 ``setHidden(False)``。
        - 组内全部隐藏时分组标题一并隐藏；搜索框为空时恢复全部显示
          （尊重折叠状态：折叠组内项保持隐藏）。
        - 折叠的组即使有匹配项也不展开（保持折叠，仅显示分组标题）。

        Args:
            text: 搜索文本（空串表示无过滤）。
        """
        text_lower = text.lower().strip()
        filter_active = text_lower != ""

        # 预计算每个分组是否有匹配项（用于决定分组标题可见性）
        groups_with_match: set[str] = set()
        if filter_active:
            for row in range(self.sidebar.count()):
                item = self.sidebar.item(row)
                if item is None or item.data(_GROUP_HEADER_ROLE):
                    continue
                title = item.data(_TAB_TITLE_ROLE) or ""
                desc = item.data(_TAB_DESC_ROLE) or ""
                if text_lower in title.lower() or text_lower in desc.lower():
                    group_name = item.data(_GROUP_NAME_ROLE)
                    if group_name is not None:
                        groups_with_match.add(group_name)

        # 应用可见性
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            if item is None:
                continue
            is_header = bool(item.data(_GROUP_HEADER_ROLE))
            group_name = item.data(_GROUP_NAME_ROLE)
            collapsed = self._is_group_collapsed(group_name)
            if is_header:
                if filter_active:
                    item.setHidden(group_name not in groups_with_match)
                else:
                    item.setHidden(False)
            else:
                if collapsed:
                    # 折叠组：内项保持隐藏（即使匹配也不展开）
                    item.setHidden(True)
                elif filter_active:
                    title = item.data(_TAB_TITLE_ROLE) or ""
                    desc = item.data(_TAB_DESC_ROLE) or ""
                    match = (
                        text_lower in title.lower()
                        or text_lower in desc.lower()
                    )
                    item.setHidden(not match)
                else:
                    item.setHidden(False)

    # ----------------------------------------------------------------------
    # 内部逻辑
    # ----------------------------------------------------------------------
    def _on_sidebar_changed(self, row: int) -> None:
        """侧边栏当前行变化时切换堆叠面板。

        若当前行是分组标题（不可选中），自动跳到最近的下一个可选中的
        Tab 项（跳过隐藏项，避免折叠/过滤后选中不可见项）；若是 Tab 项，
        切换堆叠面板并发射 :attr:`currentChanged`。
        """
        if self._updating:
            return
        if row < 0 or row >= self.sidebar.count():
            return

        item = self.sidebar.item(row)
        if item is None:
            return

        # 分组标题：跳到下一个可选中的 Tab 项
        if item.data(_GROUP_HEADER_ROLE):
            next_row = self._find_next_selectable(row)
            if next_row is not None and next_row != row:
                self._updating = True
                try:
                    self.sidebar.setCurrentRow(next_row)
                finally:
                    self._updating = False
                # setCurrentRow 触发的 currentRowChanged 被 _updating 拦截，
                # 此处手动激活目标行。
                self._activate_row(next_row)
            return

        # Tab 项：切换堆叠面板
        self._activate_row(row)

    def _activate_row(self, row: int) -> None:
        """激活指定行对应的 Tab（切换堆叠面板并发射信号）。

        Args:
            row: 侧边栏行号（对应一个 Tab 项）。
        """
        stack_index = self._row_to_stack.get(row)
        if stack_index is None:
            return
        if stack_index != self.stack.currentIndex():
            self.stack.setCurrentIndex(stack_index)
            self.currentChanged.emit(stack_index)

    def _find_next_selectable(self, start_row: int) -> int | None:
        """从 ``start_row`` 开始向下（再向上）查找下一个可选中的 Tab 项。

        跳过分组标题项与隐藏项（折叠或被搜索过滤的项），避免选中
        不可见项。

        Args:
            start_row: 起始行号（通常是分组标题行）。

        Returns:
            最近的可见 Tab 项行号；若无可用 Tab 项，返回 ``None``。
        """
        # 向下查找
        for row in range(start_row + 1, self.sidebar.count()):
            item = self.sidebar.item(row)
            if item is None:
                continue
            if item.data(_GROUP_HEADER_ROLE):
                continue
            if item.isHidden():
                continue
            return row
        # 向上查找
        for row in range(start_row - 1, -1, -1):
            item = self.sidebar.item(row)
            if item is None:
                continue
            if item.data(_GROUP_HEADER_ROLE):
                continue
            if item.isHidden():
                continue
            return row
        return None


__all__ = ["SidebarTabWidget"]
