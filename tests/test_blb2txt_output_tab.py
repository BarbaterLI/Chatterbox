"""Blb2txtOutputTab 单元测试。

验证 :class:`Blb2txtOutputTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、12 个参数控件存在性，以及
``collect_config`` / ``apply_config`` 往返一致性。

Task 4 新增：
- 3 个 QGroupBox 分组（输出路径 / 覆盖模式 / 编码格式）
- 4 个 checkbox 2x2 QGridLayout 紧凑排布
- 浏览按钮使用 QToolButton（而非 QPushButton）
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QApplication,
    QGridLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QToolButton,
)

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_output_tab import Blb2txtOutputTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 元信息测试
# ---------------------------------------------------------------------------
class TestTabMetadata:
    """``Blb2txtOutputTab`` 的元信息方法返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtOutputTab.tab_id() == "blb2txt_output"

    def test_tab_title(self) -> None:
        assert Blb2txtOutputTab.tab_title() == "输出（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtOutputTab.tab_group() == "输入输出"

    def test_tab_tool(self) -> None:
        assert Blb2txtOutputTab.tab_tool() is ToolType.BLB2TXT


# ---------------------------------------------------------------------------
# 控件存在性测试
# ---------------------------------------------------------------------------
class TestWidgetsExist:
    """验证 12 个参数控件均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtOutputTab:
        return Blb2txtOutputTab()

    def test_v_widget_is_lineedit(self, tab: Blb2txtOutputTab) -> None:
        """-v (v_output) 控件为 QLineEdit。"""
        assert isinstance(tab.v_edit, QLineEdit)

    def test_p_widget_is_lineedit(self, tab: Blb2txtOutputTab) -> None:
        """-p (p_prefix) 控件为 QLineEdit。"""
        assert isinstance(tab.p_edit, QLineEdit)

    def test_ext_widget_is_lineedit(self, tab: Blb2txtOutputTab) -> None:
        """-ext (ext_extension) 控件为 QLineEdit。"""
        assert isinstance(tab.ext_edit, QLineEdit)

    def test_out_widget_is_lineedit(self, tab: Blb2txtOutputTab) -> None:
        """-out (out_file) 控件为 QLineEdit。"""
        assert isinstance(tab.out_edit, QLineEdit)

    def test_o_widget_is_checkbox(self, tab: Blb2txtOutputTab) -> None:
        """-o (o_overwrite) 控件为 QCheckBox。"""
        assert isinstance(tab.o_check, QCheckBox)

    def test_u_widget_is_checkbox(self, tab: Blb2txtOutputTab) -> None:
        """-u (u_subdir) 控件为 QCheckBox。"""
        assert isinstance(tab.u_check, QCheckBox)

    def test_b_widget_is_checkbox(self, tab: Blb2txtOutputTab) -> None:
        """-b (b_backup) 控件为 QCheckBox。"""
        assert isinstance(tab.b_check, QCheckBox)

    def test_a_widget_is_checkbox(self, tab: Blb2txtOutputTab) -> None:
        """-a (a_append) 控件为 QCheckBox。"""
        assert isinstance(tab.a_check, QCheckBox)

    def test_n_widget_is_spinbox(self, tab: Blb2txtOutputTab) -> None:
        """-n (n_naming) 控件为 QSpinBox。"""
        assert isinstance(tab.n_spin, QSpinBox)

    def test_e_widget_is_combobox(self, tab: Blb2txtOutputTab) -> None:
        """-e (e_encoding) 控件为 QComboBox。"""
        assert isinstance(tab.e_combo, QComboBox)

    def test_cf_widget_is_combobox(self, tab: Blb2txtOutputTab) -> None:
        """-cf (cf_console_file) 控件为 QComboBox。"""
        assert isinstance(tab.cf_combo, QComboBox)

    def test_cft_widget_is_combobox(self, tab: Blb2txtOutputTab) -> None:
        """-cft (cft_console_type) 控件为 QComboBox。"""
        assert isinstance(tab.cft_combo, QComboBox)


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致性
# ---------------------------------------------------------------------------
class TestCollectApplyRoundTrip:
    """``collect_config`` 与 ``apply_config`` 的往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtOutputTab:
        return Blb2txtOutputTab()

    def test_default_round_trip(self, tab: Blb2txtOutputTab) -> None:
        """默认值往返：apply 默认 cfg 后 collect 应得到全 None/False 字段。"""
        cfg = Blb2txtConfig.create_default()
        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.v_output is None
        assert out.p_prefix is None
        assert out.ext_extension is None
        assert out.out_file is None
        assert out.o_overwrite is False
        assert out.u_subdir is False
        assert out.b_backup is False
        assert out.a_append is False
        assert out.n_naming is None
        assert out.e_encoding is None
        assert out.cf_console_file is None
        assert out.cft_console_type is None

    def test_full_round_trip(self, tab: Blb2txtOutputTab) -> None:
        """设置全部 12 个字段后往返，应保持一致。"""
        cfg = Blb2txtConfig.create_default()
        cfg.v_output = "/tmp/out"
        cfg.p_prefix = "pre_"
        cfg.ext_extension = "txt"
        cfg.out_file = "/tmp/all.txt"
        cfg.o_overwrite = True
        cfg.u_subdir = True
        cfg.b_backup = True
        cfg.a_append = True
        cfg.n_naming = 2
        cfg.e_encoding = "utf8"
        cfg.cf_console_file = "NO"
        cfg.cft_console_type = "html"

        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)

        assert out.v_output == "/tmp/out"
        assert out.p_prefix == "pre_"
        assert out.ext_extension == "txt"
        assert out.out_file == "/tmp/all.txt"
        assert out.o_overwrite is True
        assert out.u_subdir is True
        assert out.b_backup is True
        assert out.a_append is True
        assert out.n_naming == 2
        assert out.e_encoding == "utf8"
        assert out.cf_console_file == "NO"
        assert out.cft_console_type == "html"

    def test_empty_string_to_none(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """-v / -p / -ext / -out 空字符串应转为 None（避免冗余参数）。"""
        tab.v_edit.setText("   ")
        tab.p_edit.setText("")
        tab.ext_edit.setText("  ")
        tab.out_edit.setText("")
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.v_output is None
        assert out.p_prefix is None
        assert out.ext_extension is None
        assert out.out_file is None

    def test_n_spin_zero_to_none(self, tab: Blb2txtOutputTab) -> None:
        """-n spinbox 值为 0 时应转为 None（避免冗余 -n 0）。"""
        tab.n_spin.setValue(0)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.n_naming is None

    def test_n_spin_values_1_to_3(self, tab: Blb2txtOutputTab) -> None:
        """-n spinbox 取值 1/2/3 应原样写入 cfg。"""
        for v in (1, 2, 3):
            tab.n_spin.setValue(v)
            out = Blb2txtConfig.create_default()
            tab.collect_config(out)
            assert out.n_naming == v

    def test_combo_default_to_none(self, tab: Blb2txtOutputTab) -> None:
        """-e / -cf / -cft 选 index 0（默认）时写入 None。"""
        tab.e_combo.setCurrentIndex(0)
        tab.cf_combo.setCurrentIndex(0)
        tab.cft_combo.setCurrentIndex(0)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.e_encoding is None
        assert out.cf_console_file is None
        assert out.cft_console_type is None

    def test_apply_config_none_restores_default_index(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """apply None 字段时 combo 应还原到 index 0。"""
        cfg = Blb2txtConfig.create_default()
        cfg.e_encoding = None
        cfg.cf_console_file = None
        cfg.cft_console_type = None
        cfg.n_naming = None
        tab.apply_config(cfg)
        assert tab.e_combo.currentIndex() == 0
        assert tab.cf_combo.currentIndex() == 0
        assert tab.cft_combo.currentIndex() == 0
        assert tab.n_spin.value() == 0


# ---------------------------------------------------------------------------
# 控件预设选项测试
# ---------------------------------------------------------------------------
class TestComboPresets:
    """验证 -e / -cf / -cft QComboBox 的预设选项覆盖 schema 取值。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtOutputTab:
        return Blb2txtOutputTab()

    def test_e_combo_encoding_options(self, tab: Blb2txtOutputTab) -> None:
        """-e 编码 combo 应覆盖 ansi/utf8/utf8b/utf16/utf16be/utf16le。"""
        data_items = [
            tab.e_combo.itemData(i) for i in range(tab.e_combo.count())
        ]
        for enc in ("ansi", "utf8", "utf8b", "utf16", "utf16be", "utf16le"):
            assert enc in data_items, f"缺少编码选项 {enc!r}"

    def test_cf_combo_options(self, tab: Blb2txtOutputTab) -> None:
        """-cf 控制台输出 combo 应覆盖 YES/NO/STOP。"""
        data_items = [
            tab.cf_combo.itemData(i) for i in range(tab.cf_combo.count())
        ]
        for v in ("YES", "NO", "STOP"):
            assert v in data_items, f"缺少 -cf 选项 {v!r}"

    def test_cft_combo_options(self, tab: Blb2txtOutputTab) -> None:
        """-cft 控制台类型 combo 应覆盖 txt/html。"""
        data_items = [
            tab.cft_combo.itemData(i) for i in range(tab.cft_combo.count())
        ]
        for v in ("txt", "html"):
            assert v in data_items, f"缺少 -cft 选项 {v!r}"


# ---------------------------------------------------------------------------
# n_naming spinbox range 测试
# ---------------------------------------------------------------------------
class TestNamingSpinboxRange:
    """验证 -n QSpinBox 的取值范围。"""

    def test_n_spin_range(self, qapp: QApplication) -> None:
        tab = Blb2txtOutputTab()
        assert tab.n_spin.minimum() == 0
        assert tab.n_spin.maximum() == 3

    def test_n_spin_special_value_text(
        self, qapp: QApplication
    ) -> None:
        """-n spinbox 值 0 时显示特殊文本（默认）。"""
        tab = Blb2txtOutputTab()
        tab.n_spin.setValue(0)
        assert tab.n_spin.specialValueText() != ""


# ---------------------------------------------------------------------------
# Task 4: QGroupBox 分组与 2x2 checkbox 网格布局测试
# ---------------------------------------------------------------------------
class TestGroupBoxLayout:
    """验证 3 个 QGroupBox 分组与 2x2 checkbox 网格布局。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtOutputTab:
        return Blb2txtOutputTab()

    def _find_groupboxes(self, tab: Blb2txtOutputTab) -> list[QGroupBox]:
        """收集 tab 下所有 QGroupBox 子控件。"""
        return tab.findChildren(QGroupBox)

    def test_has_three_groupboxes(self, tab: Blb2txtOutputTab) -> None:
        """Tab 内 SHALL 有 3 个 QGroupBox 分组。"""
        groups = self._find_groupboxes(tab)
        assert len(groups) == 3, (
            f"应有 3 个 QGroupBox，实际 {len(groups)}"
        )

    def test_groupbox_titles_match_expected(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """3 个 QGroupBox 标题 SHALL 为 输出路径 / 覆盖模式 / 编码格式。"""
        groups = self._find_groupboxes(tab)
        titles = {g.title() for g in groups}
        expected = {"输出路径", "覆盖模式", "编码格式"}
        assert titles == expected, (
            f"QGroupBox 标题应为 {expected}，实际 {titles}"
        )

    def test_path_group_contains_v_p_ext_out(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """「输出路径」QGroupBox SHALL 包含 -v / -p / -ext / -out 4 个控件。"""
        groups = self._find_groupboxes(tab)
        path_group = next(g for g in groups if g.title() == "输出路径")
        lineedits = path_group.findChildren(QLineEdit)
        assert len(lineedits) == 4, (
            f"输出路径组应有 4 个 QLineEdit，实际 {len(lineedits)}"
        )

    def test_encoding_group_contains_three_combos(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """「编码格式」QGroupBox SHALL 包含 -e / -cf / -cft 3 个 QComboBox。"""
        groups = self._find_groupboxes(tab)
        enc_group = next(
            g for g in groups if g.title() == "编码格式"
        )
        combos = enc_group.findChildren(QComboBox)
        assert len(combos) == 3, (
            f"编码格式组应有 3 个 QComboBox，实际 {len(combos)}"
        )

    def test_overwrite_group_contains_four_checkboxes(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """「覆盖模式」QGroupBox SHALL 包含 -o / -u / -b / -a 4 个 QCheckBox。"""
        groups = self._find_groupboxes(tab)
        ow_group = next(g for g in groups if g.title() == "覆盖模式")
        checkboxes = ow_group.findChildren(QCheckBox)
        assert len(checkboxes) == 4, (
            f"覆盖模式组应有 4 个 QCheckBox，实际 {len(checkboxes)}"
        )

    def test_overwrite_group_contains_n_spin(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """「覆盖模式」QGroupBox SHALL 包含 -n QSpinBox。"""
        groups = self._find_groupboxes(tab)
        ow_group = next(g for g in groups if g.title() == "覆盖模式")
        spins = ow_group.findChildren(QSpinBox)
        assert len(spins) == 1, (
            f"覆盖模式组应有 1 个 QSpinBox，实际 {len(spins)}"
        )

    def test_checkbox_uses_grid_layout(
        self, tab: Blb2txtOutputTab
    ) -> None:
        """4 个 checkbox SHALL 使用 QGridLayout 2x2 排布。"""
        groups = self._find_groupboxes(tab)
        ow_group = next(g for g in groups if g.title() == "覆盖模式")
        # 在覆盖模式组中查找 QGridLayout
        grids = ow_group.findChildren(QGridLayout)
        assert len(grids) >= 1, (
            "覆盖模式组应至少有 1 个 QGridLayout（用于 2x2 checkbox 排布）"
        )
        # 验证 QGridLayout 容纳 4 个 checkbox
        checkbox_grid = next(
            g for g in grids
            if g.itemAtPosition(0, 0) and g.itemAtPosition(0, 0).widget()
            and isinstance(
                g.itemAtPosition(0, 0).widget(), QCheckBox
            )
        )
        # 验证 2x2 网格：4 个位置都有 checkbox
        positions = [
            (0, 0), (0, 1), (1, 0), (1, 1),
        ]
        for row, col in positions:
            item = checkbox_grid.itemAtPosition(row, col)
            assert item is not None, (
                f"QGridLayout ({row},{col}) 位置应有 item"
            )
            assert isinstance(
                item.widget(), QCheckBox
            ), f"QGridLayout ({row},{col}) 位置应为 QCheckBox"


# ---------------------------------------------------------------------------
# Task 4: QToolButton 替代 QPushButton 测试
# ---------------------------------------------------------------------------
class TestBrowseToolButton:
    """验证浏览按钮使用 QToolButton（而非 QPushButton）。"""

    def test_no_qpushbutton_in_tab(
        self, qapp: QApplication
    ) -> None:
        """Tab 内 SHALL 不包含 QPushButton（浏览按钮改用 QToolButton）。"""
        from PySide6.QtWidgets import QPushButton

        tab = Blb2txtOutputTab()
        pushbtns = tab.findChildren(QPushButton)
        assert len(pushbtns) == 0, (
            f"Tab 内不应有 QPushButton，实际有 {len(pushbtns)} 个"
        )

    def test_has_two_toolbuttons(
        self, qapp: QApplication
    ) -> None:
        """Tab 内 SHALL 有 2 个 QToolButton（-v / -out 浏览按钮）。"""
        tab = Blb2txtOutputTab()
        toolbtns = tab.findChildren(QToolButton)
        assert len(toolbtns) == 2, (
            f"应有 2 个 QToolButton，实际 {len(toolbtns)}"
        )

    def test_toolbutton_text_is_browse(
        self, qapp: QApplication
    ) -> None:
        """QToolButton 文本 SHALL 为「浏览…」。"""
        tab = Blb2txtOutputTab()
        toolbtns = tab.findChildren(QToolButton)
        for btn in toolbtns:
            assert btn.text() == "浏览…", (
                f"QToolButton 文本应为 '浏览…'，实际 {btn.text()!r}"
            )
