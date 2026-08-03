"""blb2txt 输出参数分组 Tab 模块。

提供 blb2txt.exe 输出相关 12 个参数的 GUI 编辑：
``-v`` / ``-p`` / ``-ext`` / ``-out`` / ``-o`` / ``-u`` / ``-b`` /
``-a`` / ``-n`` / ``-e`` / ``-cf`` / ``-cft``。

布局优化（Task 4）：
- 12 个参数用 3 个 :class:`QGroupBox` 分组：「输出路径」/「编码格式」/「覆盖模式」
- ``-o`` / ``-u`` / ``-b`` / ``-a`` 4 个 checkbox 用 2x2 :class:`QGridLayout` 紧凑排布
- 浏览按钮使用 :class:`QToolButton`（比 QPushButton 更紧凑，自动支持图标）
- 各组内部使用 :class:`QFormLayout` 自动对齐 label

``-v``（输出目录）与 ``-out``（输出到单一文件）的互斥语义由
:meth:`Blb2txtConfig.to_args` 决定优先级，本 Tab 允许两者同时填写。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtOutputTab(AbstractTab):
    """blb2txt 输出参数分组 Tab。

    编辑 blb2txt.exe 的 12 个输出相关参数：
    ``-v`` (输出目录)、``-p`` (文件名前缀)、``-ext`` (输出扩展名)、
    ``-out`` (输出到单一文件)、``-o`` (覆盖)、``-u`` (子目录)、
    ``-b`` (备份)、``-a`` (追加)、``-n`` (命名模式)、``-e`` (输出编码)、
    ``-cf`` (控制台输出)、``-cft`` (控制台类型)。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_output"

    @classmethod
    def tab_title(cls) -> str:
        return "输出（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "输入输出"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("输入输出")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 输出参数。"
            "输出目录 (-v)、"
            "文件名前缀 (-p)、"
            "输出扩展名 (-ext, 默认 txt)、"
            "输出到单一文件 (-out)、"
            "覆盖已存在文件 (-o, 布尔)、"
            "输出到子目录 (-u, 布尔)、"
            "备份已存在文件 (-b, 布尔)、"
            "追加到已存在文件 (-a, 布尔)、"
            "命名模式 (-n, 可选 1=原名 / 2=原名_序号 / 3=序号, 默认 1)、"
            "输出编码 (-e, 可选 ansi/utf8/utf8b/utf16/utf16be/utf16le, 默认 ansi)、"
            "控制台输出 (-cf, 可选 YES/NO/STOP, 默认 YES)、"
            "控制台类型 (-cft, 可选 txt/html, 默认 txt)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 控件读取值，写入 ``cfg`` 对应字段。"""
        cfg.v_output = self.v_edit.text().strip() or None
        cfg.p_prefix = self.p_edit.text().strip() or None
        cfg.ext_extension = self.ext_edit.text().strip() or None
        cfg.out_file = self.out_edit.text().strip() or None
        cfg.o_overwrite = self.o_check.isChecked()
        cfg.u_subdir = self.u_check.isChecked()
        cfg.b_backup = self.b_check.isChecked()
        cfg.a_append = self.a_check.isChecked()
        n_value = self.n_spin.value()
        cfg.n_naming = n_value if n_value != 0 else None
        e_value = self.e_combo.currentData()
        cfg.e_encoding = e_value if e_value else None
        cf_value = self.cf_combo.currentData()
        cfg.cf_console_file = cf_value if cf_value else None
        cft_value = self.cft_combo.currentData()
        cfg.cft_console_type = cft_value if cft_value else None

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""
        self.v_edit.setText(cfg.v_output or "")
        self.p_edit.setText(cfg.p_prefix or "")
        self.ext_edit.setText(cfg.ext_extension or "")
        self.out_edit.setText(cfg.out_file or "")
        self.o_check.setChecked(cfg.o_overwrite)
        self.u_check.setChecked(cfg.u_subdir)
        self.b_check.setChecked(cfg.b_backup)
        self.a_check.setChecked(cfg.a_append)
        self.n_spin.setValue(
            cfg.n_naming if cfg.n_naming is not None else 0
        )
        self._set_combo_by_data(self.e_combo, cfg.e_encoding)
        self._set_combo_by_data(self.cf_combo, cfg.cf_console_file)
        self._set_combo_by_data(self.cft_combo, cfg.cft_console_type)

    def refresh_voices(self, voices: list[str]) -> None:
        """Blb2txtOutputTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """Blb2txtOutputTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建 3 个 QGroupBox 分组的输出参数界面。"""
        outer = QFormLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # === QGroupBox 1: 输出路径（-v / -p / -ext / -out）===
        path_group = QGroupBox("输出路径", self)
        path_form = QFormLayout(path_group)
        path_form.setContentsMargins(8, 12, 8, 8)

        # -v 输出目录
        self.v_edit = QLineEdit()
        self.v_edit.setPlaceholderText("选择输出目录……")
        self.v_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.v_edit.textChanged.connect(lambda: self._emit_changed())
        v_browse = self._make_browse_toolbutton()
        v_browse.clicked.connect(self._on_browse_v_clicked)
        v_row = QHBoxLayout()
        v_row.setContentsMargins(0, 0, 0, 0)
        v_row.addWidget(self.v_edit, 1)
        v_row.addWidget(v_browse)
        v_container = QWidget()
        v_container.setLayout(v_row)
        path_form.addRow("输出目录 (-v)：", v_container)

        # -p 文件名前缀
        self.p_edit = QLineEdit()
        self.p_edit.setPlaceholderText("如 out_")
        self.p_edit.textChanged.connect(lambda: self._emit_changed())
        path_form.addRow("文件名前缀 (-p)：", self.p_edit)

        # -ext 输出扩展名
        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText("如 txt")
        self.ext_edit.textChanged.connect(lambda: self._emit_changed())
        path_form.addRow("输出扩展名 (-ext)：", self.ext_edit)

        # -out 输出到单一文件
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("选择输出文件……")
        self.out_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.out_edit.textChanged.connect(lambda: self._emit_changed())
        out_browse = self._make_browse_toolbutton()
        out_browse.clicked.connect(self._on_browse_out_clicked)
        out_row = QHBoxLayout()
        out_row.setContentsMargins(0, 0, 0, 0)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(out_browse)
        out_container = QWidget()
        out_container.setLayout(out_row)
        path_form.addRow("输出到单一文件 (-out)：", out_container)

        path_group.setLayout(path_form)
        outer.addRow(path_group)

        # === QGroupBox 2: 覆盖模式（-o / -u / -b / -a 2x2 网格 + -n）===
        overwrite_group = QGroupBox("覆盖模式", self)
        overwrite_layout = QFormLayout(overwrite_group)
        overwrite_layout.setContentsMargins(8, 12, 8, 8)

        # 4 个 checkbox 用 2x2 QGridLayout 紧凑排布
        checkbox_grid = QGridLayout()
        checkbox_grid.setContentsMargins(0, 0, 0, 0)
        checkbox_grid.setHorizontalSpacing(16)
        checkbox_grid.setVerticalSpacing(4)

        self.o_check = QCheckBox("覆盖已存在文件 (-o)", self)
        self.o_check.stateChanged.connect(lambda: self._emit_changed())
        checkbox_grid.addWidget(self.o_check, 0, 0)

        self.u_check = QCheckBox("输出到子目录 (-u)", self)
        self.u_check.stateChanged.connect(lambda: self._emit_changed())
        checkbox_grid.addWidget(self.u_check, 0, 1)

        self.b_check = QCheckBox("备份已存在文件 (-b)", self)
        self.b_check.stateChanged.connect(lambda: self._emit_changed())
        checkbox_grid.addWidget(self.b_check, 1, 0)

        self.a_check = QCheckBox("追加到已存在文件 (-a)", self)
        self.a_check.stateChanged.connect(lambda: self._emit_changed())
        checkbox_grid.addWidget(self.a_check, 1, 1)

        checkbox_container = QWidget()
        checkbox_container.setLayout(checkbox_grid)
        overwrite_layout.addRow(checkbox_container)

        # -n 命名模式（1=原名，2=原名_序号，3=序号；0 表示默认不输出）
        self.n_spin = QSpinBox()
        self.n_spin.setRange(0, 3)
        self.n_spin.setValue(0)
        self.n_spin.setSpecialValueText("默认")
        self.n_spin.setToolTip(
            "命名模式：1=原名，2=原名_序号，3=序号；0 或默认表示不输出 -n"
        )
        self.n_spin.valueChanged.connect(lambda: self._emit_changed())
        overwrite_layout.addRow("命名模式 (-n)：", self.n_spin)

        overwrite_group.setLayout(overwrite_layout)
        outer.addRow(overwrite_group)

        # === QGroupBox 3: 编码格式（-e / -cf / -cft）===
        encoding_group = QGroupBox("编码格式", self)
        encoding_form = QFormLayout(encoding_group)
        encoding_form.setContentsMargins(8, 12, 8, 8)

        # -e 输出编码
        self.e_combo = QComboBox()
        self.e_combo.addItem("默认", None)
        self.e_combo.addItem("ANSI", "ansi")
        self.e_combo.addItem("UTF-8", "utf8")
        self.e_combo.addItem("UTF-8 (BOM)", "utf8b")
        self.e_combo.addItem("UTF-16", "utf16")
        self.e_combo.addItem("UTF-16BE", "utf16be")
        self.e_combo.addItem("UTF-16LE", "utf16le")
        self.e_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        encoding_form.addRow("输出编码 (-e)：", self.e_combo)

        # -cf 控制台输出
        self.cf_combo = QComboBox()
        self.cf_combo.addItem("默认", None)
        self.cf_combo.addItem("YES", "YES")
        self.cf_combo.addItem("NO", "NO")
        self.cf_combo.addItem("STOP", "STOP")
        self.cf_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        encoding_form.addRow("控制台输出 (-cf)：", self.cf_combo)

        # -cft 控制台类型
        self.cft_combo = QComboBox()
        self.cft_combo.addItem("默认", None)
        self.cft_combo.addItem("txt", "txt")
        self.cft_combo.addItem("html", "html")
        self.cft_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        encoding_form.addRow("控制台类型 (-cft)：", self.cft_combo)

        encoding_group.setLayout(encoding_form)
        outer.addRow(encoding_group)

        self.setLayout(outer)

    def _make_browse_toolbutton(self) -> QToolButton:
        """创建行内浏览按钮（QToolButton 紧凑，自动支持图标）。"""
        btn = QToolButton(self)
        btn.setText("浏览…")
        btn.setToolTip("浏览选择")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        return btn

    def _on_browse_v_clicked(self) -> None:
        """-v 浏览按钮：选择输出目录。"""
        current = self.v_edit.text().strip()
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", current or ""
        )
        if path:
            self.v_edit.setText(path)

    def _on_browse_out_clicked(self) -> None:
        """-out 浏览按钮：选择输出文件。"""
        current = self.out_edit.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            current or "",
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if path:
            self.out_edit.setText(path)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, data: object) -> None:
        """按 userData 还原 QComboBox 当前项；未匹配则置 index 0。"""
        if data is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)


__all__ = ["Blb2txtOutputTab"]
