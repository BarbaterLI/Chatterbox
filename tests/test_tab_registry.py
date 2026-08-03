"""TabRegistry 模块单元测试。

验证 :class:`TabRegistry` 的自动发现、按工具过滤与分组行为，
覆盖 Task 13 的验收标准：

- :meth:`TabRegistry.get_tabs_by_tool` 按工具类型过滤 Tab 集合。
- :meth:`TabRegistry.get_all_tabs_grouped` 增加可选 ``tool`` 参数，
  默认 ``None`` 时返回全部分组（向后兼容）。
- :meth:`TabRegistry.get_all_tabs` 签名与行为完全不变（向后兼容）。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs import TabRegistry


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _refresh_registry(qapp: QApplication) -> None:
    """每个测试前强制重新扫描，确保 ``_tabs`` 缓存反映最新模块状态。

    ``qapp`` 依赖确保 PySide6 已初始化（tab 模块在导入时即需 QWidget）。
    """
    TabRegistry.refresh()


# ---------------------------------------------------------------------------
# get_all_tabs 向后兼容
# ---------------------------------------------------------------------------
class TestGetAllTabsBackwardCompat:
    """``get_all_tabs`` 签名与行为完全不变（向后兼容）。"""

    def test_get_all_tabs_no_arguments(self) -> None:
        """``get_all_tabs`` 不接受参数，仍可无参调用。"""
        # 不传参数应正常工作（向后兼容的核心要求）
        tabs = TabRegistry.get_all_tabs()
        assert isinstance(tabs, list)
        assert len(tabs) > 0, "应至少发现一个 Tab"

    def test_get_all_tabs_returns_sorted_by_title(self) -> None:
        """``get_all_tabs`` 返回结果按 ``tab_title`` 排序。"""
        tabs = TabRegistry.get_all_tabs()
        titles = [t.tab_title() for t in tabs]
        assert titles == sorted(titles), "get_all_tabs 应按 tab_title 排序"

    def test_get_all_tabs_returns_copy(self) -> None:
        """``get_all_tabs`` 返回列表副本，外部修改不影响内部缓存。"""
        tabs1 = TabRegistry.get_all_tabs()
        tabs1.append(tabs1[0])  # type: ignore[arg-type]
        tabs2 = TabRegistry.get_all_tabs()
        assert len(tabs1) != len(tabs2), "外部 append 不应污染内部缓存"

    def test_get_all_tabs_count_includes_blb2txt(self) -> None:
        """``get_all_tabs`` 应返回 12 个 balcon Tab + 已创建的 blb2txt Tab。

        Task 4b 合并 SilenceTab 入 VoiceTab，balcon 数量从 13 减至 12，
        blb2txt 数量随任务推进递增（当前至少 1 个）。
        """
        tabs = TabRegistry.get_all_tabs()
        balcon_tabs = [t for t in tabs if t.tab_tool() is ToolType.BALCON]
        blb2txt_tabs = [t for t in tabs if t.tab_tool() is ToolType.BLB2TXT]
        assert len(balcon_tabs) == 12, (
            f"应发现 12 个 balcon Tab，实际 {len(balcon_tabs)}"
        )
        assert len(blb2txt_tabs) >= 1, (
            f"应至少发现 1 个 blb2txt Tab（Task 15+），实际 {len(blb2txt_tabs)}"
        )


# ---------------------------------------------------------------------------
# get_tabs_by_tool 验收标准
# ---------------------------------------------------------------------------
class TestGetTabsByTool:
    """``get_tabs_by_tool`` 按工具类型过滤。"""

    def test_balcon_returns_12_tabs(self) -> None:
        """``get_tabs_by_tool(ToolType.BALCON)`` 返回 12 个 balcon Tab。

        Task 4b 合并 SilenceTab 入 VoiceTab，从 13 减至 12。
        """
        tabs = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        assert len(tabs) == 12, (
            f"应返回 12 个 balcon Tab，实际 {len(tabs)}"
        )

    def test_blb2txt_returns_created_tabs(self) -> None:
        """``get_tabs_by_tool(ToolType.BLB2TXT)`` 返回已创建的 blb2txt Tab。

        Task 15+ 起逐步创建 blb2txt Tab，返回列表应非空，
        且每个 Tab 的 ``tab_tool()`` 均为 :attr:`ToolType.BLB2TXT`。
        """
        tabs = TabRegistry.get_tabs_by_tool(ToolType.BLB2TXT)
        assert len(tabs) >= 1, (
            f"应至少返回 1 个 blb2txt Tab（Task 15+），实际 {len(tabs)}"
        )
        for tab_cls in tabs:
            assert tab_cls.tab_tool() is ToolType.BLB2TXT, (
                f"{tab_cls.__name__}.tab_tool() 应返回 ToolType.BLB2TXT"
            )

    def test_balcon_plus_blb2txt_plus_sapi_equals_total(self) -> None:
        """balcon Tab 数 + blb2txt Tab 数 + sapi Tab 数 == ``get_all_tabs`` 总数。"""
        all_tabs = TabRegistry.get_all_tabs()
        balcon_tabs = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        blb2txt_tabs = TabRegistry.get_tabs_by_tool(ToolType.BLB2TXT)
        sapi_tabs = TabRegistry.get_tabs_by_tool(ToolType.SAPI)
        assert (
            len(balcon_tabs) + len(blb2txt_tabs) + len(sapi_tabs)
            == len(all_tabs)
        ), (
            "balcon + blb2txt + sapi Tab 数应等于总 Tab 数；"
            "若有 Tab 未明确归类，需检查 tab_tool() 默认实现"
        )

    def test_balcon_tabs_match_tab_tool(self) -> None:
        """每个 ``get_tabs_by_tool(BALCON)`` 返回的 Tab，其 ``tab_tool()``
        均返回 :attr:`ToolType.BALCON`。"""
        for tab_cls in TabRegistry.get_tabs_by_tool(ToolType.BALCON):
            assert tab_cls.tab_tool() is ToolType.BALCON, (
                f"{tab_cls.__name__}.tab_tool() 应返回 ToolType.BALCON，"
                f"实际返回 {tab_cls.tab_tool()!r}"
            )

    def test_blb2txt_tabs_match_tab_tool(self) -> None:
        """每个 ``get_tabs_by_tool(BLB2TXT)`` 返回的 Tab，其 ``tab_tool()``
        均返回 :attr:`ToolType.BLB2TXT`。"""
        for tab_cls in TabRegistry.get_tabs_by_tool(ToolType.BLB2TXT):
            assert tab_cls.tab_tool() is ToolType.BLB2TXT, (
                f"{tab_cls.__name__}.tab_tool() 应返回 ToolType.BLB2TXT，"
                f"实际返回 {tab_cls.tab_tool()!r}"
            )

    def test_filter_result_subset_of_all_tabs(self) -> None:
        """``get_tabs_by_tool`` 返回集合是 ``get_all_tabs`` 的子集。"""
        all_tabs = TabRegistry.get_all_tabs()
        balcon_tabs = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        all_names = {t.__name__ for t in all_tabs}
        balcon_names = {t.__name__ for t in balcon_tabs}
        assert balcon_names.issubset(all_names), (
            "balcon Tab 应为全部 Tab 的子集"
        )

    def test_filter_preserves_title_order(self) -> None:
        """``get_tabs_by_tool`` 保留 ``tab_title`` 排序顺序。"""
        tabs = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        titles = [t.tab_title() for t in tabs]
        assert titles == sorted(titles), (
            "get_tabs_by_tool 应保留 get_all_tabs 的 tab_title 排序"
        )

    def test_filter_returns_new_list_each_call(self) -> None:
        """``get_tabs_by_tool`` 每次调用返回新列表，互不影响。"""
        tabs1 = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        tabs2 = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        assert tabs1 is not tabs2, "应返回新列表对象"
        assert tabs1 == tabs2, "内容应相等"


# ---------------------------------------------------------------------------
# get_all_tabs_grouped 向后兼容与 tool 过滤
# ---------------------------------------------------------------------------
class TestGetAllTabsGroupedCompat:
    """``get_all_tabs_grouped`` 不带参数的行为完全不变（向后兼容）。"""

    def test_no_arguments_returns_all_groups(self) -> None:
        """不带参数调用返回全部分组（向后兼容）。"""
        grouped = TabRegistry.get_all_tabs_grouped()
        # 不带 tool 参数应返回非空分组字典
        assert isinstance(grouped, dict)
        assert len(grouped) > 0, "至少应有一个非空分组"

    def test_no_arguments_returns_known_group_order(self) -> None:
        """不带参数时分组顺序固定为预定义顺序。"""
        grouped = TabRegistry.get_all_tabs_grouped()
        expected_order = [
            "输入输出", "语音音频", "字幕歌词",
            "文本处理", "格式选项", "高级", "其他",
        ]
        actual_keys = list(grouped.keys())
        # 实际 keys 应为 expected_order 的前缀子序列（空分组被移除）
        for key in actual_keys:
            assert key in expected_order, f"出现未预期分组名 {key!r}"
        # 验证顺序：actual_keys 中相邻元素在 expected_order 中也保持顺序
        expected_idx = [expected_order.index(k) for k in actual_keys]
        assert expected_idx == sorted(expected_idx), (
            "分组顺序应符合预定义：输入输出/语音音频/字幕歌词/"
            "文本处理/格式选项/高级/其他"
        )

    def test_no_arguments_total_equals_get_all_tabs(self) -> None:
        """不带参数时所有分组 Tab 总数等于 ``get_all_tabs`` 长度。"""
        grouped = TabRegistry.get_all_tabs_grouped()
        total = sum(len(tabs) for tabs in grouped.values())
        assert total == len(TabRegistry.get_all_tabs()), (
            "全部分组的 Tab 总数应等于 get_all_tabs 长度"
        )

    def test_no_arguments_empty_groups_removed(self) -> None:
        """不带参数时空分组被移除。"""
        grouped = TabRegistry.get_all_tabs_grouped()
        for name, tabs in grouped.items():
            assert len(tabs) > 0, f"分组 {name!r} 不应为空"


# ---------------------------------------------------------------------------
# get_all_tabs_grouped(tool=...) 过滤
# ---------------------------------------------------------------------------
class TestGetAllTabsGroupedWithTool:
    """``get_all_tabs_grouped(tool=...)`` 按工具过滤后分组。"""

    def test_balcon_grouped_total_matches_filter(self) -> None:
        """``tool=BALCON`` 时所有分组 Tab 总数等于 ``get_tabs_by_tool(BALCON)``。"""
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BALCON)
        total = sum(len(tabs) for tabs in grouped.values())
        expected = len(TabRegistry.get_tabs_by_tool(ToolType.BALCON))
        assert total == expected, (
            f"tool=BALCON 时分组总数 {total} 应等于 get_tabs_by_tool(BALCON) {expected}"
        )

    def test_balcon_grouped_only_contains_balcon_tabs(self) -> None:
        """``tool=BALCON`` 时分组中每个 Tab 的 ``tab_tool()`` 均为 BALCON。"""
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BALCON)
        for name, tabs in grouped.items():
            for tab_cls in tabs:
                assert tab_cls.tab_tool() is ToolType.BALCON, (
                    f"分组 {name!r} 中的 {tab_cls.__name__} 不属于 BALCON"
                )

    def test_blb2txt_grouped_returns_non_empty_after_creation(self) -> None:
        """``tool=BLB2TXT`` 时 blb2txt Tab 已创建，应返回非空分组 dict。

        Task 15+ 起逐步创建 blb2txt Tab，分组结果应非空，
        且每个分组中的 Tab 的 ``tab_tool()`` 均为 :attr:`ToolType.BLB2TXT`。
        """
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BLB2TXT)
        assert len(grouped) > 0, (
            f"blb2txt Tab 已创建，应返回非空 dict，实际 {grouped}"
        )
        for name, tabs in grouped.items():
            assert len(tabs) > 0, f"分组 {name!r} 不应为空"
            for tab_cls in tabs:
                assert tab_cls.tab_tool() is ToolType.BLB2TXT, (
                    f"分组 {name!r} 中的 {tab_cls.__name__} 不属于 BLB2TXT"
                )

    def test_blb2txt_grouped_has_four_groups(self) -> None:
        """``tool=BLB2TXT`` 时 blb2txt 分组数应为 4（输入输出/文本处理/格式选项/高级）。

        Task 3 将 blb2txt 分组从 7 个合并为 4 个：
        - 输入输出（Blb2txtInputTab + Blb2txtOutputTab）
        - 文本处理（Blb2txtSplitTab + Blb2txtTextProcessingTab）
        - 格式选项（Blb2txtDictNotesTab + Blb2txtTablesCsvTab + Blb2txtEmlTab）
        - 高级（Blb2txtArchivesImagesTab + Blb2txtMiscTab）
        """
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BLB2TXT)
        assert len(grouped) == 4, (
            f"blb2txt 应有 4 个分组，实际 {len(grouped)}: {list(grouped.keys())}"
        )
        expected_groups = {"输入输出", "文本处理", "格式选项", "高级"}
        actual_groups = set(grouped.keys())
        assert actual_groups == expected_groups, (
            f"blb2txt 分组名应为 {expected_groups}，实际 {actual_groups}"
        )

    def test_blb2txt_grouped_preserves_group_order(self) -> None:
        """``tool=BLB2TXT`` 时分组顺序为 输入输出/文本处理/格式选项/高级。"""
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BLB2TXT)
        expected_order = ["输入输出", "文本处理", "格式选项", "高级"]
        actual_keys = list(grouped.keys())
        assert actual_keys == expected_order, (
            f"blb2txt 分组顺序应为 {expected_order}，实际 {actual_keys}"
        )

    def test_tool_none_equals_no_arguments(self) -> None:
        """``tool=None`` 与不带参数行为一致（向后兼容）。"""
        grouped_none = TabRegistry.get_all_tabs_grouped(tool=None)
        grouped_no_arg = TabRegistry.get_all_tabs_grouped()
        # 字典内容（键 + 列表元素）应相等
        assert grouped_none.keys() == grouped_no_arg.keys(), (
            "tool=None 与不带参数应返回相同分组键"
        )
        for key in grouped_none:
            assert grouped_none[key] == grouped_no_arg[key], (
                f"分组 {key!r} 内容应一致"
            )

    def test_balcon_grouped_preserves_group_order(self) -> None:
        """``tool=BALCON`` 时分组顺序仍为预定义顺序。"""
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BALCON)
        expected_order = [
            "输入输出", "语音音频", "字幕歌词",
            "文本处理", "格式选项", "高级", "其他",
        ]
        actual_keys = list(grouped.keys())
        for key in actual_keys:
            assert key in expected_order, f"未预期分组 {key!r}"
        expected_idx = [expected_order.index(k) for k in actual_keys]
        assert expected_idx == sorted(expected_idx), (
            "tool 过滤后分组顺序应保持预定义顺序"
        )

    def test_balcon_grouped_no_empty_groups(self) -> None:
        """``tool=BALCON`` 时空分组被移除。"""
        grouped = TabRegistry.get_all_tabs_grouped(tool=ToolType.BALCON)
        for name, tabs in grouped.items():
            assert len(tabs) > 0, f"分组 {name!r} 不应为空"


# ---------------------------------------------------------------------------
# 综合：每个 Tab 的 tab_tool 与 get_tabs_by_tool 一致性
# ---------------------------------------------------------------------------
class TestTabToolConsistency:
    """每个 Tab 的 ``tab_tool()`` 返回值与 ``get_tabs_by_tool`` 过滤一致。"""

    def test_each_tab_appears_in_exactly_one_tool_filter(self) -> None:
        """每个 Tab 在 BALCON / BLB2TXT / SAPI 之一出现，且仅出现一次。"""
        all_tabs = TabRegistry.get_all_tabs()
        balcon_tabs = TabRegistry.get_tabs_by_tool(ToolType.BALCON)
        blb2txt_tabs = TabRegistry.get_tabs_by_tool(ToolType.BLB2TXT)
        sapi_tabs = TabRegistry.get_tabs_by_tool(ToolType.SAPI)

        balcon_names = {t.__name__ for t in balcon_tabs}
        blb2txt_names = {t.__name__ for t in blb2txt_tabs}
        sapi_names = {t.__name__ for t in sapi_tabs}
        all_names = {t.__name__ for t in all_tabs}

        # 并集等于全集
        assert balcon_names | blb2txt_names | sapi_names == all_names, (
            "每个 Tab 应至少出现在一个工具过滤结果中"
        )
        # 交集为空（每个 Tab 只属于一个工具）
        assert balcon_names & blb2txt_names == set(), (
            "Tab 不应同时出现在 BALCON 和 BLB2TXT 过滤结果中"
        )
        assert balcon_names & sapi_names == set(), (
            "Tab 不应同时出现在 BALCON 和 SAPI 过滤结果中"
        )
        assert blb2txt_names & sapi_names == set(), (
            "Tab 不应同时出现在 BLB2TXT 和 SAPI 过滤结果中"
        )

    def test_each_tab_tab_tool_matches_its_filter_membership(self) -> None:
        """每个 Tab 的 ``tab_tool()`` 返回值决定其在过滤结果中的归属。"""
        balcon_names = {t.__name__ for t in TabRegistry.get_tabs_by_tool(ToolType.BALCON)}
        blb2txt_names = {t.__name__ for t in TabRegistry.get_tabs_by_tool(ToolType.BLB2TXT)}
        sapi_names = {t.__name__ for t in TabRegistry.get_tabs_by_tool(ToolType.SAPI)}

        for tab_cls in TabRegistry.get_all_tabs():
            tool = tab_cls.tab_tool()
            if tool is ToolType.BALCON:
                assert tab_cls.__name__ in balcon_names, (
                    f"{tab_cls.__name__}.tab_tool() 返回 BALCON 但未出现在 BALCON 过滤结果"
                )
            elif tool is ToolType.BLB2TXT:
                assert tab_cls.__name__ in blb2txt_names, (
                    f"{tab_cls.__name__}.tab_tool() 返回 BLB2TXT 但未出现在 BLB2TXT 过滤结果"
                )
            elif tool is ToolType.SAPI:
                assert tab_cls.__name__ in sapi_names, (
                    f"{tab_cls.__name__}.tab_tool() 返回 SAPI 但未出现在 SAPI 过滤结果"
                )
            else:
                pytest.fail(f"未预期的 ToolType: {tool!r}")
