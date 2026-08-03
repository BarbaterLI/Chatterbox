"""blb2txt 输入分组 Tab 模块。

提供 blb2txt.exe 输入相关参数的 GUI 编辑：输入文件 / 文件列表 /
STDIN / 递归子目录 / 相对路径 / 输入编码 / 密码。

约束：
- 使用 PySide6（QWidget、QLineEdit、QCheckBox、QComboBox 等）。
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
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtInputTab(AbstractTab):
    """blb2txt 输入参数分组 Tab。

    编辑 blb2txt 输入相关 7 个参数：``-f``、``-fl``、``-i``、``-s``、
    ``-x``、``-if``、``-pwd``。其中 ``-f`` 控件设为只读，由主窗口文件
    列表自动填充；其余控件由用户直接编辑。

    :meth:`collect_config` / :meth:`apply_config` 操作 :class:`Blb2txtConfig`，
    字段名与配置类声明完全一致（``f_files``、``fl_file_list``、``i_stdin``、
    ``s_recursive``、``x_relative``、``if_encoding``、``pwd_password``）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_input"

    @classmethod
    def tab_title(cls) -> str:
        return "输入（blb2txt）"

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
            "blb2txt 输入参数。"
            "输入文件 (-f, 多文件, 由主窗口文件列表填充)、"
            "文件列表 (-fl, 文本文件, 每行一个路径)、"
            "从 STDIN 读取 (-i, 布尔)、"
            "递归子目录 (-s, 布尔)、"
            "使用相对路径 (-x, 布尔)、"
            "输入编码 (-if, 可选 ansi/utf-8/utf-16/utf-16le/utf-16be, 默认自动)、"
            "密码 (-pwd, 用于加密文档)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从控件读取值，写入 :class:`Blb2txtConfig` 对应字段。"""
        cfg.f_files = self._split_files(self.files_edit.text())
        cfg.fl_file_list = self.file_list_edit.text().strip() or None
        cfg.i_stdin = self.stdin_check.isChecked()
        cfg.s_recursive = self.recursive_check.isChecked()
        cfg.x_relative = self.relative_check.isChecked()
        enc = self.encoding_combo.currentData()
        cfg.if_encoding = enc if enc else None
        cfg.pwd_password = self.password_edit.text() or None

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 :class:`Blb2txtConfig` 读取值，还原控件状态。"""
        self.files_edit.setText(", ".join(cfg.f_files))
        self.file_list_edit.setText(cfg.fl_file_list or "")
        self.stdin_check.setChecked(cfg.i_stdin)
        self.recursive_check.setChecked(cfg.s_recursive)
        self.relative_check.setChecked(cfg.x_relative)
        if cfg.if_encoding is None:
            self.encoding_combo.setCurrentIndex(0)
        else:
            idx = self.encoding_combo.findData(cfg.if_encoding)
            if idx >= 0:
                self.encoding_combo.setCurrentIndex(idx)
            else:
                # 未知编码值：回退到"自动"
                self.encoding_combo.setCurrentIndex(0)
        self.password_edit.setText(cfg.pwd_password or "")

    def refresh_voices(self, voices: list[str]) -> None:
        """Blb2txtInputTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """Blb2txtInputTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # -f 输入文件（只读，由主窗口文件列表填充）
        self.files_edit = QLineEdit()
        self.files_edit.setReadOnly(True)
        self.files_edit.setPlaceholderText("由文件列表自动填充（多文件以逗号分隔）")
        self.files_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("输入文件 (-f)：", self.files_edit)

        # -fl 文件列表（txt 文件，每行一个路径）
        fl_row = QHBoxLayout()
        self.file_list_edit = QLineEdit()
        self.file_list_edit.setPlaceholderText(
            "选择文件列表 .txt（每行一个文件路径）"
        )
        self.file_list_edit.textChanged.connect(lambda: self._emit_changed())
        fl_browse_btn = QPushButton("浏览…")
        fl_browse_btn.clicked.connect(self._on_browse_file_list)
        fl_row.addWidget(self.file_list_edit, 1)
        fl_row.addWidget(fl_browse_btn)
        layout.addRow("文件列表 (-fl)：", fl_row)

        # -i 从 stdin 读取
        self.stdin_check = QCheckBox("从 STDIN 读取 (-i)")
        self.stdin_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.stdin_check)

        # -s 递归子目录
        self.recursive_check = QCheckBox("递归子目录 (-s)")
        self.recursive_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.recursive_check)

        # -x 相对路径
        self.relative_check = QCheckBox("使用相对路径 (-x)")
        self.relative_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.relative_check)

        # -if 输入编码
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItem("自动", None)
        self.encoding_combo.addItem("ANSI", "ansi")
        self.encoding_combo.addItem("UTF-8", "utf-8")
        self.encoding_combo.addItem("UTF-16", "utf-16")
        self.encoding_combo.addItem("UTF-16 LE", "utf-16le")
        self.encoding_combo.addItem("UTF-16 BE", "utf-16be")
        self.encoding_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("输入编码 (-if)：", self.encoding_combo)

        # -pwd 密码
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("加密文档的密码")
        self.password_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("密码 (-pwd)：", self.password_edit)

        self.setLayout(layout)

    def _on_browse_file_list(self) -> None:
        """浏览按钮点击：弹出文件列表文件选择对话框。"""
        current = self.file_list_edit.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文件列表",
            current or "",
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if path:
            self.file_list_edit.setText(path)

    @staticmethod
    def _split_files(text: str) -> list[str]:
        """按逗号或分号分割文件路径，忽略空串与首尾空白。"""
        if not text:
            return []
        result: list[str] = []
        for part in text.replace(";", ",").split(","):
            item = part.strip()
            if item:
                result.append(item)
        return result


__all__ = ["Blb2txtInputTab"]
