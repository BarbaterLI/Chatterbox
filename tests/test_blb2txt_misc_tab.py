"""Blb2txtMiscTab 单元测试。

验证 :class:`Blb2txtMiscTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、2 个参数控件存在性，以及
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
)

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_misc_tab import Blb2txtMiscTab


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
    """``Blb2txtMiscTab`` 的元信息方法返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtMiscTab.tab_id() == "blb2txt_misc"

    def test_tab_title(self) -> None:
        assert Blb2txtMiscTab.tab_title() == "其他（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtMiscTab.tab_group() == "高级"

    def test_tab_tool(self) -> None:
        assert Blb2txtMiscTab.tab_tool() is ToolType.BLB2TXT


# ---------------------------------------------------------------------------
# 控件存在性测试
# ---------------------------------------------------------------------------
class TestWidgetsExist:
    """验证 2 个参数控件均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtMiscTab:
        return Blb2txtMiscTab()

    def test_dp_widget_is_checkbox(self, tab: Blb2txtMiscTab) -> None:
        """-dp (dp_no_prompt) 控件为 QCheckBox。"""
        assert isinstance(tab.dp_check, QCheckBox)

    def test_cfg_widget_is_lineedit(self, tab: Blb2txtMiscTab) -> None:
        """-cfg (cfg_file) 控件为 QLineEdit。"""
        assert isinstance(tab.cfg_edit, QLineEdit)


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致性
# ---------------------------------------------------------------------------
class TestCollectApplyRoundTrip:
    """``collect_config`` 与 ``apply_config`` 的往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtMiscTab:
        return Blb2txtMiscTab()

    def test_default_round_trip(self, tab: Blb2txtMiscTab) -> None:
        """默认值往返：apply 默认 cfg 后 collect 应得到全 None/False 字段。"""
        cfg = Blb2txtConfig.create_default()
        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.dp_no_prompt is False
        assert out.cfg_file is None

    def test_full_round_trip(self, tab: Blb2txtMiscTab) -> None:
        """设置全部 2 个字段后往返，应保持一致。"""
        cfg = Blb2txtConfig.create_default()
        cfg.dp_no_prompt = True
        cfg.cfg_file = "/tmp/config.cfg"

        tab.apply_config(cfg)
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)

        assert out.dp_no_prompt is True
        assert out.cfg_file == "/tmp/config.cfg"

    def test_empty_string_to_none(self, tab: Blb2txtMiscTab) -> None:
        """-cfg 空字符串/纯空白应转为 None（避免冗余参数）。"""
        tab.cfg_edit.setText("   ")
        out = Blb2txtConfig.create_default()
        tab.collect_config(out)
        assert out.cfg_file is None

    def test_apply_config_none_restores_empty(
        self, tab: Blb2txtMiscTab
    ) -> None:
        """apply None 字段时 cfg_edit 应还原为空字符串。"""
        cfg = Blb2txtConfig.create_default()
        cfg.cfg_file = None
        cfg.dp_no_prompt = False
        tab.apply_config(cfg)
        assert tab.cfg_edit.text() == ""
        assert tab.dp_check.isChecked() is False

    def test_dp_check_round_trip_both_states(
        self, tab: Blb2txtMiscTab
    ) -> None:
        """-dp 复选框两种状态均能往返。"""
        for state in (True, False):
            cfg = Blb2txtConfig.create_default()
            cfg.dp_no_prompt = state
            tab.apply_config(cfg)
            assert tab.dp_check.isChecked() is state
            out = Blb2txtConfig.create_default()
            tab.collect_config(out)
            assert out.dp_no_prompt is state
