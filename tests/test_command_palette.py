"""CommandPalette 单元测试。

验证命令面板的构造、过滤、键盘导航、执行与关闭行为，覆盖：
1. 列表正确显示所有命令并按 group 分组排序
2. 输入文本过滤（不区分大小写）
3. 键盘 Up/Down 导航（列表与搜索框）
4. Enter 执行选中命令的 handler 并发射 command_triggered 信号
5. Esc 关闭对话框（reject）
6. 空匹配时显示占位文本
7. 列表为空（commands=[]）不崩溃

测试在 offscreen Qt 平台下运行，无需真实显示设备。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from balcon_batch_tts.gui.widgets.command_palette import Command, CommandPalette


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """返回全局 QApplication 单例（offscreen 模式）。"""
    app = QApplication.instance() or QApplication([])
    yield app


def _make_commands() -> list[Command]:
    """构造测试用命令列表（含分组与快捷键）。"""
    return [
        Command(
            id="nav.voice",
            title="跳转到语音与静音",
            group="导航",
            shortcut="Ctrl+1",
            handler=lambda: None,
        ),
        Command(
            id="nav.output",
            title="跳转到输出",
            group="导航",
            shortcut="Ctrl+2",
            handler=lambda: None,
        ),
        Command(
            id="tool.export",
            title="导出配置",
            group="工具",
            handler=lambda: None,
        ),
        Command(
            id="preset.default",
            title="加载默认预设",
            group="预设",
            handler=lambda: None,
        ),
    ]


# ---------------------------------------------------------------------------
# 1. 构造与列表显示
# ---------------------------------------------------------------------------
def test_list_shows_all_commands(qapp: QApplication) -> None:
    """构造后列表项数应等于命令数。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    assert palette.list_widget.count() == len(cmds)


def test_groups_sorted_adjacent(qapp: QApplication) -> None:
    """同组命令应相邻排列（按 group 稳定排序）。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    groups = [
        palette.list_widget.item(i).data(Qt.ItemDataRole.UserRole).group
        for i in range(palette.list_widget.count())
    ]
    # 按 group 排序：导航 < 工具 < 预设，同组保持插入顺序
    assert groups == ["导航", "导航", "工具", "预设"]


def test_initial_state(qapp: QApplication) -> None:
    """初始打开时搜索框为空且选中第一项。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    assert palette.search_box.text() == ""
    assert palette.list_widget.currentRow() == 0


# ---------------------------------------------------------------------------
# 2. 输入文本过滤
# ---------------------------------------------------------------------------
def test_filter_shows_only_matching(qapp: QApplication) -> None:
    """输入「语音」仅显示匹配项。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    palette.search_box.setText("语音")
    visible_cmds = [
        palette.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(palette.list_widget.count())
        if not palette.list_widget.item(i).isHidden()
    ]
    assert len(visible_cmds) == 1
    assert visible_cmds[0].id == "nav.voice"


def test_filter_case_insensitive(qapp: QApplication) -> None:
    """过滤不区分大小写。"""
    cmds = [
        Command(
            id="t.save",
            title="Save File",
            group="文件",
            handler=lambda: None,
        ),
        Command(
            id="t.open",
            title="Open File",
            group="文件",
            handler=lambda: None,
        ),
    ]
    palette = CommandPalette(cmds)
    palette.search_box.setText("save")
    visible = [
        i
        for i in range(palette.list_widget.count())
        if not palette.list_widget.item(i).isHidden()
    ]
    assert len(visible) == 1
    cmd = palette.list_widget.item(visible[0]).data(
        Qt.ItemDataRole.UserRole
    )
    assert cmd.id == "t.save"


# ---------------------------------------------------------------------------
# 3. 键盘导航
# ---------------------------------------------------------------------------
def test_down_selects_next(qapp: QApplication) -> None:
    """列表中按 Down 选中下一项。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    assert palette.list_widget.currentRow() == 0
    QTest.keyClick(palette.list_widget, Qt.Key.Key_Down)
    assert palette.list_widget.currentRow() == 1


def test_up_selects_previous(qapp: QApplication) -> None:
    """列表中按 Up 选中上一项。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    palette.list_widget.setCurrentRow(1)
    QTest.keyClick(palette.list_widget, Qt.Key.Key_Up)
    assert palette.list_widget.currentRow() == 0


def test_up_down_in_search_box(qapp: QApplication) -> None:
    """搜索框中按 Up/Down 也应导航列表。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    assert palette.list_widget.currentRow() == 0
    QTest.keyClick(palette.search_box, Qt.Key.Key_Down)
    assert palette.list_widget.currentRow() == 1
    QTest.keyClick(palette.search_box, Qt.Key.Key_Up)
    assert palette.list_widget.currentRow() == 0


# ---------------------------------------------------------------------------
# 4. Enter 执行选中命令
# ---------------------------------------------------------------------------
def test_enter_executes_handler_and_emits_signal(
    qapp: QApplication,
) -> None:
    """Enter 执行 handler、发射 command_triggered 信号并 accept。"""
    called: list[str] = []
    cmds = [
        Command(
            id="test.cmd",
            title="测试命令",
            group="测试",
            handler=lambda: called.append("executed"),
        ),
    ]
    palette = CommandPalette(cmds)
    triggered: list[str] = []
    accepted: list[bool] = []
    palette.command_triggered.connect(lambda cid: triggered.append(cid))
    palette.accepted.connect(lambda: accepted.append(True))

    QTest.keyClick(palette.list_widget, Qt.Key.Key_Return)

    assert called == ["executed"]
    assert triggered == ["test.cmd"]
    assert accepted == [True]
    assert palette.result() == QDialog.DialogCode.Accepted


def test_enter_skips_hidden_items(qapp: QApplication) -> None:
    """过滤后 Enter 执行的是第一个可见项的 handler。"""
    called: list[str] = []
    cmds = [
        Command(
            id="a",
            title="苹果",
            group="水果",
            handler=lambda: called.append("a"),
        ),
        Command(
            id="b",
            title="香蕉",
            group="水果",
            handler=lambda: called.append("b"),
        ),
    ]
    palette = CommandPalette(cmds)
    palette.search_box.setText("香蕉")
    QTest.keyClick(palette.list_widget, Qt.Key.Key_Return)
    assert called == ["b"]


# ---------------------------------------------------------------------------
# 5. Esc 关闭对话框
# ---------------------------------------------------------------------------
def test_esc_rejects(qapp: QApplication) -> None:
    """Esc 触发 reject 并发射 rejected 信号。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    rejected: list[bool] = []
    palette.rejected.connect(lambda: rejected.append(True))

    QTest.keyClick(palette.list_widget, Qt.Key.Key_Escape)

    assert rejected == [True]
    assert palette.result() == QDialog.DialogCode.Rejected


# ---------------------------------------------------------------------------
# 6. 空匹配占位
# ---------------------------------------------------------------------------
def test_empty_match_shows_placeholder(qapp: QApplication) -> None:
    """无匹配时显示占位标签并隐藏列表。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    palette.show()
    QApplication.processEvents()
    # 初始：列表可见，占位隐藏
    assert palette.list_widget.isVisible()
    assert not palette.placeholder_label.isVisible()
    # 过滤无匹配
    palette.search_box.setText("xyz不存在")
    assert not palette.list_widget.isVisible()
    assert palette.placeholder_label.isVisible()


def test_rematch_restores_list(qapp: QApplication) -> None:
    """从无匹配恢复到有匹配时列表重新显示。"""
    cmds = _make_commands()
    palette = CommandPalette(cmds)
    palette.show()
    QApplication.processEvents()
    palette.search_box.setText("xyz不存在")
    assert palette.placeholder_label.isVisible()
    # 清空搜索框恢复全部
    palette.search_box.clear()
    assert palette.list_widget.isVisible()
    assert not palette.placeholder_label.isVisible()


# ---------------------------------------------------------------------------
# 7. 空命令列表不崩溃
# ---------------------------------------------------------------------------
def test_empty_commands_no_crash(qapp: QApplication) -> None:
    """commands=[] 时构造不崩溃且显示占位。"""
    palette = CommandPalette([])
    assert palette.list_widget.count() == 0
    palette.show()
    QApplication.processEvents()
    assert palette.placeholder_label.isVisible()


def test_empty_commands_enter_no_crash(qapp: QApplication) -> None:
    """空列表时按 Enter 不崩溃也不 accept。"""
    palette = CommandPalette([])
    accepted: list[bool] = []
    palette.accepted.connect(lambda: accepted.append(True))
    QTest.keyClick(palette.list_widget, Qt.Key.Key_Return)
    assert accepted == []


def test_empty_commands_esc_rejects(qapp: QApplication) -> None:
    """空列表时按 Esc 仍可正常 reject。"""
    palette = CommandPalette([])
    rejected: list[bool] = []
    palette.rejected.connect(lambda: rejected.append(True))
    QTest.keyClick(palette.list_widget, Qt.Key.Key_Escape)
    assert rejected == [True]
