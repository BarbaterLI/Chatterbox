"""blb2txt 文本分割选项卡模块。

提供 :class:`Blb2txtSplitTab`，封装 blb2txt 文本分割相关参数的 GUI 控件，
包括按主题/关键词/字符数分割、递归、子目录写入、目录生成、片段连接、
保留 HTML 标题等 10 个参数。

约束：
- 使用 PySide6（QCheckBox、QFormLayout、QLineEdit、QSpinBox、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt6 原版样式。
- 控件事件连接使用 :meth:`AbstractTab._emit_changed`。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractParamTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtSplitTab(AbstractParamTab):
    """blb2txt 文本分割选项卡。

    封装 ``-t``、``-k``、``-r``、``-w``、``-l``、``-c``、``-toc``、
    ``-m``、``-j``、``-hh`` 共 10 个分割相关参数的 GUI 控件。

    控件映射：
        - 6 个 flag（``-t`` / ``-r`` / ``-w`` / ``-toc`` / ``-j`` / ``-hh``）
          使用 :class:`QCheckBox`。
        - ``-k``（关键词，多个用 ``;`` 分隔）使用 :class:`QLineEdit`。
        - ``-l`` / ``-c`` / ``-m``（int）使用 :class:`QSpinBox`，复用
          :meth:`AbstractParamTab._collect_int` / :meth:`_apply_int`
          辅助方法，spinbox 值为 0 时对应 ``None``。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_split"

    @classmethod
    def tab_title(cls) -> str:
        return "文本分割（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "文本处理"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("文本处理")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 文本分割参数。"
            "按主题分割 (-t, 布尔)、"
            "关键词分割 (-k, 多个用 ; 分隔)、"
            "递归分割 (-r, 布尔)、"
            "分割后写入子目录 (-w, 布尔)、"
            "分割级别 (-l, 默认 1)、"
            "按字符数分割 (-c, 0 = 不启用)、"
            "生成目录 (-toc, 布尔)、"
            "最小分割长度 (-m, 默认 512, 0 = 不启用)、"
            "连接分割片段 (-j, 布尔)、"
            "保留 HTML 标题 (-hh, 布尔)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 的控件读取值，写入 ``cfg`` 对应字段。"""
        cfg.t_topic = self.t_topic_chk.isChecked()
        cfg.k_keywords = self.k_keywords_edit.text().strip() or None
        cfg.r_recursive = self.r_recursive_chk.isChecked()
        cfg.w_subdir = self.w_subdir_chk.isChecked()
        self._collect_int(cfg, "-l", self.l_level_spin)
        self._collect_int(cfg, "-c", self.c_chars_spin)
        cfg.toc = self.toc_chk.isChecked()
        self._collect_int(cfg, "-m", self.m_min_length_spin)
        cfg.j_join = self.j_join_chk.isChecked()
        cfg.hh_html = self.hh_html_chk.isChecked()

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""
        self.t_topic_chk.setChecked(bool(cfg.t_topic))
        self.k_keywords_edit.setText(cfg.k_keywords or "")
        self.r_recursive_chk.setChecked(bool(cfg.r_recursive))
        self.w_subdir_chk.setChecked(bool(cfg.w_subdir))
        self._apply_int(cfg, "-l", self.l_level_spin)
        self._apply_int(cfg, "-c", self.c_chars_spin)
        self.toc_chk.setChecked(bool(cfg.toc))
        self._apply_int(cfg, "-m", self.m_min_length_spin)
        self.j_join_chk.setChecked(bool(cfg.j_join))
        self.hh_html_chk.setChecked(bool(cfg.hh_html))

    def _build_ui(self) -> None:
        """构建文本分割选项卡界面。"""
        layout = QFormLayout(self)

        # -t 按主题分割
        self.t_topic_chk = QCheckBox("按主题分割 (-t)", self)
        self.t_topic_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.t_topic_chk)

        # -k 关键词分割
        self.k_keywords_edit = QLineEdit(self)
        self.k_keywords_edit.setPlaceholderText(
            "关键词，多个用 ; 分隔（留空表示不启用 -k）"
        )
        self.k_keywords_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("关键词分割 (-k)：", self.k_keywords_edit)

        # -r 递归分割
        self.r_recursive_chk = QCheckBox("递归分割 (-r)", self)
        self.r_recursive_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.r_recursive_chk)

        # -w 分割后写入子目录
        self.w_subdir_chk = QCheckBox("分割后写入子目录 (-w)", self)
        self.w_subdir_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.w_subdir_chk)

        # -l 分割级别（默认 1）
        self.l_level_spin = QSpinBox(self)
        self.l_level_spin.setRange(0, 99)
        self.l_level_spin.setValue(1)
        self.l_level_spin.setToolTip(
            "分割级别（0 表示不启用 -l，对应 None）"
        )
        self.l_level_spin.valueChanged.connect(lambda: self._emit_changed())
        layout.addRow("分割级别 (-l)：", self.l_level_spin)

        # -c 按字符数分割
        self.c_chars_spin = QSpinBox(self)
        self.c_chars_spin.setRange(0, 999999)
        self.c_chars_spin.setValue(0)
        self.c_chars_spin.setToolTip(
            "按字符数分割（0 表示不启用 -c，对应 None）"
        )
        self.c_chars_spin.valueChanged.connect(lambda: self._emit_changed())
        layout.addRow("字符数分割 (-c)：", self.c_chars_spin)

        # -toc 生成目录
        self.toc_chk = QCheckBox("生成目录 (-toc)", self)
        self.toc_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.toc_chk)

        # -m 最小分割长度（默认 512）
        self.m_min_length_spin = QSpinBox(self)
        self.m_min_length_spin.setRange(0, 999999)
        self.m_min_length_spin.setValue(512)
        self.m_min_length_spin.setToolTip(
            "最小分割长度（0 表示不启用 -m，对应 None）"
        )
        self.m_min_length_spin.valueChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("最小分割长度 (-m)：", self.m_min_length_spin)

        # -j 连接分割片段
        self.j_join_chk = QCheckBox("连接分割片段 (-j)", self)
        self.j_join_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.j_join_chk)

        # -hh 保留 HTML 标题
        self.hh_html_chk = QCheckBox("保留 HTML 标题 (-hh)", self)
        self.hh_html_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.hh_html_chk)

        self.setLayout(layout)


__all__ = ["Blb2txtSplitTab"]
