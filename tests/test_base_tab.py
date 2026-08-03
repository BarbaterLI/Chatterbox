"""base_tab 模块单元测试。

验证 :class:`AbstractTab` 的 ``tab_tool`` 默认实现与抽象语义，
以及 :class:`AbstractParamTab` 的 ``_collect_int`` / ``_apply_int``
在 :class:`BalconConfig` 与 :class:`Blb2txtConfig` 上的泛化行为。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSpinBox

from balcon_batch_tts.core.base_config import BaseToolConfig
from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.base_tab import AbstractParamTab, AbstractTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 测试用具体子类：仅满足 AbstractTab 的抽象方法契约。
# ---------------------------------------------------------------------------
class _ConcreteTab(AbstractTab):
    """最小可实例化的 AbstractTab 子类，用于测试默认 ``tab_tool``。"""

    @classmethod
    def tab_id(cls) -> str:
        return "test_concrete"

    @classmethod
    def tab_title(cls) -> str:
        return "测试 Tab"

    def collect_config(self, cfg: BalconConfig) -> None:
        pass

    def apply_config(self, cfg: BalconConfig) -> None:
        pass


class _Blb2txtTab(AbstractParamTab):
    """重写 ``tab_tool`` 返回 BLB2TXT 的子类，验证可覆盖默认实现。"""

    @classmethod
    def tab_id(cls) -> str:
        return "test_blb2txt"

    @classmethod
    def tab_title(cls) -> str:
        return "测试 blb2txt Tab"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    def collect_config(self, cfg: BalconConfig) -> None:
        pass

    def apply_config(self, cfg: BalconConfig) -> None:
        pass


# ---------------------------------------------------------------------------
# tab_tool 默认实现
# ---------------------------------------------------------------------------
class TestTabTool:
    """``AbstractTab.tab_tool`` 默认行为与可覆盖性。"""

    def test_default_returns_balcon(self) -> None:
        """子类未重写时 ``tab_tool`` 默认返回 :attr:`ToolType.BALCON`。"""
        assert _ConcreteTab.tab_tool() is ToolType.BALCON

    def test_override_returns_blb2txt(self) -> None:
        """子类重写后可返回 :attr:`ToolType.BLB2TXT`。"""
        assert _Blb2txtTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_tool_is_classmethod(self) -> None:
        """``tab_tool`` 应为 classmethod，可通过类对象直接调用。"""
        assert isinstance(AbstractTab.__dict__["tab_tool"], classmethod)

    def test_tab_tool_not_abstract(self) -> None:
        """``tab_tool`` 不应是抽象方法，子类无需重写即可使用。"""
        method = AbstractTab.tab_tool
        assert not getattr(method, "__isabstractmethod__", False)

    def test_abstract_tab_cannot_instantiate(self) -> None:
        """``AbstractTab`` 含抽象方法，直接实例化应抛 TypeError。"""
        with pytest.raises(TypeError):
            AbstractTab()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# AbstractParamTab._collect_int / _apply_int 泛化
# ---------------------------------------------------------------------------
class TestCollectApplyInt:
    """``_collect_int`` / ``_apply_int`` 在两种 config 类型上的行为。"""

    @pytest.fixture
    def param_tab(self, qapp: QApplication) -> AbstractParamTab:
        """提供一个最小可实例化的 AbstractParamTab 子类实例。"""

        class _ParamTab(AbstractParamTab):
            @classmethod
            def tab_id(cls) -> str:
                return "test_param"

            @classmethod
            def tab_title(cls) -> str:
                return "测试参数 Tab"

            def collect_config(self, cfg: BalconConfig) -> None:
                pass

            def apply_config(self, cfg: BalconConfig) -> None:
                pass

        return _ParamTab()

    @pytest.fixture
    def spinbox(self, qapp: QApplication) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(-100, 100)
        return sb

    # --- BalconConfig 向后兼容 ---

    def test_collect_int_balcon(self, param_tab: AbstractParamTab, spinbox: QSpinBox) -> None:
        """``_collect_int`` 对 BalconConfig 仍工作（向后兼容）。"""
        cfg = BalconConfig.create_default()
        spinbox.setValue(7)
        param_tab._collect_int(cfg, "-s", spinbox)
        assert cfg.s_rate == 7

    def test_collect_int_balcon_zero_to_none(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_collect_int`` 在 spinbox 值为 0 时设为 None。"""
        cfg = BalconConfig.create_default()
        cfg.s_rate = 5  # 先设非默认值
        spinbox.setValue(0)
        param_tab._collect_int(cfg, "-s", spinbox)
        assert cfg.s_rate is None

    def test_apply_int_balcon(self, param_tab: AbstractParamTab, spinbox: QSpinBox) -> None:
        """``_apply_int`` 对 BalconConfig 还原控件状态。"""
        cfg = BalconConfig.create_default()
        cfg.s_rate = 5
        param_tab._apply_int(cfg, "-s", spinbox)
        assert spinbox.value() == 5

    def test_apply_int_balcon_none(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_apply_int`` 在 cfg 字段为 None 时置 spinbox 为 0。"""
        cfg = BalconConfig.create_default()
        cfg.s_rate = None
        spinbox.setValue(99)
        param_tab._apply_int(cfg, "-s", spinbox)
        assert spinbox.value() == 0

    # --- Blb2txtConfig 泛化 ---

    def test_collect_int_blb2txt(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_collect_int`` 对 Blb2txtConfig 工作（-n → n_naming）。"""
        cfg = Blb2txtConfig.create_default()
        spinbox.setValue(3)
        param_tab._collect_int(cfg, "-n", spinbox)
        assert cfg.n_naming == 3

    def test_collect_int_blb2txt_zero_to_none(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_collect_int`` 对 Blb2txtConfig 在 0 时设为 None。"""
        cfg = Blb2txtConfig.create_default()
        cfg.n_naming = 2
        spinbox.setValue(0)
        param_tab._collect_int(cfg, "-n", spinbox)
        assert cfg.n_naming is None

    def test_apply_int_blb2txt(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_apply_int`` 对 Blb2txtConfig 还原控件状态。"""
        cfg = Blb2txtConfig.create_default()
        cfg.n_naming = 4
        param_tab._apply_int(cfg, "-n", spinbox)
        assert spinbox.value() == 4

    def test_apply_int_blb2txt_none(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_apply_int`` 对 Blb2txtConfig 在 None 时置 spinbox 为 0。"""
        cfg = Blb2txtConfig.create_default()
        cfg.n_naming = None
        spinbox.setValue(50)
        param_tab._apply_int(cfg, "-n", spinbox)
        assert spinbox.value() == 0

    def test_collect_int_same_option_different_field(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``-n`` 在 BalconConfig 与 Blb2txtConfig 上分别映射到不同字段。

        BalconConfig 中 ``-n`` → ``n_voice``（str，但 ``_collect_int``
        仍会写入，因为字段定位基于类型动态查找）。
        Blb2txtConfig 中 ``-n`` → ``n_naming``（int）。
        """
        balcon_cfg = BalconConfig.create_default()
        blb2txt_cfg = Blb2txtConfig.create_default()
        spinbox.setValue(6)

        param_tab._collect_int(blb2txt_cfg, "-n", spinbox)
        assert blb2txt_cfg.n_naming == 6

        # BalconConfig 的 -n 是 n_voice（str 字段），_collect_int 会写入 int 值。
        # 验证字段定位正确（n_voice 而非其他），不验证值类型转换。
        param_tab._collect_int(balcon_cfg, "-n", spinbox)
        assert balcon_cfg.n_voice == 6

    # --- 错误处理 ---

    def test_collect_int_unknown_option_no_crash(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_collect_int`` 对未知选项名应记日志并安全返回，不抛异常。"""
        cfg = BalconConfig.create_default()
        spinbox.setValue(5)
        param_tab._collect_int(cfg, "--nonexistent-option", spinbox)
        # cfg 不应有变化
        assert cfg.s_rate is None

    def test_apply_int_unknown_option_no_crash(
        self, param_tab: AbstractParamTab, spinbox: QSpinBox
    ) -> None:
        """``_apply_int`` 对未知选项名应记日志并安全返回。"""
        cfg = BalconConfig.create_default()
        spinbox.setValue(99)
        param_tab._apply_int(cfg, "--nonexistent-option", spinbox)
        # spinbox 应保持原值（未被覆盖）
        assert spinbox.value() == 99

    def test_option_to_field_helper_balcon(self, param_tab: AbstractParamTab) -> None:
        """``_option_to_field`` 静态方法对 BalconConfig 反查字段名。"""
        cfg = BalconConfig.create_default()
        assert AbstractParamTab._option_to_field(cfg, "-s") == "s_rate"
        assert AbstractParamTab._option_to_field(cfg, "-v") == "v_volume"
        assert AbstractParamTab._option_to_field(cfg, "--unknown") is None

    def test_option_to_field_helper_blb2txt(self, param_tab: AbstractParamTab) -> None:
        """``_option_to_field`` 静态方法对 Blb2txtConfig 反查字段名。"""
        cfg = Blb2txtConfig.create_default()
        assert AbstractParamTab._option_to_field(cfg, "-n") == "n_naming"
        assert AbstractParamTab._option_to_field(cfg, "-l") == "l_level"
        assert AbstractParamTab._option_to_field(cfg, "--unknown") is None


# ---------------------------------------------------------------------------
# 回归验证：既有 12 个 balcon Tab 继承默认 tab_tool
# ---------------------------------------------------------------------------
class TestExistingTabsInheritDefault:
    """验证既有 balcon Tab 未重写 ``tab_tool``，继承默认 BALCON 实现。"""

    def test_all_existing_tabs_return_balcon(self) -> None:
        """通过 TabRegistry 发现的 balcon 系列 Tab 应返回 ToolType.BALCON。

        blb2txt 系列 Tab（Task 15+ 起）重写 ``tab_tool`` 返回
        :attr:`ToolType.BLB2TXT`，本测试仅验证非 blb2txt Tab 的默认继承行为。
        """
        from balcon_batch_tts.gui.tabs import TabRegistry

        # 强制重新扫描以发现最新 Tab 集合
        TabRegistry.refresh()
        tabs = TabRegistry.get_all_tabs()
        assert len(tabs) > 0, "TabRegistry 应至少发现一个 Tab"
        balcon_tabs = [t for t in tabs if t.tab_tool() is ToolType.BALCON]
        # 既有 12 个 balcon Tab 应全部继承默认 tab_tool 返回 BALCON
        # （Task 4b 合并 SilenceTab 入 VoiceTab，从 13 减至 12）
        assert len(balcon_tabs) >= 12, (
            f"应至少存在 12 个 balcon Tab 返回 BALCON，"
            f"实际 {len(balcon_tabs)} 个"
        )
