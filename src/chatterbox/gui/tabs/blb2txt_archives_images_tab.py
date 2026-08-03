"""blb2txt 归档图像分组 Tab 模块。

提供 blb2txt.exe 归档与图像相关参数的 GUI 编辑：
``-dll`` / ``-dex`` / ``-dne`` / ``-g`` / ``-cvr``。

约束：
- 使用 PySide6（QWidget、QLineEdit、QCheckBox、QFileDialog 等）。
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
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtArchivesImagesTab(AbstractTab):
    """blb2txt 归档图像参数分组 Tab。

    编辑 blb2txt.exe 的 5 个归档与图像相关参数：
    ``-dll`` (DLL 路径，用于 ZIP/RAR)、``-dex`` (排除文件扩展名列表)、
    ``-dne`` (不提取空文件)、``-g`` (提取图像)、``-cvr`` (提取封面)。

    :meth:`collect_config` / :meth:`apply_config` 操作 :class:`Blb2txtConfig`，
    字段名与配置类声明完全一致（``dll_path``、``dex_exclude``、
    ``dne_no_empty``、``g_images``、``cvr_cover``）。空字符串的 ``-dll`` /
    ``-dex`` 收集为 ``None``，避免产生冗余命令行参数。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_archives_images"

    @classmethod
    def tab_title(cls) -> str:
        return "归档图像（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "高级"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("归档图像")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 归档与图像参数。"
            "DLL 路径 (-dll, 用于解压 ZIP/RAR)、"
            "排除文件扩展名 (-dex, 多个以 ; 分隔, 如 jpg;png)、"
            "不提取空文件 (-dne, 布尔)、"
            "提取图像 (-g, 布尔)、"
            "提取封面 (-cvr, 布尔)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 控件读取值，写入 :class:`Blb2txtConfig` 对应字段。"""
        cfg.dll_path = self.dll_edit.text().strip() or None
        cfg.dex_exclude = self.dex_edit.text().strip() or None
        cfg.dne_no_empty = self.dne_check.isChecked()
        cfg.g_images = self.g_check.isChecked()
        cfg.cvr_cover = self.cvr_check.isChecked()

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 :class:`Blb2txtConfig` 读取值，还原本 Tab 控件状态。"""
        self.dll_edit.setText(cfg.dll_path or "")
        self.dex_edit.setText(cfg.dex_exclude or "")
        self.dne_check.setChecked(cfg.dne_no_empty)
        self.g_check.setChecked(cfg.g_images)
        self.cvr_check.setChecked(cfg.cvr_cover)

    def refresh_voices(self, voices: list[str]) -> None:
        """Blb2txtArchivesImagesTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """Blb2txtArchivesImagesTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # -dll DLL 路径（用于 ZIP/RAR）
        dll_row = QHBoxLayout()
        self.dll_edit = QLineEdit()
        self.dll_edit.setPlaceholderText("选择解压 DLL 文件路径……")
        self.dll_edit.textChanged.connect(lambda: self._emit_changed())
        dll_browse = QPushButton("浏览…")
        dll_browse.clicked.connect(self._on_browse_dll_clicked)
        dll_row.addWidget(self.dll_edit, 1)
        dll_row.addWidget(dll_browse)
        layout.addRow("DLL 路径 (-dll)：", dll_row)

        # -dex 排除文件扩展名列表
        self.dex_edit = QLineEdit()
        self.dex_edit.setPlaceholderText("多个扩展名以 ; 分隔，如 jpg;png")
        self.dex_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("排除扩展名 (-dex)：", self.dex_edit)

        # -dne 不提取空文件
        self.dne_check = QCheckBox("不提取空文件 (-dne)")
        self.dne_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.dne_check)

        # -g 提取图像
        self.g_check = QCheckBox("提取图像 (-g)")
        self.g_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.g_check)

        # -cvr 提取封面
        self.cvr_check = QCheckBox("提取封面 (-cvr)")
        self.cvr_check.stateChanged.connect(lambda: self._emit_changed())
        layout.addRow(self.cvr_check)

        self.setLayout(layout)

    def _on_browse_dll_clicked(self) -> None:
        """-dll 浏览按钮：选择 DLL 文件。"""
        current = self.dll_edit.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 DLL 文件",
            current or "",
            "动态链接库 (*.dll);;所有文件 (*)",
        )
        if path:
            self.dll_edit.setText(path)


__all__ = ["Blb2txtArchivesImagesTab"]
