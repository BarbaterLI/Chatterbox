"""input_tab 模块单元测试。

验证 Task 4d 的 QPlainTextEdit 升级：
- ``texts_edit`` 与 ``lines_edit`` 控件类型为 :class:`QPlainTextEdit`（非 QTextEdit）
- ``setMaximumBlockCount`` 已设置（防止内存膨胀）
- ``collect_config`` / ``apply_config`` 功能正常
- ``_split_lines`` 辅助方法行为正确
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.gui.tabs.input_tab import InputTab


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 控件类型断言
# ---------------------------------------------------------------------------
class TestControlTypes:
    """验证 InputTab 使用 QPlainTextEdit 而非 QTextEdit。"""

    def test_texts_edit_is_qplaintextedit(self, qapp: QApplication) -> None:
        """命令行文本输入控件应为 QPlainTextEdit 实例。"""
        tab = InputTab()
        assert isinstance(tab.texts_edit, QPlainTextEdit), (
            "texts_edit 应为 QPlainTextEdit 实例（非 QTextEdit）"
        )

    def test_lines_edit_is_qplaintextedit(self, qapp: QApplication) -> None:
        """行号范围输入控件应为 QPlainTextEdit 实例。"""
        tab = InputTab()
        assert isinstance(tab.lines_edit, QPlainTextEdit), (
            "lines_edit 应为 QPlainTextEdit 实例（非 QTextEdit）"
        )

    def test_texts_edit_max_block_count_set(self, qapp: QApplication) -> None:
        """``texts_edit`` 应设置 ``maximumBlockCount`` 限制最大行数。"""
        tab = InputTab()
        assert tab.texts_edit.maximumBlockCount() > 0, (
            "texts_edit 应通过 setMaximumBlockCount 限制最大行数"
        )

    def test_lines_edit_max_block_count_set(self, qapp: QApplication) -> None:
        """``lines_edit`` 应设置 ``maximumBlockCount`` 限制最大行数。"""
        tab = InputTab()
        assert tab.lines_edit.maximumBlockCount() > 0, (
            "lines_edit 应通过 setMaximumBlockCount 限制最大行数"
        )


# ---------------------------------------------------------------------------
# Tab 元信息
# ---------------------------------------------------------------------------
class TestTabMeta:
    """验证 Tab 元信息方法。"""

    def test_tab_id(self) -> None:
        assert InputTab.tab_id() == "input"

    def test_tab_title(self) -> None:
        assert InputTab.tab_title() == "输入"

    def test_tab_group(self) -> None:
        assert InputTab.tab_group() == "输入输出"


# ---------------------------------------------------------------------------
# collect_config / apply_config 行为
# ---------------------------------------------------------------------------
class TestConfigRoundTrip:
    """验证 collect_config / apply_config 在 QPlainTextEdit 上的往返。"""

    def test_collect_texts_multiline(self, qapp: QApplication) -> None:
        """多行 -t 文本应按行分割为 list[str]，忽略空行。"""
        tab = InputTab()
        tab.texts_edit.setPlainText("hello\nworld\n\n")
        cfg = BalconConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.t_texts == ["hello", "world"]

    def test_collect_lines_multiline(self, qapp: QApplication) -> None:
        """多行 -ln 范围应按行分割为 list[str]，忽略空行与首尾空白。"""
        tab = InputTab()
        tab.lines_edit.setPlainText("  26-34  \n10-20\n\n")
        cfg = BalconConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.ln_lines == ["26-34", "10-20"]

    def test_apply_texts_multiline(self, qapp: QApplication) -> None:
        """apply_config 应将 list[str] 还原为多行 QPlainTextEdit 内容。"""
        tab = InputTab()
        cfg = BalconConfig.create_default()
        cfg.t_texts = ["hello", "world"]
        tab.apply_config(cfg)
        assert tab.texts_edit.toPlainText() == "hello\nworld"

    def test_apply_lines_multiline(self, qapp: QApplication) -> None:
        """apply_config 应将 list[str] 还原为多行 QPlainTextEdit 内容。"""
        tab = InputTab()
        cfg = BalconConfig.create_default()
        cfg.ln_lines = ["1-10", "20-30"]
        tab.apply_config(cfg)
        assert tab.lines_edit.toPlainText() == "1-10\n20-30"

    def test_round_trip_preserves_state(self, qapp: QApplication) -> None:
        """collect → apply → collect 应保持数据一致。"""
        tab = InputTab()
        tab.texts_edit.setPlainText("foo\nbar\nbaz")
        tab.lines_edit.setPlainText("1-2\n3-4")
        tab.clipboard_check.setChecked(True)
        tab.stdin_check.setChecked(False)
        tab.encoding_combo.setCurrentIndex(2)  # UTF-8

        cfg = BalconConfig.create_default()
        tab.collect_config(cfg)
        assert cfg.t_texts == ["foo", "bar", "baz"]
        assert cfg.ln_lines == ["1-2", "3-4"]
        assert cfg.c_clipboard is True
        assert cfg.i_stdin is False
        assert cfg.encoding == "utf8"

        # 应用到新 Tab
        tab2 = InputTab()
        tab2.apply_config(cfg)
        assert tab2.texts_edit.toPlainText() == "foo\nbar\nbaz"
        assert tab2.lines_edit.toPlainText() == "1-2\n3-4"
        assert tab2.clipboard_check.isChecked() is True
        assert tab2.stdin_check.isChecked() is False
        assert tab2.encoding_combo.currentData() == "utf8"


# ---------------------------------------------------------------------------
# _split_lines 辅助方法
# ---------------------------------------------------------------------------
class TestSplitLines:
    """验证 ``_split_lines`` 静态方法。"""

    def test_split_lines_basic(self) -> None:
        assert InputTab._split_lines("a\nb\nc") == ["a", "b", "c"]

    def test_split_lines_strips_whitespace(self) -> None:
        assert InputTab._split_lines("  a  \n b \n") == ["a", "b"]

    def test_split_lines_ignores_empty_lines(self) -> None:
        assert InputTab._split_lines("a\n\n\nb\n") == ["a", "b"]

    def test_split_lines_empty_string(self) -> None:
        assert InputTab._split_lines("") == []

    def test_split_lines_only_whitespace(self) -> None:
        assert InputTab._split_lines("   \n  \n") == []
