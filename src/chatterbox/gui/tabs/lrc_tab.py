"""LRC 歌词选项卡模块。

提供 :class:`LrcTab`，封装 balcon LRC 相关参数的 GUI 控件，
包括创建开关、行长度、文件名、编码、时间偏移与各 ID3 标签等。

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
    QGroupBox,
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

# LRC 文件编码可选值
_LRC_ENCODINGS = ["ansi", "utf8", "unicode"]


class LrcTab(AbstractTab):
    """LRC 歌词选项卡。

    封装 ``-lrc``、``--lrc-length``、``--lrc-fname``、``--lrc-enc``、
    ``--lrc-offset`` 及各 ID3 标签字段的 GUI 控件。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "lrc"

    @classmethod
    def tab_title(cls) -> str:
        return "LRC 歌词"

    @classmethod
    def tab_group(cls) -> str:
        return "字幕歌词"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("字幕歌词")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "LRC 歌词参数。"
            "创建 LRC 文件 (-lrc, 布尔)、"
            "行最大长度 (--lrc-length, 默认 0 = 自动)、"
            "LRC 文件名 (--lrc-fname, 留空则自动生成)、"
            "LRC 编码 (--lrc-enc, 可选 ansi/utf8/unicode, 默认 ansi)、"
            "时间偏移 (--lrc-offset, 范围 -60000~60000, 默认 0, 单位毫秒)、"
            "artist 标签 (--lrc-artist)、"
            "album 标签 (--lrc-album)、"
            "title 标签 (--lrc-title)、"
            "author 标签 (--lrc-author)、"
            "creator 标签 (--lrc-creator)、"
            "句后插入空行 (--lrc-sent, 布尔)、"
            "段后插入空行 (--lrc-para, 布尔)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """从控件读值，写入 ``cfg`` 的 LRC 相关字段。

        - QCheckBox → bool
        - QSpinBox 值 0 → None，否则 int
        - QLineEdit 空字符串 → None，否则 str
        - QComboBox 正常设值
        """
        cfg.lrc = self.lrc_chk.isChecked()
        length = self.lrc_length_spin.value()
        cfg.lrc_length = length if length != 0 else None
        fname = self.lrc_fname_edit.text().strip()
        cfg.lrc_fname = fname if fname else None
        cfg.lrc_enc = self.lrc_enc_combo.currentData()
        cfg.lrc_offset = self.lrc_offset_spin.value()
        artist = self.lrc_artist_edit.text().strip()
        cfg.lrc_artist = artist if artist else None
        album = self.lrc_album_edit.text().strip()
        cfg.lrc_album = album if album else None
        title = self.lrc_title_edit.text().strip()
        cfg.lrc_title = title if title else None
        author = self.lrc_author_edit.text().strip()
        cfg.lrc_author = author if author else None
        creator = self.lrc_creator_edit.text().strip()
        cfg.lrc_creator = creator if creator else None
        cfg.lrc_sent = self.lrc_sent_chk.isChecked()
        cfg.lrc_para = self.lrc_para_chk.isChecked()

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg`` 读值，还原 LRC 相关控件状态。"""
        self.lrc_chk.setChecked(bool(cfg.lrc))
        self.lrc_length_spin.setValue(cfg.lrc_length if cfg.lrc_length is not None else 0)
        self.lrc_fname_edit.setText(cfg.lrc_fname or "")
        # 编码：若 cfg 值不在可选列表中，回退到 "ansi"
        enc = cfg.lrc_enc if cfg.lrc_enc in _LRC_ENCODINGS else "ansi"
        idx = self.lrc_enc_combo.findData(enc)
        if idx >= 0:
            self.lrc_enc_combo.setCurrentIndex(idx)
        self.lrc_offset_spin.setValue(cfg.lrc_offset if cfg.lrc_offset is not None else 0)
        self.lrc_artist_edit.setText(cfg.lrc_artist or "")
        self.lrc_album_edit.setText(cfg.lrc_album or "")
        self.lrc_title_edit.setText(cfg.lrc_title or "")
        self.lrc_author_edit.setText(cfg.lrc_author or "")
        self.lrc_creator_edit.setText(cfg.lrc_creator or "")
        self.lrc_sent_chk.setChecked(bool(cfg.lrc_sent))
        self.lrc_para_chk.setChecked(bool(cfg.lrc_para))

    def _build_ui(self) -> None:
        """构建 LRC 选项卡界面。"""
        # 创建 LRC 文件
        self.lrc_chk = QCheckBox("创建 LRC 文件 (-lrc)", self)
        self.lrc_chk.toggled.connect(lambda: self._emit_changed())

        # 行最大长度
        self.lrc_length_spin = QSpinBox(self)
        self.lrc_length_spin.setRange(0, 1000)
        self.lrc_length_spin.setSpecialValueText("自动")
        self.lrc_length_spin.setValue(0)
        self.lrc_length_spin.valueChanged.connect(lambda: self._emit_changed())

        # LRC 文件名 + 浏览按钮
        self.lrc_fname_edit = QLineEdit(self)
        self.lrc_fname_edit.setPlaceholderText("留空则自动生成 .lrc 文件名")
        self.lrc_fname_edit.setMinimumWidth(80)
        self.lrc_fname_edit.textChanged.connect(lambda: self._emit_changed())
        self.lrc_fname_browse_btn = QPushButton("浏览…", self)
        self.lrc_fname_browse_btn.clicked.connect(self._browse_lrc_fname)
        fname_row = QHBoxLayout()
        fname_row.addWidget(self.lrc_fname_edit, 1)
        fname_row.addWidget(self.lrc_fname_browse_btn)
        fname_container = QWidget(self)
        fname_container.setLayout(fname_row)

        # LRC 编码
        self.lrc_enc_combo = QComboBox(self)
        self.lrc_enc_combo.addItem("ANSI", "ansi")
        self.lrc_enc_combo.addItem("UTF-8", "utf8")
        self.lrc_enc_combo.addItem("Unicode", "unicode")
        self.lrc_enc_combo.setCurrentIndex(0)
        self.lrc_enc_combo.setMinimumWidth(70)
        self.lrc_enc_combo.currentIndexChanged.connect(lambda: self._emit_changed())

        # 时间偏移
        self.lrc_offset_spin = QSpinBox(self)
        self.lrc_offset_spin.setRange(-60000, 60000)
        self.lrc_offset_spin.setSuffix(" ms")
        self.lrc_offset_spin.setToolTip("LRC 时间偏移。负值=提前显示，正值=延后显示，单位毫秒")
        self.lrc_offset_spin.setValue(0)
        self.lrc_offset_spin.setMinimumWidth(70)
        self.lrc_offset_spin.valueChanged.connect(lambda: self._emit_changed())

        # ID3 标签
        self.lrc_artist_edit = QLineEdit(self)
        self.lrc_artist_edit.setMinimumWidth(80)
        self.lrc_artist_edit.textChanged.connect(lambda: self._emit_changed())
        self.lrc_album_edit = QLineEdit(self)
        self.lrc_album_edit.setMinimumWidth(80)
        self.lrc_album_edit.textChanged.connect(lambda: self._emit_changed())
        self.lrc_title_edit = QLineEdit(self)
        self.lrc_title_edit.setMinimumWidth(80)
        self.lrc_title_edit.textChanged.connect(lambda: self._emit_changed())
        self.lrc_author_edit = QLineEdit(self)
        self.lrc_author_edit.setMinimumWidth(80)
        self.lrc_author_edit.textChanged.connect(lambda: self._emit_changed())
        self.lrc_creator_edit = QLineEdit(self)
        self.lrc_creator_edit.setMinimumWidth(80)
        self.lrc_creator_edit.textChanged.connect(lambda: self._emit_changed())

        # 句后/段后插入空行
        self.lrc_sent_chk = QCheckBox("句后插入空行 (--lrc-sent)", self)
        self.lrc_sent_chk.toggled.connect(lambda: self._emit_changed())
        self.lrc_para_chk = QCheckBox("段后插入空行 (--lrc-para)", self)
        self.lrc_para_chk.toggled.connect(lambda: self._emit_changed())

        # 表单布局
        form = QFormLayout(self)
        form.addRow(self.lrc_chk)
        form.addRow("行最大长度 (--lrc-length)：", self.lrc_length_spin)
        form.addRow("LRC 文件名 (--lrc-fname)：", fname_container)
        form.addRow("LRC 编码 (--lrc-enc)：", self.lrc_enc_combo)
        form.addRow("时间偏移 (--lrc-offset)：", self.lrc_offset_spin)

        # ID3 标签分组
        id3_group = QGroupBox("ID3 标签", self)
        id3_form = QFormLayout(id3_group)
        id3_form.addRow("artist 标签：", self.lrc_artist_edit)
        id3_form.addRow("album 标签：", self.lrc_album_edit)
        id3_form.addRow("title 标签：", self.lrc_title_edit)
        id3_form.addRow("author 标签：", self.lrc_author_edit)
        id3_form.addRow("creator 标签：", self.lrc_creator_edit)
        form.addRow(id3_group)

        form.addRow(self.lrc_sent_chk)
        form.addRow(self.lrc_para_chk)
        self.setLayout(form)

    def _browse_lrc_fname(self) -> None:
        """打开保存文件对话框，选择 LRC 输出文件。"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择 LRC 文件",
            "",
            "LRC 文件 (*.lrc);;所有文件 (*.*)",
        )
        if path:
            self.lrc_fname_edit.setText(path)


__all__ = ["LrcTab"]
