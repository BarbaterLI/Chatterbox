"""SidebarTabWidget 分组折叠（T-B1）与搜索过滤（T-B2）单元测试。

验证分组标题点击折叠/展开、``set_collapsed_groups`` / ``get_collapsed_groups``
接口、搜索框模糊过滤、组内全空时分组标题隐藏、清空恢复、折叠与搜索协同、
以及 150ms 防抖定时器等行为契约。

测试在 offscreen Qt 平台下运行，无需真实显示设备。使用 ``QTest.qWait``
驱动事件循环以验证防抖定时器的触发时机（不依赖 pytest-qt 的 ``qtbot``）。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6.QtWidgets 之前设置 offscreen 平台插件
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from balcon_batch_tts.gui.widgets.sidebar_tab_widget import (
    _COLLAPSED_PREFIX,
    _EXPANDED_PREFIX,
    _GROUP_HEADER_ROLE,
    _GROUP_NAME_ROLE,
    _TAB_TITLE_ROLE,
    SidebarTabWidget,
)


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


def _populate(widget: SidebarTabWidget) -> SidebarTabWidget:
    """构造带 3 个分组的 SidebarTabWidget。

    - ``输入输出``: 「输入文件」「输出路径」(desc 含「语音」)
    - ``语音音频``: 「语音与静音」「音量控制」
    - ``字幕歌词``: 「SRT 字幕」「LRC 歌词」
    """
    widget.add_tab(
        _make_page(), "输入输出", "输入文件", description="拖入或选择输入文件"
    )
    widget.add_tab(
        _make_page(), "输入输出", "输出路径", description="设置语音输出目录"
    )
    widget.add_tab(
        _make_page(), "语音音频", "语音与静音", description="语音名称与静音控制"
    )
    widget.add_tab(
        _make_page(), "语音音频", "音量控制", description="音量与语速"
    )
    widget.add_tab(
        _make_page(), "字幕歌词", "SRT 字幕", description="SRT 字幕处理"
    )
    widget.add_tab(
        _make_page(), "字幕歌词", "LRC 歌词", description="LRC 歌词处理"
    )
    return widget


def _find_tab_row(widget: SidebarTabWidget, title: str) -> int:
    """返回标题为 ``title`` 的 Tab 项行号；未找到时返回 -1。"""
    for row in range(widget.sidebar.count()):
        item = widget.sidebar.item(row)
        if item is None or item.data(_GROUP_HEADER_ROLE):
            continue
        if item.data(_TAB_TITLE_ROLE) == title:
            return row
    return -1


def _group_hidden_items(widget: SidebarTabWidget, group: str) -> list[int]:
    """返回指定分组中被隐藏的 Tab 项行号列表。"""
    result: list[int] = []
    for row in range(widget.sidebar.count()):
        item = widget.sidebar.item(row)
        if item is None or item.data(_GROUP_HEADER_ROLE):
            continue
        if item.data(_GROUP_NAME_ROLE) == group and item.isHidden():
            result.append(row)
    return result


# ---------------------------------------------------------------------------
# 分组标题前缀
# ---------------------------------------------------------------------------
class TestHeaderPrefix:
    """分组标题前缀字符契约（▼ 展开 / ▶ 折叠）。"""

    def test_default_expanded_prefix(self, tab_widget: SidebarTabWidget) -> None:
        tab_widget.add_tab(_make_page(), "G1", "Tab 0")
        header = tab_widget.sidebar.item(0)
        assert header is not None
        assert header.text().startswith(_EXPANDED_PREFIX)
        assert not header.text().startswith(_COLLAPSED_PREFIX)

    def test_toggle_changes_prefix_to_collapsed(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        tab_widget.add_tab(_make_page(), "G1", "Tab 0")
        tab_widget._toggle_group(0)
        header = tab_widget.sidebar.item(0)
        assert header is not None
        assert header.text().startswith(_COLLAPSED_PREFIX)

    def test_toggle_back_restores_expanded_prefix(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        tab_widget.add_tab(_make_page(), "G1", "Tab 0")
        tab_widget._toggle_group(0)  # 折叠
        tab_widget._toggle_group(0)  # 展开
        header = tab_widget.sidebar.item(0)
        assert header is not None
        assert header.text().startswith(_EXPANDED_PREFIX)


# ---------------------------------------------------------------------------
# 分组标题项点击切换折叠（T-B1）
# ---------------------------------------------------------------------------
class TestToggleCollapse:
    """点击分组标题项切换折叠状态：折叠后组内 Tab isHidden()=True，展开后 False。"""

    def test_collapse_hides_group_items(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        g2_row = tab_widget._group_rows["语音音频"]
        # 折叠前：组内项均可见
        assert _group_hidden_items(tab_widget, "语音音频") == []
        tab_widget._toggle_group(g2_row)
        # 折叠后：组内 Tab 项 isHidden() == True
        assert tab_widget.sidebar.item(g2_row).text().startswith(
            _COLLAPSED_PREFIX
        )
        for row in range(tab_widget.sidebar.count()):
            item = tab_widget.sidebar.item(row)
            if (
                item is None
                or item.data(_GROUP_HEADER_ROLE)
                or item.data(_GROUP_NAME_ROLE) != "语音音频"
            ):
                continue
            assert item.isHidden(), f"row {row} 应被隐藏"

    def test_expand_restores_group_items(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        g2_row = tab_widget._group_rows["语音音频"]
        tab_widget._toggle_group(g2_row)  # 折叠
        tab_widget._toggle_group(g2_row)  # 展开
        assert tab_widget.sidebar.item(g2_row).text().startswith(
            _EXPANDED_PREFIX
        )
        for row in range(tab_widget.sidebar.count()):
            item = tab_widget.sidebar.item(row)
            if (
                item is None
                or item.data(_GROUP_HEADER_ROLE)
                or item.data(_GROUP_NAME_ROLE) != "语音音频"
            ):
                continue
            assert not item.isHidden(), f"row {row} 应可见"

    def test_collapse_one_group_does_not_affect_others(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget._toggle_group(tab_widget._group_rows["语音音频"])
        # 其他分组的项保持可见
        assert _group_hidden_items(tab_widget, "输入输出") == []
        assert _group_hidden_items(tab_widget, "字幕歌词") == []

    def test_group_header_pressed_signal_toggles(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """groupHeaderPressed 信号应触发 _toggle_group（验证信号连接）。"""
        _populate(tab_widget)
        g2_row = tab_widget._group_rows["语音音频"]
        # 模拟列表发射 groupHeaderPressed 信号
        tab_widget.sidebar.groupHeaderPressed.emit(g2_row)
        assert tab_widget.sidebar.item(g2_row).text().startswith(
            _COLLAPSED_PREFIX
        )
        assert _group_hidden_items(tab_widget, "语音音频")

    def test_toggle_on_non_header_row_is_noop(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """对非分组标题行调用 _toggle_group 不应改变任何状态。"""
        _populate(tab_widget)
        tab_row = _find_tab_row(tab_widget, "语音与静音")
        before = tab_widget.get_collapsed_groups()
        tab_widget._toggle_group(tab_row)
        assert tab_widget.get_collapsed_groups() == before


# ---------------------------------------------------------------------------
# set / get_collapsed_groups 接口（T-B1.3）
# ---------------------------------------------------------------------------
class TestCollapsedGroupsAPI:
    """set_collapsed_groups / get_collapsed_groups 接口契约。"""

    def test_set_and_get_multiple_groups(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["语音音频", "字幕歌词"])
        assert set(tab_widget.get_collapsed_groups()) == {
            "语音音频",
            "字幕歌词",
        }

    def test_set_empty_collapses_none(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["语音音频"])
        assert tab_widget.get_collapsed_groups() == ["语音音频"]
        tab_widget.set_collapsed_groups([])
        assert tab_widget.get_collapsed_groups() == []

    def test_set_collapsed_hides_only_target_group_items(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["输入输出"])
        # 输入输出 组内项隐藏
        assert _group_hidden_items(tab_widget, "输入输出")
        # 其他分组项可见
        assert _group_hidden_items(tab_widget, "语音音频") == []
        assert _group_hidden_items(tab_widget, "字幕歌词") == []

    def test_set_collapsed_overwrites_previous_state(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["输入输出", "语音音频"])
        tab_widget.set_collapsed_groups(["字幕歌词"])
        assert set(tab_widget.get_collapsed_groups()) == {"字幕歌词"}

    def test_get_collapsed_groups_empty_when_all_expanded(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        assert tab_widget.get_collapsed_groups() == []

    def test_set_collapsed_unknown_group_ignored(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """传入不存在的分组名不应报错，也不影响已知分组。"""
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["不存在的分组", "语音音频"])
        assert "语音音频" in tab_widget.get_collapsed_groups()
        assert "不存在的分组" not in tab_widget.get_collapsed_groups()


# ---------------------------------------------------------------------------
# 搜索过滤（T-B2）
# ---------------------------------------------------------------------------
class TestSearchFilter:
    """搜索框输入文本过滤 Tab 项契约。"""

    def test_filter_shows_only_matching_items(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget._apply_filter("语音")
        # 「语音与静音」标题匹配、「输出路径」描述含「语音」 → 可见
        assert not tab_widget.sidebar.item(
            _find_tab_row(tab_widget, "语音与静音")
        ).isHidden()
        assert not tab_widget.sidebar.item(
            _find_tab_row(tab_widget, "输出路径")
        ).isHidden()
        # 「输入文件」「音量控制」「SRT 字幕」「LRC 歌词」 → 隐藏
        for title in ("输入文件", "音量控制", "SRT 字幕", "LRC 歌词"):
            assert tab_widget.sidebar.item(
                _find_tab_row(tab_widget, title)
            ).isHidden(), f"{title} 应被隐藏"

    def test_filter_hides_header_when_all_items_filtered(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """组内全部隐藏时分组标题一并隐藏。"""
        _populate(tab_widget)
        tab_widget._apply_filter("SRT")
        # 仅「SRT 字幕」匹配，位于「字幕歌词」组 → 该组标题可见
        assert not tab_widget.sidebar.item(
            tab_widget._group_rows["字幕歌词"]
        ).isHidden()
        # 其他分组无匹配 → 标题隐藏
        assert tab_widget.sidebar.item(
            tab_widget._group_rows["输入输出"]
        ).isHidden()
        assert tab_widget.sidebar.item(
            tab_widget._group_rows["语音音频"]
        ).isHidden()

    def test_filter_case_insensitive(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget._apply_filter("srt")
        assert not tab_widget.sidebar.item(
            _find_tab_row(tab_widget, "SRT 字幕")
        ).isHidden()
        tab_widget._apply_filter("SRT")
        assert not tab_widget.sidebar.item(
            _find_tab_row(tab_widget, "SRT 字幕")
        ).isHidden()

    def test_filter_matches_description(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        # 「输出路径」描述为「设置语音输出目录」，标题不含「语音」但描述含
        tab_widget._apply_filter("输出目录")
        assert not tab_widget.sidebar.item(
            _find_tab_row(tab_widget, "输出路径")
        ).isHidden()

    def test_clear_filter_restores_all_visible(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_widget._apply_filter("语音")
        tab_widget._apply_filter("")
        # 全部项可见（含分组标题）
        for row in range(tab_widget.sidebar.count()):
            item = tab_widget.sidebar.item(row)
            assert not item.isHidden(), f"row {row} 清空后应可见"

    def test_clear_filter_respects_collapse_state(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """清空过滤后，折叠组的内项保持隐藏。"""
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["语音音频"])
        tab_widget._apply_filter("语音")
        tab_widget._apply_filter("")
        # 折叠组内项保持隐藏
        for row in range(tab_widget.sidebar.count()):
            item = tab_widget.sidebar.item(row)
            if (
                item is None
                or item.data(_GROUP_HEADER_ROLE)
                or item.data(_GROUP_NAME_ROLE) != "语音音频"
            ):
                continue
            assert item.isHidden(), "折叠组内项应保持隐藏"
        # 展开组内项恢复可见
        for row in range(tab_widget.sidebar.count()):
            item = tab_widget.sidebar.item(row)
            if (
                item is None
                or item.data(_GROUP_HEADER_ROLE)
                or item.data(_GROUP_NAME_ROLE) == "语音音频"
            ):
                continue
            assert not item.isHidden(), "展开组内项应可见"


# ---------------------------------------------------------------------------
# 搜索与折叠状态协同
# ---------------------------------------------------------------------------
class TestSearchCollapseInteraction:
    """搜索过滤与折叠状态协同契约。"""

    def test_collapsed_group_items_stay_hidden_even_if_match(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """折叠的组即使有匹配项也不展开（保持折叠，仅显示分组标题）。"""
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["语音音频"])
        tab_widget._apply_filter("语音")
        # 折叠组内「语音与静音」虽匹配但保持隐藏
        voice_row = _find_tab_row(tab_widget, "语音与静音")
        assert tab_widget.sidebar.item(voice_row).isHidden()
        # 但分组标题可见（组内有匹配）
        assert not tab_widget.sidebar.item(
            tab_widget._group_rows["语音音频"]
        ).isHidden()

    def test_filter_does_not_change_collapse_state(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """搜索过滤不应改变折叠状态（仅临时隐藏不匹配项）。"""
        _populate(tab_widget)
        tab_widget.set_collapsed_groups(["语音音频"])
        collapsed_before = tab_widget.get_collapsed_groups()
        tab_widget._apply_filter("语音")
        tab_widget._apply_filter("")
        # 折叠状态未变
        assert tab_widget.get_collapsed_groups() == collapsed_before

    def test_collapse_after_filter_applies(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """在搜索激活时折叠分组应立即生效（折叠+过滤协同）。"""
        _populate(tab_widget)
        tab_widget._apply_filter("语音")
        # 此时「输出路径」可见（匹配）
        out_row = _find_tab_row(tab_widget, "输出路径")
        assert not tab_widget.sidebar.item(out_row).isHidden()
        # 折叠「输入输出」组 → 「输出路径」隐藏
        tab_widget._toggle_group(tab_widget._group_rows["输入输出"])
        assert tab_widget.sidebar.item(out_row).isHidden()
        # 展开 → 恢复可见（仍匹配过滤）
        tab_widget._toggle_group(tab_widget._group_rows["输入输出"])
        assert not tab_widget.sidebar.item(out_row).isHidden()


# ---------------------------------------------------------------------------
# 防抖定时器（T-B2.3）
# ---------------------------------------------------------------------------
class TestDebounce:
    """textChanged → 150ms 防抖定时器 → _apply_filter 契约。"""

    def test_filter_not_applied_immediately(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """输入后不应立即过滤（防抖期内项可见性不变）。"""
        _populate(tab_widget)
        out_row = _find_tab_row(tab_widget, "输出路径")
        edit = tab_widget._search_edit
        edit.setText("SRT")
        # 立即检查：防抖期内过滤未触发，「输出路径」仍可见
        assert not tab_widget.sidebar.item(out_row).isHidden()
        # 防抖定时器处于活动状态
        assert tab_widget._filter_timer.isActive()

    def test_filter_applied_after_debounce(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """防抖定时器触发后过滤生效。"""
        _populate(tab_widget)
        out_row = _find_tab_row(tab_widget, "输出路径")
        srt_row = _find_tab_row(tab_widget, "SRT 字幕")
        edit = tab_widget._search_edit
        edit.setText("SRT")
        # 等待 150ms 防抖 + 少量余量，驱动事件循环
        QTest.qWait(300)
        # 过滤已生效：「SRT 字幕」可见，「输出路径」隐藏
        assert not tab_widget.sidebar.item(srt_row).isHidden()
        assert tab_widget.sidebar.item(out_row).isHidden()
        # 定时器已停止
        assert not tab_widget._filter_timer.isActive()

    def test_continuous_input_resets_timer(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """连续输入重置定时器：中途过滤不触发，最终文本过滤生效。"""
        _populate(tab_widget)
        out_row = _find_tab_row(tab_widget, "输出路径")
        srt_row = _find_tab_row(tab_widget, "SRT 字幕")
        edit = tab_widget._search_edit
        # 快速连续输入 "S" → "SR" → "SRT"
        edit.setText("S")
        QTest.qWait(80)  # 不足 150ms
        edit.setText("SR")
        QTest.qWait(80)  # 不足 150ms（重置定时器）
        edit.setText("SRT")
        # 中途（最后一次输入后 80ms，不足 150ms 防抖）过滤未触发
        QTest.qWait(80)
        assert tab_widget._filter_timer.isActive()  # 定时器仍活动
        # 「输出路径」此时仍可见（过滤未触发）
        assert not tab_widget.sidebar.item(out_row).isHidden()
        # 等待超过 150ms，定时器触发
        QTest.qWait(300)
        assert not tab_widget.sidebar.item(srt_row).isHidden()
        assert tab_widget.sidebar.item(out_row).isHidden()

    def test_clear_text_triggers_debounce(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        """清空搜索框也走防抖：清空后定时器触发，恢复全部显示。"""
        _populate(tab_widget)
        srt_row = _find_tab_row(tab_widget, "SRT 字幕")
        out_row = _find_tab_row(tab_widget, "输出路径")
        edit = tab_widget._search_edit
        # 通过搜索框输入 "SRT"，等待防抖过滤生效
        edit.setText("SRT")
        QTest.qWait(300)
        assert not tab_widget.sidebar.item(srt_row).isHidden()
        assert tab_widget.sidebar.item(out_row).isHidden()
        # 清空搜索框（触发防抖），等待定时器触发
        edit.setText("")
        QTest.qWait(300)
        # 全部恢复可见
        assert not tab_widget.sidebar.item(srt_row).isHidden()
        assert not tab_widget.sidebar.item(out_row).isHidden()


# ---------------------------------------------------------------------------
# 分组标题项不可选中
# ---------------------------------------------------------------------------
class TestHeaderNotSelectable:
    """分组标题项仅 ItemIsEnabled，不可选中。"""

    def test_header_flags_no_selectable(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        header = tab_widget.sidebar.item(tab_widget._group_rows["语音音频"])
        assert header is not None
        flags = header.flags()
        assert flags & Qt.ItemFlag.ItemIsEnabled
        assert not (flags & Qt.ItemFlag.ItemIsSelectable)

    def test_tab_flags_selectable(
        self, tab_widget: SidebarTabWidget
    ) -> None:
        _populate(tab_widget)
        tab_row = _find_tab_row(tab_widget, "语音与静音")
        tab_item = tab_widget.sidebar.item(tab_row)
        assert tab_item is not None
        flags = tab_item.flags()
        assert flags & Qt.ItemFlag.ItemIsEnabled
        assert flags & Qt.ItemFlag.ItemIsSelectable
