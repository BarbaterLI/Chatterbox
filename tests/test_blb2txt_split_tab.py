"""blb2txt_split_tab 模块单元测试。

验证 :class:`Blb2txtSplitTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、10 个参数控件存在性，以及
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
    QSpinBox,
)

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.blb2txt_split_tab import Blb2txtSplitTab


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
    """``Blb2txtSplitTab`` 的 classmethod 元信息返回值。"""

    def test_tab_id(self) -> None:
        assert Blb2txtSplitTab.tab_id() == "blb2txt_split"

    def test_tab_title(self) -> None:
        assert Blb2txtSplitTab.tab_title() == "文本分割（blb2txt）"

    def test_tab_group(self) -> None:
        """验收项：``tab_group`` 必须返回 ``"文本处理"``。"""
        assert Blb2txtSplitTab.tab_group() == "文本处理"

    def test_tab_tool(self) -> None:
        """``tab_tool`` 应返回 :attr:`ToolType.BLB2TXT`，而非默认 BALCON。"""
        assert Blb2txtSplitTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_icon_not_none(self) -> None:
        """``tab_icon`` 应返回非 None 的 QIcon（即使 SVG 渲染失败也是 QIcon）。"""
        icon = Blb2txtSplitTab.tab_icon()
        assert icon is not None

    def test_is_abstracttab_subclass(self) -> None:
        from balcon_batch_tts.gui.tabs.base_tab import AbstractTab

        assert issubclass(Blb2txtSplitTab, AbstractTab)


# ---------------------------------------------------------------------------
# 10 个参数控件存在性
# ---------------------------------------------------------------------------
class TestControlsExist:
    """验证 10 个参数对应的控件属性均存在且类型正确。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtSplitTab:
        return Blb2txtSplitTab()

    @pytest.mark.parametrize(
        "attr,widget_type,option",
        [
            # 6 个 flag → QCheckBox
            ("t_topic_chk", QCheckBox, "-t"),
            ("r_recursive_chk", QCheckBox, "-r"),
            ("w_subdir_chk", QCheckBox, "-w"),
            ("toc_chk", QCheckBox, "-toc"),
            ("j_join_chk", QCheckBox, "-j"),
            ("hh_html_chk", QCheckBox, "-hh"),
            # -k 关键词 → QLineEdit
            ("k_keywords_edit", QLineEdit, "-k"),
            # 3 个 int → QSpinBox
            ("l_level_spin", QSpinBox, "-l"),
            ("c_chars_spin", QSpinBox, "-c"),
            ("m_min_length_spin", QSpinBox, "-m"),
        ],
    )
    def test_control_exists(
        self,
        tab: Blb2txtSplitTab,
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

    def test_control_count_is_10(self, tab: Blb2txtSplitTab) -> None:
        """10 个参数控件属性应全部存在。"""
        expected = {
            "t_topic_chk",
            "k_keywords_edit",
            "r_recursive_chk",
            "w_subdir_chk",
            "l_level_spin",
            "c_chars_spin",
            "toc_chk",
            "m_min_length_spin",
            "j_join_chk",
            "hh_html_chk",
        }
        actual = {
            attr
            for attr in expected
            if hasattr(tab, attr)
        }
        assert actual == expected


# ---------------------------------------------------------------------------
# collect_config / apply_config 往返一致
# ---------------------------------------------------------------------------
class TestCollectApplyRoundtrip:
    """``collect_config`` 与 ``apply_config`` 的双向往返一致性。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtSplitTab:
        return Blb2txtSplitTab()

    def test_default_to_empty_args(self, tab: Blb2txtSplitTab) -> None:
        """默认控件状态 collect 后，cfg.to_args() 应不含本 Tab 的参数。

        注意：``-l`` 默认 1、``-m`` 默认 512 是 GUI 显示默认值，
        collect 后会写入 cfg（非 None），故 to_args 会包含 ``-l 1`` 与
        ``-m 512``。本测试验证其余 8 个参数在默认状态下不出现在 args。
        """
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        args = cfg.to_args()
        # 6 个 flag 与 -k 默认 False/None，不应出现
        for option in ("-t", "-k", "-r", "-w", "-toc", "-j", "-hh"):
            assert option not in args, (
                f"默认状态下不应生成 {option}，实际 args={args}"
            )
        # -l / -m 默认显示值非 0，会出现在 args
        assert "-l" in args and "1" in args
        assert "-m" in args and "512" in args
        # -c 默认 0 → None，不应出现
        assert "-c" not in args

    def test_apply_default_config(self, tab: Blb2txtSplitTab) -> None:
        """从默认 cfg 还原控件：6 flag 全 False，-k 空，3 int 中 -l/-m 为 0。"""
        cfg = Blb2txtConfig.create_default()
        tab.apply_config(cfg)
        assert tab.t_topic_chk.isChecked() is False
        assert tab.k_keywords_edit.text() == ""
        assert tab.r_recursive_chk.isChecked() is False
        assert tab.w_subdir_chk.isChecked() is False
        # -l / -c / -m 字段为 None → spinbox 为 0
        assert tab.l_level_spin.value() == 0
        assert tab.c_chars_spin.value() == 0
        assert tab.m_min_length_spin.value() == 0
        assert tab.toc_chk.isChecked() is False
        assert tab.j_join_chk.isChecked() is False
        assert tab.hh_html_chk.isChecked() is False

    def test_roundtrip_all_set(self, tab: Blb2txtSplitTab) -> None:
        """设置全部 10 个控件后 collect → 新 tab apply → 控件状态一致。"""
        # 设置控件
        tab.t_topic_chk.setChecked(True)
        tab.k_keywords_edit.setText("第一章;第二章;第三章")
        tab.r_recursive_chk.setChecked(True)
        tab.w_subdir_chk.setChecked(True)
        tab.l_level_spin.setValue(3)
        tab.c_chars_spin.setValue(2000)
        tab.toc_chk.setChecked(True)
        tab.m_min_length_spin.setValue(1024)
        tab.j_join_chk.setChecked(True)
        tab.hh_html_chk.setChecked(True)

        # collect 到 cfg
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.t_topic is True
        assert cfg.k_keywords == "第一章;第二章;第三章"
        assert cfg.r_recursive is True
        assert cfg.w_subdir is True
        assert cfg.l_level == 3
        assert cfg.c_chars == 2000
        assert cfg.toc is True
        assert cfg.m_min_length == 1024
        assert cfg.j_join is True
        assert cfg.hh_html is True

        # 用同一 cfg 还原到新 tab 实例，验证往返一致
        tab2 = Blb2txtSplitTab()
        tab2.apply_config(cfg)
        assert tab2.t_topic_chk.isChecked() is True
        assert tab2.k_keywords_edit.text() == "第一章;第二章;第三章"
        assert tab2.r_recursive_chk.isChecked() is True
        assert tab2.w_subdir_chk.isChecked() is True
        assert tab2.l_level_spin.value() == 3
        assert tab2.c_chars_spin.value() == 2000
        assert tab2.toc_chk.isChecked() is True
        assert tab2.m_min_length_spin.value() == 1024
        assert tab2.j_join_chk.isChecked() is True
        assert tab2.hh_html_chk.isChecked() is True

    def test_roundtrip_to_args_and_back(self, tab: Blb2txtSplitTab) -> None:
        """collect → to_args → from_dict → apply → 控件状态一致。"""
        tab.t_topic_chk.setChecked(True)
        tab.k_keywords_edit.setText("intro;body;end")
        tab.l_level_spin.setValue(2)
        tab.c_chars_spin.setValue(500)
        tab.m_min_length_spin.setValue(256)
        tab.hh_html_chk.setChecked(True)

        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        args = cfg.to_args()
        # 验证关键参数已生成
        assert "-t" in args
        assert "-k" in args
        assert "intro;body;end" in args
        assert "-l" in args
        assert "-c" in args
        assert "-m" in args
        assert "-hh" in args

        # 序列化往返
        cfg_dict = cfg.to_dict()
        cfg2 = Blb2txtConfig.from_dict(cfg_dict)
        tab2 = Blb2txtSplitTab()
        tab2.apply_config(cfg2)
        assert tab2.t_topic_chk.isChecked() is True
        assert tab2.k_keywords_edit.text() == "intro;body;end"
        assert tab2.l_level_spin.value() == 2
        assert tab2.c_chars_spin.value() == 500
        assert tab2.m_min_length_spin.value() == 256
        assert tab2.hh_html_chk.isChecked() is True

    def test_k_keywords_empty_to_none(self, tab: Blb2txtSplitTab) -> None:
        """``-k`` 输入为空（或纯空白）时，collect 后 ``k_keywords`` 应为 None。"""
        tab.k_keywords_edit.setText("   ")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.k_keywords is None

    def test_l_level_zero_to_none(self, tab: Blb2txtSplitTab) -> None:
        """``-l`` spinbox 值为 0 时，collect 后 ``l_level`` 应为 None。"""
        tab.l_level_spin.setValue(0)
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.l_level is None


# ---------------------------------------------------------------------------
# config_changed 信号
# ---------------------------------------------------------------------------
class TestConfigChangedSignal:
    """控件值变化应发射 ``config_changed`` 信号。"""

    def test_signal_emitted_on_checkbox_toggle(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtSplitTab()
        signals: list[None] = []
        tab.config_changed.connect(lambda: signals.append(None))
        tab.t_topic_chk.setChecked(True)
        assert len(signals) >= 1

    def test_signal_emitted_on_lineedit_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtSplitTab()
        signals: list[None] = []
        tab.config_changed.connect(lambda: signals.append(None))
        tab.k_keywords_edit.setText("新关键词")
        assert len(signals) >= 1

    def test_signal_emitted_on_spinbox_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtSplitTab()
        signals: list[None] = []
        tab.config_changed.connect(lambda: signals.append(None))
        tab.c_chars_spin.setValue(100)
        assert len(signals) >= 1
