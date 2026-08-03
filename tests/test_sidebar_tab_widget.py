"""SidebarTabWidget 单元测试。

验证 ``add_tab`` / ``clear`` 等方法的行为契约，覆盖初始状态、
添加 Tab、清空、清空后再添加等场景。

测试在 offscreen Qt 平台下运行，无需真实显示设备。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6.QtWidgets 之前设置 offscreen 平台插件
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from balcon_batch_tts.gui.widgets.sidebar_tab_widget import SidebarTabWidget


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """返回全局 QApplication 单例（offscreen 模式）。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def tab_widget(qapp: QApplication) -> SidebarTabWidget:
    """返回一个空的 SidebarTabWidget。"""
    return SidebarTabWidget()


def _make_page() -> QWidget:
    """创建一个简单的 QWidget 充当 Tab 页面。"""
    return QWidget()


# ---------------------------------------------------------------------------
# 初始状态
# ---------------------------------------------------------------------------
class TestInitialState:
    """空 widget 的初始状态契约。"""

    def test_sidebar_empty_initially(self, tab_widget: SidebarTabWidget) -> None:
        assert tab_widget.sidebar.count() == 0

    def test_stack_empty_initially(self, tab_widget: SidebarTabWidget) -> None:
        assert tab_widget.stack.count() == 0

    def test_count_is_zero_initially(self, tab_widget: SidebarTabWidget) -> None:
        assert tab_widget.count() == 0

    def test_mappings_empty_initially(self, tab_widget: SidebarTabWidget) -> None:
        assert tab_widget._row_to_stack == {}
        assert tab_widget._stack_to_row == {}
        assert tab_widget._group_rows == {}


# ---------------------------------------------------------------------------
# add_tab
# ---------------------------------------------------------------------------
class TestAddTab:
    """add_tab 行为。"""

    def test_add_three_tabs_count(self, tab_widget: SidebarTabWidget) -> None:
        for i in range(3):
            tab_widget.add_tab(_make_page(), "G1", f"Tab {i}")
        # 堆叠页面数 == Tab 数
        assert tab_widget.count() == 3
        assert tab_widget.stack.count() == 3

    def test_add_three_tabs_sidebar_rows(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        for i in range(3):
            tab_widget.add_tab(_make_page(), "G1", f"Tab {i}")
        # 1 个分组标题 + 3 个 Tab 项 = 4 行
        assert tab_widget.sidebar.count() == 4

    def test_add_tab_updates_mappings(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        tab_widget.add_tab(_make_page(), "G1", "Tab 0")
        assert len(tab_widget._row_to_stack) == 1
        assert len(tab_widget._stack_to_row) == 1
        assert len(tab_widget._group_rows) == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------
class TestClear:
    """clear 行为契约。"""

    def test_clear_empty_is_noop(self, tab_widget: SidebarTabWidget) -> None:
        """对空状态调用 clear 不报错，且状态保持为空。"""
        tab_widget.clear()
        assert tab_widget.sidebar.count() == 0
        assert tab_widget.stack.count() == 0
        assert tab_widget._row_to_stack == {}
        assert tab_widget._stack_to_row == {}
        assert tab_widget._group_rows == {}

    def test_clear_after_adding(self, tab_widget: SidebarTabWidget) -> None:
        for i in range(3):
            tab_widget.add_tab(_make_page(), "G1", f"Tab {i}")
        tab_widget.clear()
        assert tab_widget.sidebar.count() == 0
        assert tab_widget.stack.count() == 0
        assert tab_widget._row_to_stack == {}
        assert tab_widget._stack_to_row == {}
        assert tab_widget._group_rows == {}

    def test_clear_after_adding_multiple_groups(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        tab_widget.add_tab(_make_page(), "G1", "A")
        tab_widget.add_tab(_make_page(), "G2", "B")
        tab_widget.add_tab(_make_page(), "G3", "C")
        tab_widget.clear()
        assert tab_widget.sidebar.count() == 0
        assert tab_widget.stack.count() == 0
        assert tab_widget._group_rows == {}

    def test_clear_then_add_no_residue(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """clear 后再 add_tab，旧项不残留。"""
        for i in range(3):
            tab_widget.add_tab(_make_page(), "G1", f"Tab {i}")
        tab_widget.clear()
        for i in range(2):
            tab_widget.add_tab(_make_page(), "G2", f"New {i}")

        # Tab 数 == 新增数
        assert tab_widget.count() == 2
        assert tab_widget.stack.count() == 2
        # 1 个新分组标题 + 2 个新 Tab 项 = 3 行
        assert tab_widget.sidebar.count() == 3
        # 映射条目数与新增 Tab 数一致
        assert len(tab_widget._row_to_stack) == 2
        assert len(tab_widget._stack_to_row) == 2
        assert len(tab_widget._group_rows) == 1
        assert "G1" not in tab_widget._group_rows
        assert "G2" in tab_widget._group_rows

    def test_clear_idempotent(self, tab_widget: SidebarTabWidget) -> None:
        """连续多次 clear 不报错。"""
        tab_widget.add_tab(_make_page(), "G1", "Tab 0")
        tab_widget.clear()
        tab_widget.clear()
        tab_widget.clear()
        assert tab_widget.sidebar.count() == 0
        assert tab_widget.stack.count() == 0


# ---------------------------------------------------------------------------
# 可调整宽度（QSplitter）
# ---------------------------------------------------------------------------
class TestResizableSidebar:
    """侧边栏宽度可通过 QSplitter 拖拽调整。"""

    def test_splitter_exists(self, tab_widget: SidebarTabWidget) -> None:
        """SidebarTabWidget 应包含内部 QSplitter。"""
        assert hasattr(tab_widget, "_splitter")
        assert tab_widget._splitter is not None

    def test_sidebar_not_fixed_width(self, tab_widget: SidebarTabWidget) -> None:
        """侧边栏不应使用 setFixedWidth（minimumWidth < maximumWidth）。"""
        sb = tab_widget.sidebar
        # setFixedWidth 会使 minimumWidth == maximumWidth
        assert sb.minimumWidth() < sb.maximumWidth()

    def test_sidebar_minimum_width(self, tab_widget: SidebarTabWidget) -> None:
        """侧边栏最小宽度应为 _SIDEBAR_MIN_WIDTH。"""
        from balcon_batch_tts.gui.widgets.sidebar_tab_widget import (
            _SIDEBAR_MIN_WIDTH,
        )

        assert tab_widget.sidebar.minimumWidth() == _SIDEBAR_MIN_WIDTH

    def test_sidebar_maximum_width(self, tab_widget: SidebarTabWidget) -> None:
        """侧边栏最大宽度应为 _SIDEBAR_MAX_WIDTH。"""
        from balcon_batch_tts.gui.widgets.sidebar_tab_widget import (
            _SIDEBAR_MAX_WIDTH,
        )

        assert tab_widget.sidebar.maximumWidth() == _SIDEBAR_MAX_WIDTH

    def test_splitter_contains_sidebar_and_stack(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """QSplitter 应包含 sidebar 和 stack 两个子部件。"""
        assert tab_widget._splitter.count() == 2
        assert tab_widget._splitter.widget(0) is tab_widget.sidebar
        assert tab_widget._splitter.widget(1) is tab_widget.stack

    def test_splitter_not_collapsible(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """QSplitter 子部件不应可折叠（避免意外隐藏）。"""
        assert tab_widget._splitter.childrenCollapsible() is False

    def test_splitter_sizes_adjustable(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """setSizes 不抛异常且返回 2 个尺寸值。"""
        tab_widget._splitter.setSizes([300, 700])
        sizes = tab_widget._splitter.sizes()
        # 应返回 2 个尺寸值
        assert len(sizes) == 2
