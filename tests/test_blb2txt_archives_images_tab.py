"""blb2txt_archives_images_tab 模块单元测试。

验证 :class:`Blb2txtArchivesImagesTab` 的元信息（``tab_id`` /
``tab_title`` / ``tab_group`` / ``tab_tool``）、5 个参数控件的存在性，
以及控件与 :class:`Blb2txtConfig` 之间的 collect/apply 往返一致性。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.base_tab import AbstractTab
from balcon_batch_tts.gui.tabs.blb2txt_archives_images_tab import (
    Blb2txtArchivesImagesTab,
)


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------
class TestBlb2txtArchivesImagesTabMeta:
    """``Blb2txtArchivesImagesTab`` 类元信息。"""

    def test_tab_id(self) -> None:
        assert Blb2txtArchivesImagesTab.tab_id() == "blb2txt_archives_images"

    def test_tab_title(self) -> None:
        assert Blb2txtArchivesImagesTab.tab_title() == "归档图像（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtArchivesImagesTab.tab_group() == "高级"

    def test_tab_tool_returns_blb2txt(self) -> None:
        """``tab_tool`` 应返回 :attr:`ToolType.BLB2TXT`。"""
        assert Blb2txtArchivesImagesTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_tool_is_classmethod(self) -> None:
        """``tab_tool`` 应为 classmethod（可由类对象直接调用）。"""
        assert isinstance(
            Blb2txtArchivesImagesTab.__dict__["tab_tool"], classmethod
        )

    def test_inherits_abstract_tab(self) -> None:
        assert issubclass(Blb2txtArchivesImagesTab, AbstractTab)

    def test_tab_icon_returns_qicon(self, qapp: QApplication) -> None:
        """``tab_icon`` 应返回分组"归档图像"对应的 QIcon。

        SVG 渲染依赖 QGuiApplication，故请求 ``qapp`` fixture。
        """
        from PySide6.QtGui import QIcon

        icon = Blb2txtArchivesImagesTab.tab_icon()
        assert isinstance(icon, QIcon)


# ---------------------------------------------------------------------------
# 控件存在性（5 个参数控件）
# ---------------------------------------------------------------------------
class TestBlb2txtArchivesImagesTabControls:
    """``Blb2txtArchivesImagesTab`` 包含 5 个参数控件。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtArchivesImagesTab:
        return Blb2txtArchivesImagesTab()

    def test_five_param_controls_exist(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """Tab 应包含 -dll、-dex、-dne、-g、-cvr 5 个参数控件。"""
        assert hasattr(tab, "dll_edit")    # -dll
        assert hasattr(tab, "dex_edit")    # -dex
        assert hasattr(tab, "dne_check")   # -dne
        assert hasattr(tab, "g_check")     # -g
        assert hasattr(tab, "cvr_check")   # -cvr

    def test_dll_control_is_lineedit(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-dll 控件应为 QLineEdit。"""
        assert isinstance(tab.dll_edit, QLineEdit)

    def test_dex_control_is_lineedit(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-dex 控件应为 QLineEdit。"""
        assert isinstance(tab.dex_edit, QLineEdit)

    def test_dne_control_is_checkbox(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-dne 控件应为 QCheckBox。"""
        assert isinstance(tab.dne_check, QCheckBox)

    def test_g_control_is_checkbox(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-g 控件应为 QCheckBox。"""
        assert isinstance(tab.g_check, QCheckBox)

    def test_cvr_control_is_checkbox(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-cvr 控件应为 QCheckBox。"""
        assert isinstance(tab.cvr_check, QCheckBox)

    def test_dex_placeholder_hints_separator(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """-dex 占位提示应包含 ``;`` 分隔符说明。"""
        assert ";" in tab.dex_edit.placeholderText()


# ---------------------------------------------------------------------------
# collect_config / apply_config
# ---------------------------------------------------------------------------
class TestBlb2txtArchivesImagesTabCollectApply:
    """``Blb2txtArchivesImagesTab`` 控件与 :class:`Blb2txtConfig` 的 collect/apply。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtArchivesImagesTab:
        return Blb2txtArchivesImagesTab()

    def test_collect_default(self, tab: Blb2txtArchivesImagesTab) -> None:
        """默认控件状态对应 :class:`Blb2txtConfig` 默认值。"""
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.dll_path is None
        assert cfg.dex_exclude is None
        assert cfg.dne_no_empty is False
        assert cfg.g_images is False
        assert cfg.cvr_cover is False

    def test_collect_from_controls(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """控件值正确写入 :class:`Blb2txtConfig` 对应字段。"""
        tab.dll_edit.setText("C:/path/7z.dll")
        tab.dex_edit.setText("jpg;png")
        tab.dne_check.setChecked(True)
        tab.g_check.setChecked(True)
        tab.cvr_check.setChecked(True)

        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.dll_path == "C:/path/7z.dll"
        assert cfg.dex_exclude == "jpg;png"
        assert cfg.dne_no_empty is True
        assert cfg.g_images is True
        assert cfg.cvr_cover is True

    def test_collect_empty_dll_becomes_none(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """空 DLL 路径应收集为 ``None``。"""
        tab.dll_edit.setText("   ")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.dll_path is None

    def test_collect_empty_dex_becomes_none(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """空排除扩展名应收集为 ``None``。"""
        tab.dex_edit.setText("   ")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.dex_exclude is None

    def test_apply_to_controls(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """:class:`Blb2txtConfig` 值正确还原控件状态。"""
        cfg = Blb2txtConfig.create_default()
        cfg.dll_path = "D:/libs/unrar.dll"
        cfg.dex_exclude = "bmp;gif"
        cfg.dne_no_empty = True
        cfg.g_images = True
        cfg.cvr_cover = True

        tab.apply_config(cfg)

        assert tab.dll_edit.text() == "D:/libs/unrar.dll"
        assert tab.dex_edit.text() == "bmp;gif"
        assert tab.dne_check.isChecked() is True
        assert tab.g_check.isChecked() is True
        assert tab.cvr_check.isChecked() is True

    def test_apply_none_dll_clears_field(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """``dll_path`` 为 ``None`` 时清空 DLL 文本框。"""
        tab.dll_edit.setText("stale.dll")
        cfg = Blb2txtConfig.create_default()
        cfg.dll_path = None
        tab.apply_config(cfg)
        assert tab.dll_edit.text() == ""

    def test_apply_none_dex_clears_field(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """``dex_exclude`` 为 ``None`` 时清空排除扩展名框。"""
        tab.dex_edit.setText("stale;jpg")
        cfg = Blb2txtConfig.create_default()
        cfg.dex_exclude = None
        tab.apply_config(cfg)
        assert tab.dex_edit.text() == ""

    def test_apply_false_flags_unchecks(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """3 个 flag 字段为 ``False`` 时取消勾选。"""
        tab.dne_check.setChecked(True)
        tab.g_check.setChecked(True)
        tab.cvr_check.setChecked(True)

        cfg = Blb2txtConfig.create_default()
        cfg.dne_no_empty = False
        cfg.g_images = False
        cfg.cvr_cover = False
        tab.apply_config(cfg)

        assert tab.dne_check.isChecked() is False
        assert tab.g_check.isChecked() is False
        assert tab.cvr_check.isChecked() is False


# ---------------------------------------------------------------------------
# Round-trip：apply(collect(cfg)) 一致
# ---------------------------------------------------------------------------
class TestBlb2txtArchivesImagesTabRoundTrip:
    """``apply_config`` 后再 ``collect_config`` 应与原配置一致。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtArchivesImagesTab:
        return Blb2txtArchivesImagesTab()

    def test_round_trip_full(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """全字段 round-trip：apply → collect 与原 cfg 一致。"""
        original = Blb2txtConfig.create_default()
        original.dll_path = "C:/lib/7z.dll"
        original.dex_exclude = "jpg;png;gif"
        original.dne_no_empty = True
        original.g_images = False
        original.cvr_cover = True

        tab.apply_config(original)
        round_tripped = Blb2txtConfig.create_default()
        tab.collect_config(round_tripped)

        assert round_tripped.dll_path == original.dll_path
        assert round_tripped.dex_exclude == original.dex_exclude
        assert round_tripped.dne_no_empty == original.dne_no_empty
        assert round_tripped.g_images == original.g_images
        assert round_tripped.cvr_cover == original.cvr_cover

    def test_round_trip_defaults(
        self, tab: Blb2txtArchivesImagesTab
    ) -> None:
        """默认值 round-trip：apply(默认) → collect 仍为默认。"""
        original = Blb2txtConfig.create_default()
        tab.apply_config(original)
        round_tripped = Blb2txtConfig.create_default()
        tab.collect_config(round_tripped)

        assert round_tripped.dll_path is None
        assert round_tripped.dex_exclude is None
        assert round_tripped.dne_no_empty is False
        assert round_tripped.g_images is False
        assert round_tripped.cvr_cover is False


# ---------------------------------------------------------------------------
# config_changed 信号
# ---------------------------------------------------------------------------
class TestBlb2txtArchivesImagesTabSignal:
    """控件值变化应发射 :attr:`config_changed` 信号。"""

    def test_signal_emitted_on_checkbox_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtArchivesImagesTab()
        signals: list[int] = []
        tab.config_changed.connect(lambda: signals.append(1))

        tab.g_check.setChecked(True)

        assert len(signals) >= 1

    def test_signal_emitted_on_lineedit_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtArchivesImagesTab()
        signals: list[int] = []
        tab.config_changed.connect(lambda: signals.append(1))

        tab.dll_edit.setText("C:/path.dll")

        assert len(signals) >= 1
