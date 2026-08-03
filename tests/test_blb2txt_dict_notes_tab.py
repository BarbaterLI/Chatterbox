"""Blb2txtDictNotesTab 单元测试。

验证 :class:`Blb2txtDictNotesTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、6 个参数控件存在性，以及
``collect_config`` / ``apply_config`` 往返一致性。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLineEdit,
    QSpinBox,
)

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_dict_notes_tab import (
    Blb2txtDictNotesTab,
)


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Tab 元信息测试
# ---------------------------------------------------------------------------
class TestTabMetadata:
    """``Blb2txtDictNotesTab`` 的元信息方法返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtDictNotesTab.tab_id() == "blb2txt_dict_notes"

    def test_tab_title(self) -> None:
        assert Blb2txtDictNotesTab.tab_title() == "字典注释（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtDictNotesTab.tab_group() == "格式选项"

    def test_tab_tool(self) -> None:
        assert Blb2txtDictNotesTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_icon_not_none(self, qapp: QApplication) -> None:
        """tab_icon 应返回 QIcon（非 None）。"""
        icon = Blb2txtDictNotesTab.tab_icon()
        assert icon is not None


# ---------------------------------------------------------------------------
# 控件存在性测试
# ---------------------------------------------------------------------------
class TestWidgetsExist:
    """验证 6 个参数控件均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtDictNotesTab:
        return Blb2txtDictNotesTab()

    def test_d_dict_widget_is_lineedit(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """-d (d_dict) 控件为 QLineEdit。"""
        assert isinstance(tab.d_dict_edit, QLineEdit)

    def test_extract_summary_widget_is_spinbox(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--extract-summary / -es (extract_summary) 控件为 QSpinBox。"""
        assert isinstance(tab.extract_summary_spin, QSpinBox)

    def test_skip_notes_widget_is_checkbox(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--skip-notes / -sn (skip_notes) 控件为 QCheckBox。"""
        assert isinstance(tab.skip_notes_chk, QCheckBox)

    def test_include_notes_widget_is_spinbox(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--include-notes / -in (include_notes) 控件为 QSpinBox。"""
        assert isinstance(tab.include_notes_spin, QSpinBox)

    def test_insert_note_begin_widget_is_lineedit(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--insert-note-begin / -inb (insert_note_begin) 控件为 QLineEdit。"""
        assert isinstance(tab.insert_note_begin_edit, QLineEdit)

    def test_insert_note_end_widget_is_lineedit(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--insert-note-end / -ine (insert_note_end) 控件为 QLineEdit。"""
        assert isinstance(tab.insert_note_end_edit, QLineEdit)

    def test_all_six_widgets_exist(self, qapp: QApplication) -> None:
        """Tab 应包含恰好 6 个参数控件（2 QLineEdit + 2 QSpinBox +
        1 QCheckBox + 1 QLineEdit）。"""
        tab = Blb2txtDictNotesTab()
        # 直接通过属性访问验证 6 个控件均存在
        assert tab.d_dict_edit is not None
        assert tab.extract_summary_spin is not None
        assert tab.skip_notes_chk is not None
        assert tab.include_notes_spin is not None
        assert tab.insert_note_begin_edit is not None
        assert tab.insert_note_end_edit is not None


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致性
# ---------------------------------------------------------------------------
class TestCollectApplyRoundTrip:
    """``collect_config`` 与 ``apply_config`` 的往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtDictNotesTab:
        return Blb2txtDictNotesTab()

    def test_default_round_trip(self, tab: Blb2txtDictNotesTab) -> None:
        """默认值往返：apply 默认 cfg 后 collect 应得到全 None/False 字段。"""
        cfg = Blb2txtConfig.create_default()
        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.d_dict is None
        assert out.extract_summary is None
        assert out.skip_notes is False
        assert out.include_notes is None
        assert out.insert_note_begin is None
        assert out.insert_note_end is None

    def test_full_round_trip(self, tab: Blb2txtDictNotesTab) -> None:
        """设置全部 6 个字段后往返，应保持一致。"""
        cfg = Blb2txtConfig.create_default()
        cfg.d_dict = "/tmp/dict.dic"
        cfg.extract_summary = 1
        cfg.skip_notes = True
        cfg.include_notes = 1
        cfg.insert_note_begin = "【"
        cfg.insert_note_end = "】"

        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)

        assert out.d_dict == "/tmp/dict.dic"
        assert out.extract_summary == 1
        assert out.skip_notes is True
        assert out.include_notes == 1
        assert out.insert_note_begin == "【"
        assert out.insert_note_end == "】"

    def test_empty_string_to_none(self, tab: Blb2txtDictNotesTab) -> None:
        """-d / -inb / -ine 空字符串（或纯空白）应转为 None。"""
        tab.d_dict_edit.setText("   ")
        tab.insert_note_begin_edit.setText("")
        tab.insert_note_end_edit.setText("  ")
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.d_dict is None
        assert out.insert_note_begin is None
        assert out.insert_note_end is None

    def test_note_markers_keep_inner_content(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """注释标记的前后空白被 strip，但内部内容保留。"""
        tab.insert_note_begin_edit.setText("  【  ")
        tab.insert_note_end_edit.setText("  】  ")
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.insert_note_begin == "【"
        assert out.insert_note_end == "】"

    def test_extract_summary_spin_zero_to_none(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--extract-summary spinbox 值为 0 时应转为 None。"""
        tab.extract_summary_spin.setValue(0)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.extract_summary is None

    def test_include_notes_spin_zero_to_none(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """--include-notes spinbox 值为 0 时应转为 None。"""
        tab.include_notes_spin.setValue(0)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.include_notes is None

    def test_extract_summary_spin_one(self, tab: Blb2txtDictNotesTab) -> None:
        """--extract-summary spinbox 值为 1 时应写入 1。"""
        tab.extract_summary_spin.setValue(1)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.extract_summary == 1

    def test_include_notes_spin_one(self, tab: Blb2txtDictNotesTab) -> None:
        """--include-notes spinbox 值为 1 时应写入 1。"""
        tab.include_notes_spin.setValue(1)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.include_notes == 1

    def test_apply_config_none_restores_default_state(
        self, tab: Blb2txtDictNotesTab
    ) -> None:
        """apply None / False 字段时控件应还原到默认状态。"""
        cfg = Blb2txtConfig.create_default()
        cfg.d_dict = None
        cfg.extract_summary = None
        cfg.skip_notes = False
        cfg.include_notes = None
        cfg.insert_note_begin = None
        cfg.insert_note_end = None
        tab.apply_config(cfg)
        assert tab.d_dict_edit.text() == ""
        assert tab.extract_summary_spin.value() == 0
        assert tab.skip_notes_chk.isChecked() is False
        assert tab.include_notes_spin.value() == 0
        assert tab.insert_note_begin_edit.text() == ""
        assert tab.insert_note_end_edit.text() == ""


# ---------------------------------------------------------------------------
# Spinbox 取值范围测试
# ---------------------------------------------------------------------------
class TestSpinboxRange:
    """验证 --extract-summary / --include-notes QSpinBox 的取值范围。"""

    def test_es_spin_range(self, qapp: QApplication) -> None:
        tab = Blb2txtDictNotesTab()
        assert tab.extract_summary_spin.minimum() == 0
        assert tab.extract_summary_spin.maximum() == 1

    def test_in_spin_range(self, qapp: QApplication) -> None:
        tab = Blb2txtDictNotesTab()
        assert tab.include_notes_spin.minimum() == 0
        assert tab.include_notes_spin.maximum() == 1

    def test_es_spin_special_value_text(
        self, qapp: QApplication
    ) -> None:
        """--extract-summary spinbox 值 0 时显示特殊文本（默认）。"""
        tab = Blb2txtDictNotesTab()
        tab.extract_summary_spin.setValue(0)
        assert tab.extract_summary_spin.specialValueText() != ""

    def test_in_spin_special_value_text(
        self, qapp: QApplication
    ) -> None:
        """--include-notes spinbox 值 0 时显示特殊文本（默认）。"""
        tab = Blb2txtDictNotesTab()
        tab.include_notes_spin.setValue(0)
        assert tab.include_notes_spin.specialValueText() != ""


# ---------------------------------------------------------------------------
# TabRegistry 自动发现
# ---------------------------------------------------------------------------
class TestRegistryDiscovery:
    """TabRegistry 自动发现验证。"""

    def test_tab_discovered_by_registry(self) -> None:
        """TabRegistry 应自动发现 Blb2txtDictNotesTab。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        tab_ids = {t.tab_id() for t in tabs}
        assert "blb2txt_dict_notes" in tab_ids

    def test_tab_returns_blb2txt_in_registry(self) -> None:
        """Registry 中本 Tab 的 tab_tool 应为 BLB2TXT，分组为"格式选项"。"""
        from balcon_batch_tts.gui.tabs import TabRegistry

        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        for t in tabs:
            if t.tab_id() == "blb2txt_dict_notes":
                assert t.tab_tool() is ToolType.BLB2TXT
                assert t.tab_group() == "格式选项"
                return
        pytest.fail("TabRegistry 未发现 blb2txt_dict_notes Tab")
