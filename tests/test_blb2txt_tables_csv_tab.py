"""Blb2txtTablesCsvTab 单元测试。

验证 :class:`Blb2txtTablesCsvTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、7 个参数控件存在性（1 个 QSpinBox +
6 个 QCheckBox），以及 ``collect_config`` / ``apply_config`` 的往返一致性。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QSpinBox

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_tables_csv_tab import Blb2txtTablesCsvTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# 6 个 CSV flag 的 (字段名, 选项名) 映射，与 Tab 内部声明一致
CSV_FIELDS: list[tuple[str, str]] = [
    ("csv_comma", "--csv-comma"),
    ("csv_semicolon", "--csv-semicolon"),
    ("csv_space", "--csv-space"),
    ("csv_tab", "--csv-tab"),
    ("csv_double_quote", "--csv-double-quote"),
    ("csv_single_quote", "--csv-single-quote"),
]


# ---------------------------------------------------------------------------
# Tab 元信息
# ---------------------------------------------------------------------------
class TestTabMeta:
    """``Blb2txtTablesCsvTab`` 的 classmethod 元信息返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtTablesCsvTab.tab_id() == "blb2txt_tables_csv"

    def test_tab_title(self) -> None:
        assert Blb2txtTablesCsvTab.tab_title() == "表格CSV（blb2txt）"

    def test_tab_group(self) -> None:
        """验收项：``tab_group`` 必须返回 ``"格式选项"``（Task 3 合并）。"""
        assert Blb2txtTablesCsvTab.tab_group() == "格式选项"

    def test_tab_tool(self) -> None:
        """``tab_tool`` 应返回 :attr:`ToolType.BLB2TXT`，而非默认 BALCON。"""
        assert Blb2txtTablesCsvTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_icon_not_none(self, qapp: QApplication) -> None:
        """``tab_icon`` 应返回非 None 的 QIcon（即使 SVG 渲染失败也是 QIcon）。"""
        icon = Blb2txtTablesCsvTab.tab_icon()
        assert icon is not None

    def test_is_abstracttab_subclass(self) -> None:
        from balcon_batch_tts.gui.tabs.base_tab import AbstractTab

        assert issubclass(Blb2txtTablesCsvTab, AbstractTab)


# ---------------------------------------------------------------------------
# 7 个参数控件存在性
# ---------------------------------------------------------------------------
class TestControlsExist:
    """验证 7 个参数对应的控件属性均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtTablesCsvTab:
        return Blb2txtTablesCsvTab()

    def test_extract_tables_spin_exists(self, tab: Blb2txtTablesCsvTab) -> None:
        """``-et`` 对应的 ``extract_tables_spin`` 应为 QSpinBox。"""
        assert isinstance(tab.extract_tables_spin, QSpinBox)

    def test_extract_tables_spin_range(self, tab: Blb2txtTablesCsvTab) -> None:
        """``-et`` QSpinBox 范围应为 0-1。"""
        assert tab.extract_tables_spin.minimum() == 0
        assert tab.extract_tables_spin.maximum() == 1

    @pytest.mark.parametrize(
        "field_name,option",
        CSV_FIELDS,
        ids=[f[0] for f in CSV_FIELDS],
    )
    def test_csv_checkbox_attribute_exists(
        self, tab: Blb2txtTablesCsvTab, field_name: str, option: str
    ) -> None:
        """每个 CSV flag 对应的 ``{field_name}_chk`` 属性应为 QCheckBox。"""
        chk = getattr(tab, f"{field_name}_chk")
        assert isinstance(chk, QCheckBox)

    @pytest.mark.parametrize(
        "field_name,option",
        CSV_FIELDS,
        ids=[f[0] for f in CSV_FIELDS],
    )
    def test_csv_checkbox_label_contains_option(
        self, tab: Blb2txtTablesCsvTab, field_name: str, option: str
    ) -> None:
        """每个 CheckBox 标签应包含完整选项名（如 ``--csv-comma``）。"""
        chk = getattr(tab, f"{field_name}_chk")
        assert option in chk.text()

    def test_has_one_spinbox_and_six_checkboxes(
        self, tab: Blb2txtTablesCsvTab
    ) -> None:
        """Tab 应包含恰好 1 个 QSpinBox 与 6 个 QCheckBox 子控件。"""
        spinboxes = tab.findChildren(QSpinBox)
        checkboxes = tab.findChildren(QCheckBox)
        assert len(spinboxes) == 1
        assert len(checkboxes) == 6


# ---------------------------------------------------------------------------
# 默认状态
# ---------------------------------------------------------------------------
class TestDefaultState:
    """Tab 默认状态：spinbox 为 0，所有 checkbox 未勾选。"""

    def test_default_extract_tables_spin_is_zero(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtTablesCsvTab()
        assert tab.extract_tables_spin.value() == 0

    @pytest.mark.parametrize(
        "field_name,option",
        CSV_FIELDS,
        ids=[f[0] for f in CSV_FIELDS],
    )
    def test_default_csv_checkbox_unchecked(
        self, qapp: QApplication, field_name: str, option: str
    ) -> None:
        tab = Blb2txtTablesCsvTab()
        chk = getattr(tab, f"{field_name}_chk")
        assert not chk.isChecked()


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致
# ---------------------------------------------------------------------------
class TestCollectApplyRoundtrip:
    """``collect_config`` / ``apply_config`` 往返一致性。"""

    def test_collect_default_writes_none_and_false(
        self, qapp: QApplication
    ) -> None:
        """默认状态下 collect_config 应将 extract_tables 写为 None，
        6 个 CSV flag 写为 False。"""
        tab = Blb2txtTablesCsvTab()
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.extract_tables is None
        for field_name, _ in CSV_FIELDS:
            assert getattr(cfg, field_name) is False

    def test_apply_then_collect_roundtrip(self, qapp: QApplication) -> None:
        """apply_config 还原 cfg → 修改控件 → collect_config 写回，应一致。"""
        tab = Blb2txtTablesCsvTab()
        cfg = Blb2txtConfig.create_default()
        cfg.extract_tables = 1
        cfg.csv_comma = True
        cfg.csv_double_quote = True
        tab.apply_config(cfg)
        # 验证控件状态已还原
        assert tab.extract_tables_spin.value() == 1
        assert tab.csv_comma_chk.isChecked()
        assert tab.csv_double_quote_chk.isChecked()
        assert not tab.csv_semicolon_chk.isChecked()
        # collect 回写
        cfg2 = Blb2txtConfig.create_default()
        tab.collect_config(cfg2)
        assert cfg2.extract_tables == 1
        assert cfg2.csv_comma is True
        assert cfg2.csv_double_quote is True
        assert cfg2.csv_semicolon is False

    def test_apply_extract_tables_none_sets_spin_zero(
        self, qapp: QApplication
    ) -> None:
        """cfg.extract_tables 为 None 时 apply 应将 spinbox 置 0。"""
        tab = Blb2txtTablesCsvTab()
        cfg = Blb2txtConfig.create_default()
        cfg.extract_tables = None
        tab.apply_config(cfg)
        assert tab.extract_tables_spin.value() == 0

    def test_apply_all_csv_true_then_collect(
        self, qapp: QApplication
    ) -> None:
        """全部 CSV flag 设为 True 后 apply → collect 应全部为 True。"""
        tab = Blb2txtTablesCsvTab()
        cfg = Blb2txtConfig.create_default()
        for field_name, _ in CSV_FIELDS:
            setattr(cfg, field_name, True)
        tab.apply_config(cfg)
        for field_name, _ in CSV_FIELDS:
            chk = getattr(tab, f"{field_name}_chk")
            assert chk.isChecked()
        cfg2 = Blb2txtConfig.create_default()
        tab.collect_config(cfg2)
        for field_name, _ in CSV_FIELDS:
            assert getattr(cfg2, field_name) is True

    def test_apply_does_not_affect_other_fields(
        self, qapp: QApplication
    ) -> None:
        """apply_config 设置部分字段不应影响其他未设置字段。"""
        tab = Blb2txtTablesCsvTab()
        cfg = Blb2txtConfig.create_default()
        cfg.csv_comma = True
        tab.apply_config(cfg)
        # 其他 5 个 checkbox 应仍为未勾选
        for field_name, _ in CSV_FIELDS:
            if field_name == "csv_comma":
                continue
            chk = getattr(tab, f"{field_name}_chk")
            assert not chk.isChecked()
        # spinbox 应仍为 0
        assert tab.extract_tables_spin.value() == 0


# ---------------------------------------------------------------------------
# 修改控件后 collect_config 写入对应字段
# ---------------------------------------------------------------------------
class TestControlChangesWriteField:
    """修改控件后 collect_config 应将对应字段写为新值。"""

    def test_set_spin_to_one_collects_extract_tables_one(
        self, qapp: QApplication
    ) -> None:
        """spinbox 设为 1 后 collect_config 应将 extract_tables 写为 1。"""
        tab = Blb2txtTablesCsvTab()
        tab.extract_tables_spin.setValue(1)
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.extract_tables == 1

    def test_set_spin_to_zero_collects_extract_tables_none(
        self, qapp: QApplication
    ) -> None:
        """spinbox 设为 0 后 collect_config 应将 extract_tables 写为 None。"""
        tab = Blb2txtTablesCsvTab()
        tab.extract_tables_spin.setValue(1)
        tab.extract_tables_spin.setValue(0)
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.extract_tables is None

    @pytest.mark.parametrize(
        "field_name,option",
        CSV_FIELDS,
        ids=[f[0] for f in CSV_FIELDS],
    )
    def test_check_single_csv_checkbox_sets_field_true(
        self, qapp: QApplication, field_name: str, option: str
    ) -> None:
        """勾选单个 CSV checkbox 后 collect_config 应仅该字段为 True。"""
        tab = Blb2txtTablesCsvTab()
        chk = getattr(tab, f"{field_name}_chk")
        chk.setChecked(True)
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert getattr(cfg, field_name) is True
        for other_field, _ in CSV_FIELDS:
            if other_field != field_name:
                assert getattr(cfg, other_field) is False


# ---------------------------------------------------------------------------
# TabRegistry 自动发现
# ---------------------------------------------------------------------------
class TestRegistryDiscovery:
    """TabRegistry 自动发现验证。"""

    def test_tab_discovered_by_registry(self) -> None:
        """TabRegistry 应自动发现 Blb2txtTablesCsvTab。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        tab_ids = {t.tab_id() for t in tabs}
        assert "blb2txt_tables_csv" in tab_ids

    def test_tab_returns_blb2txt_in_registry(self) -> None:
        """Registry 中本 Tab 的 tab_tool 应为 BLB2TXT，tab_group 为 "格式选项"（Task 3 合并）。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        for t in tabs:
            if t.tab_id() == "blb2txt_tables_csv":
                assert t.tab_tool() is ToolType.BLB2TXT
                assert t.tab_group() == "格式选项"
                return
        pytest.fail("TabRegistry 未发现 blb2txt_tables_csv Tab")
