"""blb2txt 字典注释分组 Tab 模块。

提供 blb2txt.exe 字典与注释相关参数的 GUI 编辑：
``-d`` / ``--extract-summary`` (``-es``) / ``--skip-notes`` (``-sn``) /
``--include-notes`` (``-in``) / ``--insert-note-begin`` (``-inb``) /
``--insert-note-end`` (``-ine``)。

约束：
- 使用 PySide6（QCheckBox、QFileDialog、QFormLayout、QHBoxLayout、
  QLineEdit、QPushButton、QSpinBox、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt 原版样式。
- 控件值变化时调用 :meth:`AbstractTab._emit_changed` 发射
  :attr:`config_changed` 信号。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtDictNotesTab(AbstractTab):
    """blb2txt 字典注释参数分组 Tab。

    编辑 blb2txt.exe 的 6 个字典与注释相关参数：

    - ``-d`` (``d_dict``)：字典文件路径，:class:`QLineEdit` + 浏览按钮。
    - ``--extract-summary`` (``-es``，``extract_summary``，int | None)：
      提取摘要（0/1），:class:`QSpinBox`，值为 0 时映射到 ``None``。
    - ``--skip-notes`` (``-sn``，``skip_notes``，bool)：跳过注释，
      :class:`QCheckBox`。
    - ``--include-notes`` (``-in``，``include_notes``，int | None)：
      包含注释（0/1），:class:`QSpinBox`，值为 0 时映射到 ``None``。
    - ``--insert-note-begin`` (``-inb``，``insert_note_begin``，str | None)：
      注释开始标记，:class:`QLineEdit`。
    - ``--insert-note-end`` (``-ine``，``insert_note_end``，str | None)：
      注释结束标记，:class:`QLineEdit`。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_dict_notes"

    @classmethod
    def tab_title(cls) -> str:
        return "字典注释（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "格式选项"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("字典注释")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 字典与注释参数。"
            "字典文件 (-d, 单文件)、"
            "提取摘要 (--extract-summary / -es, 0/1, 默认 0)、"
            "跳过注释 (--skip-notes / -sn, 布尔)、"
            "包含注释 (--include-notes / -in, 0/1, 默认 1)、"
            "注释开始标记 (--insert-note-begin / -inb, 如 【 或 <!-- )、"
            "注释结束标记 (--insert-note-end / -ine, 如 】 或 --> )"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 控件读取值，写入 ``cfg`` 对应字段。"""
        cfg.d_dict = self.d_dict_edit.text().strip() or None
        es_value = self.extract_summary_spin.value()
        cfg.extract_summary = es_value if es_value != 0 else None
        cfg.skip_notes = self.skip_notes_chk.isChecked()
        in_value = self.include_notes_spin.value()
        cfg.include_notes = in_value if in_value != 0 else None
        cfg.insert_note_begin = (
            self.insert_note_begin_edit.text().strip() or None
        )
        cfg.insert_note_end = (
            self.insert_note_end_edit.text().strip() or None
        )

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""
        self.d_dict_edit.setText(cfg.d_dict or "")
        self.extract_summary_spin.setValue(
            cfg.extract_summary if cfg.extract_summary is not None else 0
        )
        self.skip_notes_chk.setChecked(bool(cfg.skip_notes))
        self.include_notes_spin.setValue(
            cfg.include_notes if cfg.include_notes is not None else 0
        )
        self.insert_note_begin_edit.setText(
            cfg.insert_note_begin or ""
        )
        self.insert_note_end_edit.setText(cfg.insert_note_end or "")

    def refresh_voices(self, voices: list[str]) -> None:
        """Blb2txtDictNotesTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """Blb2txtDictNotesTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建字典注释选项卡界面。"""
        layout = QFormLayout(self)

        # -d 字典文件路径
        d_row = QHBoxLayout()
        self.d_dict_edit = QLineEdit()
        self.d_dict_edit.setPlaceholderText("选择字典文件……")
        self.d_dict_edit.textChanged.connect(lambda: self._emit_changed())
        d_browse = QPushButton("浏览…")
        d_browse.clicked.connect(self._on_browse_d_clicked)
        d_row.addWidget(self.d_dict_edit, 1)
        d_row.addWidget(d_browse)
        layout.addRow("字典文件 (-d)：", d_row)

        # --extract-summary / -es 提取摘要（0/1）
        self.extract_summary_spin = QSpinBox()
        self.extract_summary_spin.setRange(0, 1)
        self.extract_summary_spin.setValue(0)
        self.extract_summary_spin.setSpecialValueText("默认")
        self.extract_summary_spin.setToolTip(
            "提取摘要（0/1）：0 或默认表示不输出 --extract-summary，"
            "1 表示输出 --extract-summary 1"
        )
        self.extract_summary_spin.valueChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(
            "提取摘要 (--extract-summary / -es)：", self.extract_summary_spin
        )

        # --skip-notes / -sn 跳过注释
        self.skip_notes_chk = QCheckBox(
            "跳过注释 (--skip-notes / -sn)"
        )
        self.skip_notes_chk.stateChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(self.skip_notes_chk)

        # --include-notes / -in 包含注释（0/1）
        self.include_notes_spin = QSpinBox()
        self.include_notes_spin.setRange(0, 1)
        self.include_notes_spin.setValue(0)
        self.include_notes_spin.setSpecialValueText("默认")
        self.include_notes_spin.setToolTip(
            "包含注释（0/1）：0 或默认表示不输出 --include-notes，"
            "1 表示输出 --include-notes 1"
        )
        self.include_notes_spin.valueChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(
            "包含注释 (--include-notes / -in)：", self.include_notes_spin
        )

        # --insert-note-begin / -inb 注释开始标记
        self.insert_note_begin_edit = QLineEdit()
        self.insert_note_begin_edit.setPlaceholderText(
            "如 【 或 <!-- "
        )
        self.insert_note_begin_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(
            "注释开始标记 (--insert-note-begin / -inb)：",
            self.insert_note_begin_edit,
        )

        # --insert-note-end / -ine 注释结束标记
        self.insert_note_end_edit = QLineEdit()
        self.insert_note_end_edit.setPlaceholderText("如 】 或 -->")
        self.insert_note_end_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow(
            "注释结束标记 (--insert-note-end / -ine)：",
            self.insert_note_end_edit,
        )

        self.setLayout(layout)

    def _on_browse_d_clicked(self) -> None:
        """-d 浏览按钮：选择字典文件。"""
        current = self.d_dict_edit.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字典文件",
            current or "",
            "所有文件 (*);;文本文件 (*.txt);;字典文件 (*.dic)",
        )
        if path:
            self.d_dict_edit.setText(path)


__all__ = ["Blb2txtDictNotesTab"]
