"""blb2txt EML 邮件选项卡模块。

提供 :class:`Blb2txtEmlTab`，封装 blb2txt EML 邮件相关参数的 GUI 控件，
包括保存 EML、保存附件、包含抄送、日期/发件人/主题/收件人格式、原始格式、
保留 RTF 共 9 个参数。

约束：
- 使用 PySide6（QCheckBox、QFormLayout、QLineEdit、QWidget）。
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
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractParamTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class Blb2txtEmlTab(AbstractParamTab):
    """blb2txt EML 邮件选项卡。

    封装 ``--eml-save``、``--eml-att``、``--eml-cc``、``--eml-date``、
    ``--eml-from``、``--eml-org``、``--eml-rt``、``--eml-subj``、
    ``--eml-to`` 共 9 个 EML 相关参数的 GUI 控件。

    控件映射：
        - 5 个 flag（``--eml-save`` / ``--eml-att`` / ``--eml-cc`` /
          ``--eml-org`` / ``--eml-rt``）使用 :class:`QCheckBox`。
        - 4 个 str 字段（``--eml-date`` / ``--eml-from`` / ``--eml-subj`` /
          ``--eml-to``）使用 :class:`QLineEdit`，空字符串映射到 ``None``
          （避免生成 ``--eml-date ""`` 等空值参数）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_eml"

    @classmethod
    def tab_title(cls) -> str:
        return "EML（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "格式选项"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("EML")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt EML 邮件参数。"
            "保存 EML (--eml-save, 布尔)、"
            "保存附件 (--eml-att, 布尔)、"
            "包含抄送 (--eml-cc, 布尔)、"
            "日期格式 (--eml-date, 留空不启用)、"
            "发件人格式 (--eml-from, 留空不启用)、"
            "原始格式 (--eml-org, 布尔)、"
            "保留 RTF (--eml-rt, 布尔)、"
            "主题格式 (--eml-subj, 留空不启用)、"
            "收件人格式 (--eml-to, 留空不启用)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 的控件读取值，写入 ``cfg`` 对应字段。"""
        cfg.eml_save = self.eml_save_chk.isChecked()
        cfg.eml_att = self.eml_att_chk.isChecked()
        cfg.eml_cc = self.eml_cc_chk.isChecked()
        cfg.eml_date = self.eml_date_edit.text().strip() or None
        cfg.eml_from = self.eml_from_edit.text().strip() or None
        cfg.eml_org = self.eml_org_chk.isChecked()
        cfg.eml_rt = self.eml_rt_chk.isChecked()
        cfg.eml_subj = self.eml_subj_edit.text().strip() or None
        cfg.eml_to = self.eml_to_edit.text().strip() or None

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""
        self.eml_save_chk.setChecked(bool(cfg.eml_save))
        self.eml_att_chk.setChecked(bool(cfg.eml_att))
        self.eml_cc_chk.setChecked(bool(cfg.eml_cc))
        self.eml_date_edit.setText(cfg.eml_date or "")
        self.eml_from_edit.setText(cfg.eml_from or "")
        self.eml_org_chk.setChecked(bool(cfg.eml_org))
        self.eml_rt_chk.setChecked(bool(cfg.eml_rt))
        self.eml_subj_edit.setText(cfg.eml_subj or "")
        self.eml_to_edit.setText(cfg.eml_to or "")

    def _build_ui(self) -> None:
        """构建 EML 邮件选项卡界面。"""
        layout = QFormLayout(self)

        # --eml-save 保存 EML
        self.eml_save_chk = QCheckBox("保存 EML (--eml-save)", self)
        self.eml_save_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.eml_save_chk)

        # --eml-att 保存附件
        self.eml_att_chk = QCheckBox("保存附件 (--eml-att)", self)
        self.eml_att_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.eml_att_chk)

        # --eml-cc 包含抄送
        self.eml_cc_chk = QCheckBox("包含抄送 (--eml-cc)", self)
        self.eml_cc_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.eml_cc_chk)

        # --eml-date 日期格式
        self.eml_date_edit = QLineEdit(self)
        self.eml_date_edit.setPlaceholderText(
            "日期格式（留空表示不启用 --eml-date）"
        )
        self.eml_date_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("日期格式 (--eml-date)：", self.eml_date_edit)

        # --eml-from 发件人格式
        self.eml_from_edit = QLineEdit(self)
        self.eml_from_edit.setPlaceholderText(
            "发件人格式（留空表示不启用 --eml-from）"
        )
        self.eml_from_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("发件人格式 (--eml-from)：", self.eml_from_edit)

        # --eml-org 原始格式
        self.eml_org_chk = QCheckBox("原始格式 (--eml-org)", self)
        self.eml_org_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.eml_org_chk)

        # --eml-rt 保留 RTF
        self.eml_rt_chk = QCheckBox("保留 RTF (--eml-rt)", self)
        self.eml_rt_chk.toggled.connect(lambda: self._emit_changed())
        layout.addRow(self.eml_rt_chk)

        # --eml-subj 主题格式
        self.eml_subj_edit = QLineEdit(self)
        self.eml_subj_edit.setPlaceholderText(
            "主题格式（留空表示不启用 --eml-subj）"
        )
        self.eml_subj_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("主题格式 (--eml-subj)：", self.eml_subj_edit)

        # --eml-to 收件人格式
        self.eml_to_edit = QLineEdit(self)
        self.eml_to_edit.setPlaceholderText(
            "收件人格式（留空表示不启用 --eml-to）"
        )
        self.eml_to_edit.textChanged.connect(lambda: self._emit_changed())
        layout.addRow("收件人格式 (--eml-to)：", self.eml_to_edit)

        self.setLayout(layout)


__all__ = ["Blb2txtEmlTab"]
