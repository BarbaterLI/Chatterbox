"""输入分组 Tab 模块。

提供文本输入相关参数的 GUI 编辑：剪贴板 / STDIN / 命令行文本 /
行号选择 / 文本编码。

Task 4d 优化（Qt6 原生控件升级）：
- 命令行文本 -t 与行号范围 -ln 改用 :class:`QPlainTextEdit`（非 QTextEdit），
  避免富文本开销，支持纯文本编辑与 ``setMaximumBlockCount`` 限制最大行数。
- 保留 :class:`QComboBox` 离散档位选择（编码格式）。
- 保留 :class:`QCheckBox` 布尔开关。

约束：
- 使用 PySide6（QCheckBox、QComboBox、QFormLayout、QPlainTextEdit、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt6 原版样式。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)

# 多行文本控件最大块数（防止内存膨胀）
_MAX_BLOCK_COUNT = 1000


class InputTab(AbstractTab):
    """输入参数分组 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "input"

    @classmethod
    def tab_title(cls) -> str:
        return "输入"

    @classmethod
    def tab_group(cls) -> str:
        return "输入输出"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("输入输出")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "文本输入参数（同时勾选时优先级 -c > -i > -f > -t）。"
            "输入文件 (-f, 多文件)、"
            "文件列表 (-fl)、"
            "从剪贴板获取 (-c)、"
            "命令行文本 (-t, 每行一条)、"
            "从 STDIN 获取 (-i)、"
            "行号范围 (-ln, 如 26-34, 仅对文件输入有效)、"
            "文本编码 (--encoding, 可选 ansi/utf8/unicode, 默认自动)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        cfg.c_clipboard = self.clipboard_check.isChecked()
        cfg.i_stdin = self.stdin_check.isChecked()
        cfg.t_texts = self._split_lines(self.texts_edit.toPlainText())
        cfg.ln_lines = self._split_lines(self.lines_edit.toPlainText())
        enc = self.encoding_combo.currentData()
        cfg.encoding = enc if enc else None

    def apply_config(self, cfg: BalconConfig) -> None:
        self.clipboard_check.setChecked(cfg.c_clipboard)
        self.stdin_check.setChecked(cfg.i_stdin)
        self.texts_edit.setPlainText("\n".join(cfg.t_texts))
        self.lines_edit.setPlainText("\n".join(cfg.ln_lines))
        if cfg.encoding is None:
            self.encoding_combo.setCurrentIndex(0)
        else:
            idx = self.encoding_combo.findData(cfg.encoding)
            if idx >= 0:
                self.encoding_combo.setCurrentIndex(idx)

    def refresh_voices(self, voices: list[str]) -> None:
        """InputTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """InputTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # SubTask 7.1: 输入源互斥优先级提示（QPalette 灰色 + 小号字体，非 QSS）
        hint_label = QLabel("同时勾选时优先级：-c > -i > -f > -t")
        hint_font = hint_label.font()
        hint_font.setPointSizeF(max(hint_font.pointSizeF() - 1.0, 1.0))
        hint_label.setFont(hint_font)
        hint_palette = hint_label.palette()
        gray_color = hint_palette.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText
        )
        hint_palette.setColor(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.WindowText,
            gray_color,
        )
        hint_palette.setColor(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.WindowText,
            gray_color,
        )
        hint_label.setPalette(hint_palette)
        layout.addRow(hint_label)

        self.clipboard_check = QCheckBox("从剪贴板获取文本 (-c)")
        # SubTask 7.5: 剪贴板输入 tooltip
        self.clipboard_check.setToolTip("从剪贴板获取文本 (-c)")
        self.clipboard_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(self.clipboard_check)

        self.stdin_check = QCheckBox("从 STDIN 获取 (-i)")
        # SubTask 7.5: 标准输入 tooltip
        self.stdin_check.setToolTip("从标准输入获取文本 (-i)")
        self.stdin_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.stdin_check)

        # 命令行文本 -t：使用 QPlainTextEdit 避免富文本开销
        self.texts_edit = QPlainTextEdit()
        self.texts_edit.setPlaceholderText(
            "每行一条 -t 文本（命令行直接输入的文本）"
        )
        # SubTask 7.3: -t 文本 tooltip
        self.texts_edit.setToolTip("直接输入要朗读的文本，每行一段")
        self.texts_edit.setMaximumBlockCount(_MAX_BLOCK_COUNT)
        self.texts_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("命令行文本 (-t)：", self.texts_edit)

        # 行号范围 -ln：使用 QPlainTextEdit 避免富文本开销
        self.lines_edit = QPlainTextEdit()
        self.lines_edit.setPlaceholderText(
            '每行一个行号范围，如 "26-34"（仅对文件输入有效）'
        )
        # SubTask 7.2: -ln 行号范围 tooltip
        self.lines_edit.setToolTip(
            "指定读取行数范围，格式『起始-结束』（如 26-34）或单行号（如 5）。"
            "仅对文件输入 (-f/-fl) 有效"
        )
        self.lines_edit.setMaximumBlockCount(_MAX_BLOCK_COUNT)
        self.lines_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("行号范围 (-ln)：", self.lines_edit)

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItem("自动", None)
        self.encoding_combo.addItem("ANSI", "ansi")
        self.encoding_combo.addItem("UTF-8", "utf8")
        self.encoding_combo.addItem("Unicode", "unicode")
        # SubTask 7.4: 编码 ComboBox tooltip + 各项 tooltip
        encoding_tooltip = (
            "输入文本编码\n"
            "- ANSI：Windows 系统代码页（如 GBK）\n"
            "- UTF-8\n"
            "- Unicode"
        )
        self.encoding_combo.setToolTip(encoding_tooltip)
        self.encoding_combo.setItemData(
            0, "自动检测输入文件编码（balcon 默认行为）", Qt.ToolTipRole
        )
        self.encoding_combo.setItemData(
            1, "ANSI：Windows 系统代码页（如 GBK）", Qt.ToolTipRole
        )
        self.encoding_combo.setItemData(
            2, "UTF-8：通用 Unicode 编码", Qt.ToolTipRole
        )
        self.encoding_combo.setItemData(
            3, "Unicode：UTF-16 LE 编码", Qt.ToolTipRole
        )
        self.encoding_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("文本编码 (--encoding)：", self.encoding_combo)

        self.setLayout(layout)

    @staticmethod
    def _split_lines(text: str) -> list[str]:
        """按行分割文本，忽略空行与首尾空白。"""
        return [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]


__all__ = ["InputTab"]
