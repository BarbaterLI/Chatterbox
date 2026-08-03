"""blb2txt_input_tab 模块单元测试。

验证 :class:`Blb2txtInputTab` 的元信息（``tab_id`` / ``tab_title`` /
``tab_group`` / ``tab_tool``）、7 个参数控件的存在性，以及控件与
:class:`Blb2txtConfig` 之间的 collect/apply 往返一致性。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.tabs.base_tab import AbstractTab
from balcon_batch_tts.gui.tabs.blb2txt_input_tab import Blb2txtInputTab


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
class TestBlb2txtInputTabMeta:
    """``Blb2txtInputTab`` 类元信息。"""

    def test_tab_id(self) -> None:
        assert Blb2txtInputTab.tab_id() == "blb2txt_input"

    def test_tab_title(self) -> None:
        assert Blb2txtInputTab.tab_title() == "输入（blb2txt）"

    def test_tab_group(self) -> None:
        assert Blb2txtInputTab.tab_group() == "输入输出"

    def test_tab_tool_returns_blb2txt(self) -> None:
        """``tab_tool`` 应返回 :attr:`ToolType.BLB2TXT`。"""
        assert Blb2txtInputTab.tab_tool() is ToolType.BLB2TXT

    def test_tab_tool_is_classmethod(self) -> None:
        """``tab_tool`` 应为 classmethod（可由类对象直接调用）。"""
        assert isinstance(Blb2txtInputTab.__dict__["tab_tool"], classmethod)

    def test_inherits_abstract_tab(self) -> None:
        assert issubclass(Blb2txtInputTab, AbstractTab)

    def test_tab_icon_returns_qicon(self, qapp: QApplication) -> None:
        """``tab_icon`` 应返回分组"输入输出"对应的 QIcon。

        SVG 渲染依赖 QGuiApplication，故请求 ``qapp`` fixture。
        """
        from PySide6.QtGui import QIcon

        icon = Blb2txtInputTab.tab_icon()
        assert isinstance(icon, QIcon)


# ---------------------------------------------------------------------------
# 控件存在性（7 个参数控件）
# ---------------------------------------------------------------------------
class TestBlb2txtInputTabControls:
    """``Blb2txtInputTab`` 包含 7 个参数控件。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtInputTab:
        return Blb2txtInputTab()

    def test_seven_param_controls_exist(self, tab: Blb2txtInputTab) -> None:
        """Tab 应包含 -f、-fl、-i、-s、-x、-if、-pwd 7 个参数控件。"""
        assert hasattr(tab, "files_edit")        # -f
        assert hasattr(tab, "file_list_edit")    # -fl
        assert hasattr(tab, "stdin_check")       # -i
        assert hasattr(tab, "recursive_check")   # -s
        assert hasattr(tab, "relative_check")    # -x
        assert hasattr(tab, "encoding_combo")    # -if
        assert hasattr(tab, "password_edit")     # -pwd

    def test_files_edit_is_readonly(self, tab: Blb2txtInputTab) -> None:
        """-f 控件应设为只读（由主窗口文件列表填充）。"""
        assert tab.files_edit.isReadOnly() is True

    def test_password_uses_password_echo(self, tab: Blb2txtInputTab) -> None:
        """-pwd 控件应使用密码回显模式。"""
        assert tab.password_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_encoding_combo_has_auto_default(self, tab: Blb2txtInputTab) -> None:
        """-if 编码下拉首项应为"自动"（currentData 为 None）。"""
        assert tab.encoding_combo.currentIndex() == 0
        assert tab.encoding_combo.currentData() is None


# ---------------------------------------------------------------------------
# collect_config / apply_config
# ---------------------------------------------------------------------------
class TestBlb2txtInputTabCollectApply:
    """``Blb2txtInputTab`` 控件与 :class:`Blb2txtConfig` 的 collect/apply。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtInputTab:
        return Blb2txtInputTab()

    def test_collect_default(self, tab: Blb2txtInputTab) -> None:
        """默认控件状态对应 :class:`Blb2txtConfig` 默认值。"""
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.f_files == []
        assert cfg.fl_file_list is None
        assert cfg.i_stdin is False
        assert cfg.s_recursive is False
        assert cfg.x_relative is False
        assert cfg.if_encoding is None
        assert cfg.pwd_password is None

    def test_collect_from_controls(self, tab: Blb2txtInputTab) -> None:
        """控件值正确写入 :class:`Blb2txtConfig` 对应字段。"""
        # -f 是只读控件，通过 setText 模拟主窗口填充（含逗号与分号混合）
        tab.files_edit.setText("a.pdf, b.docx; c.epub")
        tab.file_list_edit.setText("list.txt")
        tab.stdin_check.setChecked(True)
        tab.recursive_check.setChecked(True)
        tab.relative_check.setChecked(True)
        tab.encoding_combo.setCurrentIndex(2)  # UTF-8
        tab.password_edit.setText("secret")

        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)

        assert cfg.f_files == ["a.pdf", "b.docx", "c.epub"]
        assert cfg.fl_file_list == "list.txt"
        assert cfg.i_stdin is True
        assert cfg.s_recursive is True
        assert cfg.x_relative is True
        assert cfg.if_encoding == "utf-8"
        assert cfg.pwd_password == "secret"

    def test_collect_empty_password_becomes_none(
        self, tab: Blb2txtInputTab
    ) -> None:
        """空密码应收集为 ``None``（不产生 -pwd 参数）。"""
        tab.password_edit.setText("")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.pwd_password is None

    def test_collect_empty_file_list_becomes_none(
        self, tab: Blb2txtInputTab
    ) -> None:
        """空文件列表应收集为 ``None``。"""
        tab.file_list_edit.setText("   ")
        cfg = Blb2txtConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.fl_file_list is None

    def test_apply_to_controls(self, tab: Blb2txtInputTab) -> None:
        """:class:`Blb2txtConfig` 值正确还原控件状态。"""
        cfg = Blb2txtConfig.create_default()
        cfg.f_files = ["x.pdf", "y.docx"]
        cfg.fl_file_list = "files.txt"
        cfg.i_stdin = True
        cfg.s_recursive = True
        cfg.x_relative = True
        cfg.if_encoding = "utf-16"
        cfg.pwd_password = "pass123"

        tab.apply_config(cfg)

        assert tab.files_edit.text() == "x.pdf, y.docx"
        assert tab.file_list_edit.text() == "files.txt"
        assert tab.stdin_check.isChecked() is True
        assert tab.recursive_check.isChecked() is True
        assert tab.relative_check.isChecked() is True
        assert tab.encoding_combo.currentData() == "utf-16"
        assert tab.password_edit.text() == "pass123"

    def test_apply_none_encoding_resets_to_auto(
        self, tab: Blb2txtInputTab
    ) -> None:
        """``if_encoding`` 为 ``None`` 时还原为"自动"项。"""
        cfg = Blb2txtConfig.create_default()
        cfg.if_encoding = None
        tab.apply_config(cfg)
        assert tab.encoding_combo.currentIndex() == 0
        assert tab.encoding_combo.currentData() is None

    def test_apply_unknown_encoding_resets_to_auto(
        self, tab: Blb2txtInputTab
    ) -> None:
        """未知编码值还原时回退到"自动"。"""
        cfg = Blb2txtConfig.create_default()
        cfg.if_encoding = "klingon"
        tab.apply_config(cfg)
        assert tab.encoding_combo.currentIndex() == 0

    def test_apply_none_password_clears_field(
        self, tab: Blb2txtInputTab
    ) -> None:
        """``pwd_password`` 为 ``None`` 时清空密码框。"""
        tab.password_edit.setText("stale")
        cfg = Blb2txtConfig.create_default()
        cfg.pwd_password = None
        tab.apply_config(cfg)
        assert tab.password_edit.text() == ""

    def test_apply_empty_files_clears_field(self, tab: Blb2txtInputTab) -> None:
        """``f_files`` 为空列表时清空 -f 文本框。"""
        tab.files_edit.setText("stale.pdf")
        cfg = Blb2txtConfig.create_default()
        cfg.f_files = []
        tab.apply_config(cfg)
        assert tab.files_edit.text() == ""


# ---------------------------------------------------------------------------
# Round-trip：apply(collect(cfg)) 一致
# ---------------------------------------------------------------------------
class TestBlb2txtInputTabRoundTrip:
    """``apply_config`` 后再 ``collect_config`` 应与原配置一致。"""

    @pytest.fixture
    def tab(self, qapp: QApplication) -> Blb2txtInputTab:
        return Blb2txtInputTab()

    def test_round_trip_full(self, tab: Blb2txtInputTab) -> None:
        """全字段 round-trip：apply → collect 与原 cfg 一致。"""
        original = Blb2txtConfig.create_default()
        original.f_files = ["book1.pdf", "book2.epub"]
        original.fl_file_list = "list.txt"
        original.i_stdin = False
        original.s_recursive = True
        original.x_relative = False
        original.if_encoding = "ansi"
        original.pwd_password = "pw"

        tab.apply_config(original)
        round_tripped = Blb2txtConfig.create_default()
        tab.collect_config(round_tripped)

        assert round_tripped.f_files == original.f_files
        assert round_tripped.fl_file_list == original.fl_file_list
        assert round_tripped.i_stdin == original.i_stdin
        assert round_tripped.s_recursive == original.s_recursive
        assert round_tripped.x_relative == original.x_relative
        assert round_tripped.if_encoding == original.if_encoding
        assert round_tripped.pwd_password == original.pwd_password

    def test_round_trip_defaults(self, tab: Blb2txtInputTab) -> None:
        """默认值 round-trip：apply(默认) → collect 仍为默认。"""
        original = Blb2txtConfig.create_default()
        tab.apply_config(original)
        round_tripped = Blb2txtConfig.create_default()
        tab.collect_config(round_tripped)

        assert round_tripped.f_files == []
        assert round_tripped.fl_file_list is None
        assert round_tripped.i_stdin is False
        assert round_tripped.s_recursive is False
        assert round_tripped.x_relative is False
        assert round_tripped.if_encoding is None
        assert round_tripped.pwd_password is None


# ---------------------------------------------------------------------------
# config_changed 信号
# ---------------------------------------------------------------------------
class TestBlb2txtInputTabSignal:
    """控件值变化应发射 :attr:`config_changed` 信号。"""

    def test_signal_emitted_on_checkbox_change(
        self, qapp: QApplication
    ) -> None:
        tab = Blb2txtInputTab()
        signals: list[int] = []
        tab.config_changed.connect(lambda: signals.append(1))

        tab.stdin_check.setChecked(True)

        assert len(signals) >= 1
