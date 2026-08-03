"""SRT 字幕选项卡模块。

提供 :class:`SrtTab`，封装 balcon SRT 相关参数的 GUI 控件，
包括创建开关、行长度、文件名与编码。

约束：
- 使用 PySide6（QCheckBox、QSpinBox、QLineEdit、QComboBox、QPushButton、
  QFileDialog、QFormLayout、QHBoxLayout、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)

# SRT 文件编码可选值
_SRT_ENCODINGS = ["ansi", "utf8", "unicode"]


class SrtTab(AbstractTab):
    """SRT 字幕选项卡。

    封装 ``-srt``、``--srt-length``、``--srt-fname``、``--srt-enc``
    字段的 GUI 控件。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "srt"

    @classmethod
    def tab_title(cls) -> str:
        return "SRT 字幕"

    @classmethod
    def tab_group(cls) -> str:
        return "字幕歌词"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("字幕歌词")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "SRT 字幕参数。"
            "创建 SRT 文件 (-srt, 布尔)、"
            "行最大长度 (--srt-length, 默认 0 = 自动)、"
            "SRT 文件名 (--srt-fname, 留空则自动生成)、"
            "SRT 编码 (--srt-enc, 可选 ansi/utf8/unicode, 默认 ansi)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """从控件读值，写入 ``cfg`` 的 SRT 相关字段。

        - QCheckBox → bool
        - QSpinBox 值 0 → None，否则 int
        - QLineEdit 空字符串 → None，否则 str
        - QComboBox 正常设值
        """
        cfg.srt = self.srt_chk.isChecked()
        length = self.srt_length_spin.value()
        cfg.srt_length = length if length != 0 else None
        fname = self.srt_fname_edit.text().strip()
        cfg.srt_fname = fname if fname else None
        cfg.srt_enc = self.srt_enc_combo.currentData()

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg`` 读值，还原 SRT 相关控件状态。"""
        self.srt_chk.setChecked(bool(cfg.srt))
        self.srt_length_spin.setValue(cfg.srt_length if cfg.srt_length is not None else 0)
        self.srt_fname_edit.setText(cfg.srt_fname or "")
        # 编码：若 cfg 值不在可选列表中，回退到 "ansi"
        enc = cfg.srt_enc if cfg.srt_enc in _SRT_ENCODINGS else "ansi"
        idx = self.srt_enc_combo.findData(enc)
        if idx >= 0:
            self.srt_enc_combo.setCurrentIndex(idx)

    def _build_ui(self) -> None:
        """构建 SRT 选项卡界面。"""
        # 创建 SRT 文件
        self.srt_chk = QCheckBox("创建 SRT 文件 (-srt)", self)
        self.srt_chk.toggled.connect(lambda: self._emit_changed())

        # 行最大长度
        self.srt_length_spin = QSpinBox(self)
        self.srt_length_spin.setRange(0, 1000)
        self.srt_length_spin.setSpecialValueText("自动")
        self.srt_length_spin.setValue(0)
        self.srt_length_spin.valueChanged.connect(lambda: self._emit_changed())

        # SRT 文件名 + 浏览按钮
        self.srt_fname_edit = QLineEdit(self)
        self.srt_fname_edit.setPlaceholderText("留空则自动生成 .srt 文件名")
        self.srt_fname_edit.textChanged.connect(lambda: self._emit_changed())
        self.srt_fname_browse_btn = QPushButton("浏览…", self)
        self.srt_fname_browse_btn.clicked.connect(self._browse_srt_fname)
        fname_row = QHBoxLayout()
        fname_row.addWidget(self.srt_fname_edit, 1)
        fname_row.addWidget(self.srt_fname_browse_btn)
        fname_container = QWidget(self)
        fname_container.setLayout(fname_row)

        # SRT 编码
        self.srt_enc_combo = QComboBox(self)
        self.srt_enc_combo.addItem("ANSI", "ansi")
        self.srt_enc_combo.addItem("UTF-8", "utf8")
        self.srt_enc_combo.addItem("Unicode", "unicode")
        self.srt_enc_combo.setCurrentIndex(0)
        self.srt_enc_combo.currentIndexChanged.connect(lambda: self._emit_changed())

        # 表单布局
        form = QFormLayout(self)
        form.addRow(self.srt_chk)
        form.addRow("行最大长度 (--srt-length)：", self.srt_length_spin)
        form.addRow("SRT 文件名 (--srt-fname)：", fname_container)
        form.addRow("SRT 编码 (--srt-enc)：", self.srt_enc_combo)
        self.setLayout(form)

    def _browse_srt_fname(self) -> None:
        """打开保存文件对话框，选择 SRT 输出文件。"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择 SRT 文件",
            "",
            "SRT 文件 (*.srt);;所有文件 (*.*)",
        )
        if path:
            self.srt_fname_edit.setText(path)


__all__ = ["SrtTab"]
