"""文本过滤选项卡模块。

提供 :class:`TextFilterTab`，封装 balcon 文本过滤相关参数的 GUI 控件，
包括各类括号、URL 与注释的忽略开关。

约束：
- 使用 PySide6（QCheckBox、QGridLayout、QGroupBox、QHBoxLayout、QPushButton、
  QVBoxLayout、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class TextFilterTab(AbstractTab):
    """文本过滤选项卡。

    封装 ``--ignore-square-brackets``、``--ignore-curly-brackets``、
    ``--ignore-angle-brackets``、``--ignore-round-brackets``、
    ``--ignore-url``、``--ignore-comments`` 字段的 GUI 控件。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "text_filter"

    @classmethod
    def tab_title(cls) -> str:
        return "文本过滤"

    @classmethod
    def tab_group(cls) -> str:
        return "高级"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("高级")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "文本过滤规则（均为布尔开关, 默认全部关闭）。"
            "忽略 [方括号] 内文本 (--ignore-square-brackets)、"
            "忽略 {花括号} 内文本 (--ignore-curly-brackets)、"
            "忽略 <尖括号> 内文本 (--ignore-angle-brackets)、"
            "忽略 (圆括号) 内文本 (--ignore-round-brackets)、"
            "忽略 URL (--ignore-url)、"
            "忽略注释 // 和 /* */ (--ignore-comments)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """将 6 个 QCheckBox 的 isChecked 赋值对应字段。"""
        cfg.ignore_square_brackets = self.square_brackets_chk.isChecked()
        cfg.ignore_curly_brackets = self.curly_brackets_chk.isChecked()
        cfg.ignore_angle_brackets = self.angle_brackets_chk.isChecked()
        cfg.ignore_round_brackets = self.round_brackets_chk.isChecked()
        cfg.ignore_url = self.url_chk.isChecked()
        cfg.ignore_comments = self.comments_chk.isChecked()

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg`` 读值，还原 6 个 QCheckBox 状态。"""
        self.square_brackets_chk.setChecked(bool(cfg.ignore_square_brackets))
        self.curly_brackets_chk.setChecked(bool(cfg.ignore_curly_brackets))
        self.angle_brackets_chk.setChecked(bool(cfg.ignore_angle_brackets))
        self.round_brackets_chk.setChecked(bool(cfg.ignore_round_brackets))
        self.url_chk.setChecked(bool(cfg.ignore_url))
        self.comments_chk.setChecked(bool(cfg.ignore_comments))

    def _build_ui(self) -> None:
        """构建文本过滤选项卡界面。"""
        self.square_brackets_chk = QCheckBox(
            "忽略 [方括号] 内文本", self
        )
        self.square_brackets_chk.setToolTip(
            "忽略 [方括号] 内的文本 (--ignore-square-brackets)。例如：[注释] 会被跳过"
        )
        self.square_brackets_chk.toggled.connect(lambda: self._emit_changed())

        self.curly_brackets_chk = QCheckBox(
            "忽略 {花括号} 内文本", self
        )
        self.curly_brackets_chk.setToolTip(
            "忽略 {花括号} 内的文本 (--ignore-curly-brackets)。例如：{变量名} 会被跳过"
        )
        self.curly_brackets_chk.toggled.connect(lambda: self._emit_changed())

        self.angle_brackets_chk = QCheckBox(
            "忽略 <尖括号> 内文本", self
        )
        self.angle_brackets_chk.setToolTip(
            "忽略 <尖括号> 内的文本 (--ignore-angle-brackets)。例如：<tag> 会被跳过"
        )
        self.angle_brackets_chk.toggled.connect(lambda: self._emit_changed())

        self.round_brackets_chk = QCheckBox(
            "忽略 (圆括号) 内文本", self
        )
        self.round_brackets_chk.setToolTip(
            "忽略 (圆括号) 内的文本 (--ignore-round-brackets)。例如：(注释) 会被跳过"
        )
        self.round_brackets_chk.toggled.connect(lambda: self._emit_changed())

        self.url_chk = QCheckBox("忽略 URL", self)
        self.url_chk.setToolTip(
            "忽略 URL (--ignore-url)。例如：https://example.com 会被跳过"
        )
        self.url_chk.toggled.connect(lambda: self._emit_changed())

        self.comments_chk = QCheckBox(
            "忽略注释 // 和 /* */", self
        )
        self.comments_chk.setToolTip(
            "忽略注释 (--ignore-comments)。例如：// 行注释 和 /* 块注释 */ 会被跳过"
        )
        self.comments_chk.toggled.connect(lambda: self._emit_changed())

        # 6 个 CheckBox 用 1 列 QGridLayout 排列（6 行 x 1 列）
        grid = QGridLayout()
        grid.addWidget(self.square_brackets_chk, 0, 0)
        grid.addWidget(self.curly_brackets_chk, 1, 0)
        grid.addWidget(self.angle_brackets_chk, 2, 0)
        grid.addWidget(self.round_brackets_chk, 3, 0)
        grid.addWidget(self.url_chk, 4, 0)
        grid.addWidget(self.comments_chk, 5, 0)

        filter_group = QGroupBox("文本过滤规则", self)
        filter_group.setLayout(grid)

        # 全选 / 全不选 按钮
        self.select_all_btn = QPushButton("全选", self)
        self.select_all_btn.clicked.connect(self._select_all)
        self.unselect_all_btn = QPushButton("全不选", self)
        self.unselect_all_btn.clicked.connect(self._unselect_all)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.unselect_all_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(filter_group)
        layout.addLayout(btn_row)
        layout.addStretch()
        self.setLayout(layout)

    def _select_all(self) -> None:
        """勾选全部 6 个过滤规则 CheckBox。"""
        self.square_brackets_chk.setChecked(True)
        self.curly_brackets_chk.setChecked(True)
        self.angle_brackets_chk.setChecked(True)
        self.round_brackets_chk.setChecked(True)
        self.url_chk.setChecked(True)
        self.comments_chk.setChecked(True)

    def _unselect_all(self) -> None:
        """取消勾选全部 6 个过滤规则 CheckBox。"""
        self.square_brackets_chk.setChecked(False)
        self.curly_brackets_chk.setChecked(False)
        self.angle_brackets_chk.setChecked(False)
        self.round_brackets_chk.setChecked(False)
        self.url_chk.setChecked(False)
        self.comments_chk.setChecked(False)


__all__ = ["TextFilterTab"]
