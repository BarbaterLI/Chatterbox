"""shortcuts_dialog 模块单元测试。

验证 ``ShortcutsDialog`` 的核心行为，包括：
- 按 group 分组展示所有快捷键
- 搜索框模糊过滤（key 或 description 子串匹配，不区分大小写）
- 组内全部隐藏时分组节点也隐藏
- 搜索框清空后恢复全部显示
- 空列表构造不崩溃
- 默认所有分组展开

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import pytest

from balcon_batch_tts.gui.dialogs.shortcuts_dialog import (
    ShortcutItem,
    ShortcutsDialog,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


def _sample_shortcuts() -> list[ShortcutItem]:
    """构造覆盖多分组的样例快捷键列表。"""
    return [
        ShortcutItem("Ctrl+Shift+P", "打开命令面板", "导航"),
        ShortcutItem("Ctrl+P", "快速跳转", "导航"),
        ShortcutItem("Ctrl+O", "打开文件", "文件"),
        ShortcutItem("Ctrl+S", "保存文件", "文件"),
        ShortcutItem("F5", "开始执行", "执行控制"),
        ShortcutItem("Ctrl+Shift+T", "切换主题", "主题"),
    ]


def _visible_children(dialog: ShortcutsDialog) -> dict[str, list[tuple[str, str]]]:
    """收集当前树中可见的分组及其可见子节点 (key, description)。"""
    result: dict[str, list[tuple[str, str]]] = {}
    for i in range(dialog._tree.topLevelItemCount()):
        group_item = dialog._tree.topLevelItem(i)
        if group_item.isHidden():
            continue
        group_name = group_item.text(0)
        children: list[tuple[str, str]] = []
        for j in range(group_item.childCount()):
            child = group_item.child(j)
            if not child.isHidden():
                children.append((child.text(0), child.text(1)))
        result[group_name] = children
    return result


# ---------------------------------------------------------------------------
# 基础构造与分组展示
# ---------------------------------------------------------------------------
class TestShortcutsDialogInit:
    """``ShortcutsDialog`` 初始化与分组展示契约。"""

    def test_groups_displayed_in_tree(self, qapp: QApplication) -> None:
        """树形列表应正确按 group 分组展示所有快捷键。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        # 4 个分组：导航、文件、执行控制、主题
        assert dialog._tree.topLevelItemCount() == 4
        group_names = [
            dialog._tree.topLevelItem(i).text(0)
            for i in range(dialog._tree.topLevelItemCount())
        ]
        assert group_names == ["导航", "文件", "执行控制", "主题"]

    def test_group_children_displayed(self, qapp: QApplication) -> None:
        """每个分组下应正确展示子节点的 key 与 description。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        visible = _visible_children(dialog)
        assert visible["导航"] == [
            ("Ctrl+Shift+P", "打开命令面板"),
            ("Ctrl+P", "快速跳转"),
        ]
        assert visible["文件"] == [
            ("Ctrl+O", "打开文件"),
            ("Ctrl+S", "保存文件"),
        ]
        assert visible["执行控制"] == [("F5", "开始执行")]
        assert visible["主题"] == [("Ctrl+Shift+T", "切换主题")]

    def test_total_items_displayed(self, qapp: QApplication) -> None:
        """所有快捷键项均应展示在树中。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        visible = _visible_children(dialog)
        total = sum(len(items) for items in visible.values())
        assert total == len(shortcuts)

    def test_default_group_used_when_not_specified(
        self, qapp: QApplication
    ) -> None:
        """未指定 group 的项应归入「其他」分组。"""
        shortcuts = [ShortcutItem("Ctrl+Q", "退出")]
        dialog = ShortcutsDialog(shortcuts)
        assert dialog._tree.topLevelItemCount() == 1
        assert dialog._tree.topLevelItem(0).text(0) == "其他"

    def test_column_width_for_key_column(self, qapp: QApplication) -> None:
        """快捷键列宽度应设为 160。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        assert dialog._tree.columnWidth(0) == 160

    def test_header_labels(self, qapp: QApplication) -> None:
        """列头应显示「快捷键」与「说明」。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        assert dialog._tree.headerItem().text(0) == "快捷键"
        assert dialog._tree.headerItem().text(1) == "说明"

    def test_dialog_is_modal(self, qapp: QApplication) -> None:
        """对话框应为模态。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        assert dialog.isModal()

    def test_search_box_placeholder(self, qapp: QApplication) -> None:
        """搜索框占位文本应为「搜索快捷键…」。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        assert dialog._search_box.placeholderText() == "搜索快捷键…"

    def test_close_button_exists(self, qapp: QApplication) -> None:
        """应存在「关闭」按钮。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        assert dialog._close_button.text() == "关闭"


# ---------------------------------------------------------------------------
# 默认展开
# ---------------------------------------------------------------------------
class TestDefaultExpanded:
    """默认所有分组展开契约。"""

    def test_all_groups_expanded_by_default(self, qapp: QApplication) -> None:
        """默认所有分组节点应处于展开状态。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        for i in range(dialog._tree.topLevelItemCount()):
            group_item = dialog._tree.topLevelItem(i)
            assert group_item.isExpanded(), (
                f"分组 '{group_item.text(0)}' 应默认展开"
            )

    def test_single_group_expanded(self, qapp: QApplication) -> None:
        """单分组也应默认展开。"""
        shortcuts = [ShortcutItem("Ctrl+Q", "退出", "其他")]
        dialog = ShortcutsDialog(shortcuts)
        assert dialog._tree.topLevelItem(0).isExpanded()


# ---------------------------------------------------------------------------
# 搜索过滤
# ---------------------------------------------------------------------------
class TestSearchFilter:
    """搜索框过滤行为。"""

    def test_filter_shows_only_matches(self, qapp: QApplication) -> None:
        """输入「命令」仅显示匹配项。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("命令")
        visible = _visible_children(dialog)
        # 仅「导航」分组的「打开命令面板」匹配
        assert "导航" in visible
        assert visible["导航"] == [("Ctrl+Shift+P", "打开命令面板")]
        # 其他分组应被隐藏（不在 visible 字典中）
        assert "文件" not in visible
        assert "执行控制" not in visible
        assert "主题" not in visible

    def test_filter_hides_group_when_all_children_hidden(
        self, qapp: QApplication
    ) -> None:
        """组内全部子节点不匹配时，分组节点也应隐藏。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("命令")
        # 「文件」「执行控制」「主题」分组无匹配项，应被隐藏
        for i in range(dialog._tree.topLevelItemCount()):
            group_item = dialog._tree.topLevelItem(i)
            if group_item.text(0) in {"文件", "执行控制", "主题"}:
                assert group_item.isHidden(), (
                    f"分组 '{group_item.text(0)}' 应被隐藏"
                )

    def test_filter_by_key(self, qapp: QApplication) -> None:
        """按快捷键文本过滤应生效。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("F5")
        visible = _visible_children(dialog)
        assert "执行控制" in visible
        assert visible["执行控制"] == [("F5", "开始执行")]

    def test_filter_case_insensitive(self, qapp: QApplication) -> None:
        """过滤应不区分大小写。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("f5")
        visible = _visible_children(dialog)
        assert "执行控制" in visible
        assert visible["执行控制"] == [("F5", "开始执行")]

    def test_filter_description_partial_match(self, qapp: QApplication) -> None:
        """按 description 子串过滤应生效。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("文件")
        visible = _visible_children(dialog)
        # 「文件」分组中两项均含「文件」二字
        assert "文件" in visible
        assert len(visible["文件"]) == 2

    def test_clear_search_restores_all(self, qapp: QApplication) -> None:
        """搜索框清空后应恢复全部显示。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        # 先过滤
        dialog._search_box.setText("命令")
        visible_after_filter = _visible_children(dialog)
        assert len(visible_after_filter) == 1
        # 清空
        dialog._search_box.setText("")
        visible_after_clear = _visible_children(dialog)
        # 应恢复全部 4 个分组
        assert len(visible_after_clear) == 4
        total = sum(len(items) for items in visible_after_clear.values())
        assert total == len(shortcuts)

    def test_no_match_hides_everything(self, qapp: QApplication) -> None:
        """无匹配项时所有分组应隐藏。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("zzz不存在zzz")
        visible = _visible_children(dialog)
        assert visible == {}

    def test_whitespace_only_treated_as_empty(self, qapp: QApplication) -> None:
        """仅含空白字符的搜索文本应等同于空（显示全部）。"""
        shortcuts = _sample_shortcuts()
        dialog = ShortcutsDialog(shortcuts)
        dialog._search_box.setText("   ")
        visible = _visible_children(dialog)
        assert len(visible) == 4


# ---------------------------------------------------------------------------
# 空列表
# ---------------------------------------------------------------------------
class TestEmptyShortcuts:
    """空快捷键列表契约。"""

    def test_empty_list_does_not_crash(self, qapp: QApplication) -> None:
        """空列表构造不应崩溃。"""
        dialog = ShortcutsDialog([])
        assert dialog._tree.topLevelItemCount() == 0

    def test_empty_list_filter_does_not_crash(self, qapp: QApplication) -> None:
        """空列表下过滤不应崩溃。"""
        dialog = ShortcutsDialog([])
        dialog._search_box.setText("任意")
        assert dialog._tree.topLevelItemCount() == 0

    def test_empty_list_clear_does_not_crash(self, qapp: QApplication) -> None:
        """空列表下清空搜索不应崩溃。"""
        dialog = ShortcutsDialog([])
        dialog._search_box.setText("任意")
        dialog._search_box.setText("")
        assert dialog._tree.topLevelItemCount() == 0


# ---------------------------------------------------------------------------
# 分组顺序
# ---------------------------------------------------------------------------
class TestGroupOrder:
    """分组顺序保留契约。"""

    def test_group_order_preserved_by_first_occurrence(
        self, qapp: QApplication
    ) -> None:
        """分组顺序应按首次出现顺序保留。"""
        shortcuts = [
            ShortcutItem("K1", "D1", "C组"),
            ShortcutItem("K2", "D2", "A组"),
            ShortcutItem("K3", "D3", "B组"),
            ShortcutItem("K4", "D4", "C组"),
        ]
        dialog = ShortcutsDialog(shortcuts)
        group_names = [
            dialog._tree.topLevelItem(i).text(0)
            for i in range(dialog._tree.topLevelItemCount())
        ]
        # 顺序应为首次出现顺序：C组、A组、B组
        assert group_names == ["C组", "A组", "B组"]

    def test_items_within_group_preserve_input_order(
        self, qapp: QApplication
    ) -> None:
        """同一分组内的项应保留输入顺序。"""
        shortcuts = [
            ShortcutItem("K1", "D1", "G"),
            ShortcutItem("K2", "D2", "G"),
            ShortcutItem("K3", "D3", "G"),
        ]
        dialog = ShortcutsDialog(shortcuts)
        group_item = dialog._tree.topLevelItem(0)
        keys = [
            group_item.child(j).text(0)
            for j in range(group_item.childCount())
        ]
        assert keys == ["K1", "K2", "K3"]


# ---------------------------------------------------------------------------
# 分组节点属性
# ---------------------------------------------------------------------------
class TestGroupNodeFlags:
    """顶层分组节点属性契约。"""

    def test_group_node_not_selectable(self, qapp: QApplication) -> None:
        """顶层分组节点不可选中。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        for i in range(dialog._tree.topLevelItemCount()):
            group_item = dialog._tree.topLevelItem(i)
            flags = group_item.flags()
            assert not (flags & Qt.ItemIsSelectable), (
                f"分组 '{group_item.text(0)}' 不应可选择"
            )

    def test_group_node_not_editable(self, qapp: QApplication) -> None:
        """顶层分组节点不可编辑。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        for i in range(dialog._tree.topLevelItemCount()):
            group_item = dialog._tree.topLevelItem(i)
            flags = group_item.flags()
            assert not (flags & Qt.ItemIsEditable), (
                f"分组 '{group_item.text(0)}' 不应可编辑"
            )

    def test_group_node_enabled(self, qapp: QApplication) -> None:
        """顶层分组节点应启用（可展开/收起）。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        for i in range(dialog._tree.topLevelItemCount()):
            group_item = dialog._tree.topLevelItem(i)
            flags = group_item.flags()
            assert flags & Qt.ItemIsEnabled

    def test_child_node_selectable(self, qapp: QApplication) -> None:
        """子节点应可选择。"""
        dialog = ShortcutsDialog(_sample_shortcuts())
        group_item = dialog._tree.topLevelItem(0)
        child = group_item.child(0)
        assert child.flags() & Qt.ItemIsSelectable
