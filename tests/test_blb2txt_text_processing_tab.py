"""Blb2txtTextProcessingTab 单元测试。

验证 :class:`Blb2txtTextProcessingTab` 的元信息（tab_id / tab_title /
tab_group / tab_tool）、14 个 QCheckBox 的存在性与标签、collect_config /
apply_config 的往返一致性，以及勾选状态到 cfg 字段的写入。

Task 4e 新增测试：
- 4 个 QGroupBox 语义分组（空白处理 / 括号处理 / OCR 与内容 / 字符转换）
- QScrollArea 包裹内容（避免窗口撑爆）
- 每组内 QCheckBox 数量正确
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QScrollArea,
)

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_text_processing_tab import (
    Blb2txtTextProcessingTab,
)


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# 14 个 flag 的 (字段名, 选项别名) 映射，与 Tab 内部声明一致
EXPECTED_FIELDS: list[tuple[str, str]] = [
    ("remove_spaces", "-rs"),
    ("remove_hyphens", "-rh"),
    ("remove_lines", "-rl"),
    ("remove_multiple", "-rm"),
    ("remove_paragraphs", "-rp"),
    ("remove_square_brackets", "-rsb"),
    ("remove_curly_brackets", "-rcb"),
    ("remove_angle_brackets", "-rab"),
    ("remove_round_brackets", "-rrb"),
    ("remove_comments", "-rc"),
    ("remove_page_numbers", "-rpn"),
    ("ocr_correction", "-ocr"),
    ("lowercase", "-ls"),
    ("ascii_pure", "-ap"),
]


# ---------------------------------------------------------------------------
# Tab 元信息
# ---------------------------------------------------------------------------
class TestTabMetadata:
    """tab_id / tab_title / tab_group / tab_tool / tab_icon 返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtTextProcessingTab.tab_id() == "blb2txt_text_processing"

    def test_tab_title(self) -> None:
        assert Blb2txtTextProcessingTab.tab_title() == "文本处理（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtTextProcessingTab.tab_group() == "文本处理"

    def test_tab_tool(self) -> None:
        assert Blb2txtTextProcessingTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_icon_not_none(self, qapp: QApplication) -> None:
        """tab_icon 应返回 QIcon（非 None）。"""
        icon = Blb2txtTextProcessingTab.tab_icon()
        assert icon is not None

    def test_tab_metadata_are_classmethods(self) -> None:
        """tab_id / tab_title / tab_group / tab_tool 应为 classmethod，
        可通过类对象直接调用（TabRegistry 依赖此契约）。"""
        from balcon_batch_tts.gui.tabs.base_tab import AbstractTab

        # tab_tool 在 AbstractTab 上声明为 classmethod
        assert isinstance(AbstractTab.__dict__["tab_tool"], classmethod)


# ---------------------------------------------------------------------------
# 14 个 QCheckBox 存在性
# ---------------------------------------------------------------------------
class TestCheckboxExistence:
    """14 个 QCheckBox 子控件的存在性与标签。"""

    def test_has_14_checkboxes(self, qapp: QApplication) -> None:
        """Tab 实例应包含恰好 14 个 QCheckBox 子控件。"""
        tab = Blb2txtTextProcessingTab()
        checkboxes = tab.findChildren(QCheckBox)
        assert len(checkboxes) == 14

    @pytest.mark.parametrize(
        "field_name,alias",
        EXPECTED_FIELDS,
        ids=[f[0] for f in EXPECTED_FIELDS],
    )
    def test_checkbox_attribute_exists(
        self, qapp: QApplication, field_name: str, alias: str
    ) -> None:
        """每个字段对应的 ``{field_name}_chk`` 属性应存在且为 QCheckBox。"""
        tab = Blb2txtTextProcessingTab()
        chk = getattr(tab, f"{field_name}_chk")
        assert isinstance(chk, QCheckBox)

    @pytest.mark.parametrize(
        "field_name,alias",
        EXPECTED_FIELDS,
        ids=[f[0] for f in EXPECTED_FIELDS],
    )
    def test_checkbox_label_contains_alias(
        self, qapp: QApplication, field_name: str, alias: str
    ) -> None:
        """每个 CheckBox 标签应包含选项别名（如 ``-rs``）。"""
        tab = Blb2txtTextProcessingTab()
        chk = getattr(tab, f"{field_name}_chk")
        assert alias in chk.text()


# ---------------------------------------------------------------------------
# 默认状态
# ---------------------------------------------------------------------------
class TestDefaultState:
    """Tab 默认状态：所有 checkbox 未勾选。"""

    def test_all_checkboxes_unchecked_by_default(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtTextProcessingTab()
        for field_name, _alias in EXPECTED_FIELDS:
            chk = getattr(tab, f"{field_name}_chk")
            assert not chk.isChecked(), (
                f"{field_name}_chk 默认应为未勾选状态"
            )


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致
# ---------------------------------------------------------------------------
class TestCollectApplyRoundtrip:
    """collect_config / apply_config 往返一致性。"""

    def test_collect_default_writes_all_false(
        self, qapp: QApplication
    ) -> None:
        """默认状态下 collect_config 应将所有 14 个字段写为 False。"""
        tab = Blb2txtTextProcessingTab()
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        for field_name, _alias in EXPECTED_FIELDS:
            assert getattr(cfg, field_name) is False, (
                f"默认 collect_config 应将 {field_name} 写为 False"
            )

    def test_apply_then_collect_roundtrip(
        self, qapp: QApplication
    ) -> None:
        """apply_config 还原 cfg → 修改控件 → collect_config 写回，应一致。"""
        tab = Blb2txtTextProcessingTab()
        cfg = Blb2txtConfig.create_default()
        # 设置部分字段为 True
        cfg.remove_spaces = True
        cfg.ocr_correction = True
        cfg.ascii_pure = True
        tab.apply_config(cfg)
        # 验证控件状态已还原
        assert tab.remove_spaces_chk.isChecked()
        assert tab.ocr_correction_chk.isChecked()
        assert tab.ascii_pure_chk.isChecked()
        assert not tab.remove_hyphens_chk.isChecked()
        # collect 回写
        cfg2 = Blb2txtConfig.create_default()
        tab.collect_config(cfg2)
        assert cfg2.remove_spaces is True
        assert cfg2.ocr_correction is True
        assert cfg2.ascii_pure is True
        assert cfg2.remove_hyphens is False

    def test_apply_all_true_then_collect(
        self, qapp: QApplication
    ) -> None:
        """全部字段设为 True 后 apply → collect 应全部为 True。"""
        tab = Blb2txtTextProcessingTab()
        cfg = Blb2txtConfig.create_default()
        for field_name, _alias in EXPECTED_FIELDS:
            setattr(cfg, field_name, True)
        tab.apply_config(cfg)
        # 验证所有 checkbox 已勾选
        for field_name, _alias in EXPECTED_FIELDS:
            chk = getattr(tab, f"{field_name}_chk")
            assert chk.isChecked(), f"{field_name}_chk 应已勾选"
        # collect 回写
        cfg2 = Blb2txtConfig.create_default()
        tab.collect_config(cfg2)
        for field_name, _alias in EXPECTED_FIELDS:
            assert getattr(cfg2, field_name) is True

    def test_apply_does_not_affect_other_fields(
        self, qapp: QApplication
    ) -> None:
        """apply_config 设置部分字段不应影响其他未设置字段。"""
        tab = Blb2txtTextProcessingTab()
        cfg = Blb2txtConfig.create_default()
        cfg.remove_spaces = True
        tab.apply_config(cfg)
        # 其他 13 个 checkbox 应仍为未勾选
        for field_name, _alias in EXPECTED_FIELDS:
            if field_name == "remove_spaces":
                continue
            chk = getattr(tab, f"{field_name}_chk")
            assert not chk.isChecked(), (
                f"{field_name}_chk 不应被 remove_spaces 的 apply 影响"
            )


# ---------------------------------------------------------------------------
# 勾选某 checkbox 后 collect_config 写入对应字段为 True
# ---------------------------------------------------------------------------
class TestCheckTogglesWriteField:
    """勾选某 checkbox 后 collect_config 应将对应字段写为 True。"""

    @pytest.mark.parametrize(
        "field_name,alias",
        EXPECTED_FIELDS,
        ids=[f[0] for f in EXPECTED_FIELDS],
    )
    def test_check_single_checkbox_sets_field_true(
        self, qapp: QApplication, field_name: str, alias: str
    ) -> None:
        """勾选单个 checkbox 后 collect_config 应仅该字段为 True。"""
        tab = Blb2txtTextProcessingTab()
        chk = getattr(tab, f"{field_name}_chk")
        chk.setChecked(True)
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert getattr(cfg, field_name) is True
        # 其他 13 个字段应仍为 False
        for other_field, _ in EXPECTED_FIELDS:
            if other_field != field_name:
                assert getattr(cfg, other_field) is False, (
                    f"{other_field} 应仍为 False（仅 {field_name} 被勾选）"
                )


# ---------------------------------------------------------------------------
# TabRegistry 自动发现
# ---------------------------------------------------------------------------
class TestRegistryDiscovery:
    """TabRegistry 自动发现验证。"""

    def test_tab_discovered_by_registry(self) -> None:
        """TabRegistry 应自动发现 Blb2txtTextProcessingTab。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        tab_ids = {t.tab_id() for t in tabs}
        assert "blb2txt_text_processing" in tab_ids

    def test_tab_returns_blb2txt_in_registry(self) -> None:
        """Registry 中本 Tab 的 tab_tool 应为 BLB2TXT。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        for t in tabs:
            if t.tab_id() == "blb2txt_text_processing":
                assert t.tab_tool() is ToolType.BLB2TXT
                assert t.tab_group() == "文本处理"
                return
        pytest.fail("TabRegistry 未发现 blb2txt_text_processing Tab")


# ---------------------------------------------------------------------------
# Task 4e: QGroupBox 语义分组与 QScrollArea
# ---------------------------------------------------------------------------
class TestGroupBoxGrouping:
    """验证 14 个 flag 按 4 个 QGroupBox 语义分组。"""

    _EXPECTED_GROUPS: list[tuple[str, list[str]]] = [
        ("空白处理", [
            "remove_spaces", "remove_hyphens", "remove_lines",
            "remove_multiple", "remove_paragraphs",
        ]),
        ("括号处理", [
            "remove_square_brackets", "remove_curly_brackets",
            "remove_angle_brackets", "remove_round_brackets",
        ]),
        ("OCR 与内容", [
            "remove_comments", "remove_page_numbers", "ocr_correction",
        ]),
        ("字符转换", ["lowercase", "ascii_pure"]),
    ]

    def test_has_4_groupboxes(self, qapp: QApplication) -> None:
        """Tab 实例应包含恰好 4 个 QGroupBox 子控件。"""
        tab = Blb2txtTextProcessingTab()
        groups = tab.findChildren(QGroupBox)
        assert len(groups) == 4, f"应有 4 个 QGroupBox，实际 {len(groups)}"

    def test_groupbox_titles_match_expected(self, qapp: QApplication) -> None:
        """4 个 QGroupBox 标题应为 空白处理 / 括号处理 / OCR 与内容 / 字符转换。"""
        tab = Blb2txtTextProcessingTab()
        groups = tab.findChildren(QGroupBox)
        titles = {g.title() for g in groups}
        expected = {g[0] for g in self._EXPECTED_GROUPS}
        assert titles == expected, f"分组标题应为 {expected}，实际 {titles}"

    @pytest.mark.parametrize(
        "group_title,expected_suffixes",
        [(g[0], g[1]) for g in _EXPECTED_GROUPS],
        ids=[g[0] for g in _EXPECTED_GROUPS],
    )
    def test_group_contains_correct_checkboxes(
        self, qapp: QApplication, group_title: str, expected_suffixes: list[str]
    ) -> None:
        """每个 QGroupBox 应包含对应分组的 QCheckBox 子控件。"""
        tab = Blb2txtTextProcessingTab()
        groups = tab.findChildren(QGroupBox)
        target_group = next((g for g in groups if g.title() == group_title), None)
        assert target_group is not None, f"未找到分组 {group_title!r}"

        # 收集该 QGroupBox 内的 QCheckBox 文本
        checkboxes = target_group.findChildren(QCheckBox)
        chk_texts = {chk.text() for chk in checkboxes}

        # 期望的 QCheckBox 文本应包含对应字段的别名
        from balcon_batch_tts.gui.tabs.blb2txt_text_processing_tab import (
            _TEXT_PROCESSING_FIELDS,
        )
        suffix_to_alias = {s: a for s, _f, a, _l in _TEXT_PROCESSING_FIELDS}
        for suffix in expected_suffixes:
            alias = suffix_to_alias[suffix]
            assert any(alias in t for t in chk_texts), (
                f"分组 {group_title!r} 应包含别名 {alias!r} 的 checkbox"
            )

    def test_total_checkboxes_in_groups_equals_14(
        self, qapp: QApplication
    ) -> None:
        """4 个 QGroupBox 内的 QCheckBox 总数应为 14。"""
        tab = Blb2txtTextProcessingTab()
        groups = tab.findChildren(QGroupBox)
        total = sum(len(g.findChildren(QCheckBox)) for g in groups)
        assert total == 14, f"分组内 QCheckBox 总数应为 14，实际 {total}"


class TestScrollArea:
    """验证 QScrollArea 包裹内容（避免参数过多撑爆窗口）。"""

    def test_has_scrollarea(self, qapp: QApplication) -> None:
        """Tab 实例应包含一个 QScrollArea 子控件。"""
        tab = Blb2txtTextProcessingTab()
        scrolls = tab.findChildren(QScrollArea)
        assert len(scrolls) >= 1, "应有至少 1 个 QScrollArea 包裹内容"

    def test_scrollarea_widget_resizable(self, qapp: QApplication) -> None:
        """QScrollArea 应启用 widgetResizable，保证内容自适应宽度。"""
        tab = Blb2txtTextProcessingTab()
        scrolls = tab.findChildren(QScrollArea)
        assert any(s.widgetResizable() for s in scrolls), (
            "QScrollArea 应启用 widgetResizable"
        )

    def test_scrollarea_contains_groupboxes(
        self, qapp: QApplication
    ) -> None:
        """QScrollArea 内应包含 QGroupBox。"""
        tab = Blb2txtTextProcessingTab()
        scrolls = tab.findChildren(QScrollArea)
        assert scrolls, "应有 QScrollArea"
        scroll = scrolls[0]
        content = scroll.widget()
        assert content is not None, "QScrollArea 应有内容 widget"
        groups = content.findChildren(QGroupBox)
        assert len(groups) == 4, (
            f"QScrollArea 内应有 4 个 QGroupBox，实际 {len(groups)}"
        )
