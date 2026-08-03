"""blb2txt_eml_tab 模块单元测试。

验证 :class:`Blb2txtEmlTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、9 个参数控件存在性，以及
``collect_config`` / ``apply_config`` 的往返一致性。
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
from balcon_batch_tts.gui.tabs.blb2txt_eml_tab import Blb2txtEmlTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Tab 元信息
# ---------------------------------------------------------------------------
class TestTabMeta:
    """``Blb2txtEmlTab`` 的 classmethod 元信息返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtEmlTab.tab_id() == "blb2txt_eml"

    def test_tab_title(self) -> None:
        assert Blb2txtEmlTab.tab_title() == "EML（blb2txt）"

    def test_tab_group(self) -> None:
        """验收项：``tab_group`` 必须返回 ``"格式选项"``（Task 3 合并）。"""
        assert Blb2txtEmlTab.tab_group() == "格式选项"

    def test_tab_tool(self) -> None:
        """``tab_tool`` 应返回 :attr:`ToolType.BLB2TXT`，而非默认 BALCON。"""
        assert Blb2txtEmlTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_icon_not_none(self) -> None:
        """``tab_icon`` 应返回非 None 的 QIcon（即使 SVG 渲染失败也是 QIcon）。"""
        icon = Blb2txtEmlTab.tab_icon()
        assert icon is not None

    def test_is_abstracttab_subclass(self) -> None:
        from balcon_batch_tts.gui.tabs.base_tab import AbstractTab

        assert issubclass(Blb2txtEmlTab, AbstractTab)


# ---------------------------------------------------------------------------
# 9 个参数控件存在性
# ---------------------------------------------------------------------------
class TestControlsExist:
    """验证 9 个参数对应的控件属性均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtEmlTab:
        return Blb2txtEmlTab()

    @pytest.mark.parametrize(
        "attr,widget_type,option",
        [
            # 5 个 flag → QCheckBox
            ("eml_save_chk", QCheckBox, "--eml-save"),
            ("eml_att_chk", QCheckBox, "--eml-att"),
            ("eml_cc_chk", QCheckBox, "--eml-cc"),
            ("eml_org_chk", QCheckBox, "--eml-org"),
            ("eml_rt_chk", QCheckBox, "--eml-rt"),
            # 4 个 str → QLineEdit
            ("eml_date_edit", QLineEdit, "--eml-date"),
            ("eml_from_edit", QLineEdit, "--eml-from"),
            ("eml_subj_edit", QLineEdit, "--eml-subj"),
            ("eml_to_edit", QLineEdit, "--eml-to"),
        ],
    )
    def test_control_exists(
        self,
        tab: Blb2txtEmlTab,
        attr: str,
        widget_type: type,
        option: str,
    ) -> None:
        """每个参数对应的控件应存在且类型正确。"""
        assert hasattr(tab, attr), f"缺少控件属性 {attr}（对应 {option}）"
        widget = getattr(tab, attr)
        assert isinstance(widget, widget_type), (
            f"{attr} 应为 {widget_type.__name__}，"
            f"实际为 {type(widget).__name__}"
        )

    def test_control_count_is_9(self, tab: Blb2txtEmlTab) -> None:
        """9 个参数控件属性应全部存在。"""
        expected = {
            "eml_save_chk",
            "eml_att_chk",
            "eml_cc_chk",
            "eml_date_edit",
            "eml_from_edit",
            "eml_org_chk",
            "eml_rt_chk",
            "eml_subj_edit",
            "eml_to_edit",
        }
        actual = {attr for attr in expected if hasattr(tab, attr)}
        assert actual == expected


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致
# ---------------------------------------------------------------------------
class TestCollectApplyRoundtrip:
    """``collect_config`` 与 ``apply_config`` 的双向往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtEmlTab:
        return Blb2txtEmlTab()

    def test_default_to_empty_args(self, tab: Blb2txtEmlTab) -> None:
        """默认控件状态 collect 后，cfg.to_args() 应不含任何 EML 参数。"""
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        args = cfg.to_args()
        for option in (
            "--eml-save",
            "--eml-att",
            "--eml-cc",
            "--eml-date",
            "--eml-from",
            "--eml-org",
            "--eml-rt",
            "--eml-subj",
            "--eml-to",
        ):
            assert option not in args, (
                f"默认状态下不应生成 {option}，实际 args={args}"
            )

    def test_apply_default_config(self, tab: Blb2txtEmlTab) -> None:
        """从默认 cfg 还原控件：5 flag 全 False，4 str 字段为空。"""
        cfg = Blb2txtConfig.create_default()
        tab.apply_config(cfg)
        assert tab.eml_save_chk.isChecked() is False
        assert tab.eml_att_chk.isChecked() is False
        assert tab.eml_cc_chk.isChecked() is False
        assert tab.eml_date_edit.text() == ""
        assert tab.eml_from_edit.text() == ""
        assert tab.eml_org_chk.isChecked() is False
        assert tab.eml_rt_chk.isChecked() is False
        assert tab.eml_subj_edit.text() == ""
        assert tab.eml_to_edit.text() == ""

    def test_roundtrip_all_set(self, tab: Blb2txtEmlTab) -> None:
        """设置全部 9 个控件后 collect → 新 tab apply → 控件状态一致。"""
        tab.eml_save_chk.setChecked(True)
        tab.eml_att_chk.setChecked(True)
        tab.eml_cc_chk.setChecked(True)
        tab.eml_date_edit.setText("%Y-%m-%d")
        tab.eml_from_edit.setText("%name% <%addr%>")
        tab.eml_org_chk.setChecked(True)
        tab.eml_rt_chk.setChecked(True)
        tab.eml_subj_edit.setText("%s")
        tab.eml_to_edit.setText("%name% <%addr%>")

        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.eml_save is True
        assert cfg.eml_att is True
        assert cfg.eml_cc is True
        assert cfg.eml_date == "%Y-%m-%d"
        assert cfg.eml_from == "%name% <%addr%>"
        assert cfg.eml_org is True
        assert cfg.eml_rt is True
        assert cfg.eml_subj == "%s"
        assert cfg.eml_to == "%name% <%addr%>"

        # 用同一 cfg 还原到新 tab 实例，验证往返一致
        tab2 = Blb2txtEmlTab()
        tab2.apply_config(cfg)
        assert tab2.eml_save_chk.isChecked() is True
        assert tab2.eml_att_chk.isChecked() is True
        assert tab2.eml_cc_chk.isChecked() is True
        assert tab2.eml_date_edit.text() == "%Y-%m-%d"
        assert tab2.eml_from_edit.text() == "%name% <%addr%>"
        assert tab2.eml_org_chk.isChecked() is True
        assert tab2.eml_rt_chk.isChecked() is True
        assert tab2.eml_subj_edit.text() == "%s"
        assert tab2.eml_to_edit.text() == "%name% <%addr%>"

    def test_roundtrip_to_args_and_back(self, tab: Blb2txtEmlTab) -> None:
        """collect → to_args → from_dict → apply → 控件状态一致。"""
        tab.eml_save_chk.setChecked(True)
        tab.eml_date_edit.setText("%Y-%m-%d %H:%M")
        tab.eml_from_edit.setText("From: %name%")
        tab.eml_rt_chk.setChecked(True)
        tab.eml_to_edit.setText("To: %name%")

        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        args = cfg.to_args()
        assert "--eml-save" in args
        assert "--eml-date" in args
        assert "%Y-%m-%d %H:%M" in args
        assert "--eml-from" in args
        assert "From: %name%" in args
        assert "--eml-rt" in args
        assert "--eml-to" in args
        assert "To: %name%" in args

        # 序列化往返
        cfg_dict = cfg.to_dict()
        cfg2 = Blb2txtConfig.from_dict(cfg_dict)
        tab2 = Blb2txtEmlTab()
        tab2.apply_config(cfg2)
        assert tab2.eml_save_chk.isChecked() is True
        assert tab2.eml_date_edit.text() == "%Y-%m-%d %H:%M"
        assert tab2.eml_from_edit.text() == "From: %name%"
        assert tab2.eml_rt_chk.isChecked() is True
        assert tab2.eml_to_edit.text() == "To: %name%"

    def test_str_fields_empty_to_none(self, tab: Blb2txtEmlTab) -> None:
        """4 个 str 字段输入为空（或纯空白）时，collect 后应为 None。"""
        tab.eml_date_edit.setText("   ")
        tab.eml_from_edit.setText("\t")
        tab.eml_subj_edit.setText("")
        tab.eml_to_edit.setText("  \t ")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.eml_date is None
        assert cfg.eml_from is None
        assert cfg.eml_subj is None
        assert cfg.eml_to is None


# ---------------------------------------------------------------------------
# config_changed 信号
# ---------------------------------------------------------------------------
class TestConfigChangedSignal:
    """控件值变化应发射 ``config_changed`` 信号。"""

    def test_signal_emitted_on_checkbox_toggle(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtEmlTab()
        signals: list[None] = []
        tab.config_changed.connect(lambda: signals.append(None))
        tab.eml_save_chk.setChecked(True)
        assert len(signals) >= 1

    def test_signal_emitted_on_lineedit_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtEmlTab()
        signals: list[None] = []
        tab.config_changed.connect(lambda: signals.append(None))
        tab.eml_date_edit.setText("%Y-%m-%d")
        assert len(signals) >= 1
