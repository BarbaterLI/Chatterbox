"""blb2txt 表格 CSV 选项卡模块。

提供 :class:`Blb2txtTablesCsvTab`，封装 blb2txt 表格提取与 CSV 分隔符
相关的 7 个参数的 GUI 控件，包括 ``-et`` 提取表格（0/1）与 6 个 CSV
flag（``--csv-comma`` / ``--csv-semicolon`` / ``--csv-space`` /
``--csv-tab`` / ``--csv-double-quote`` / ``--csv-single-quote``）。

约束：
- 使用 PySide6（QCheckBox、QFormLayout、QSpinBox、QWidget）。
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
    QSpinBox,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractParamTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


# 6 个 CSV flag 字段定义：(属性后缀, 字段名, 选项名, 中文标签)
# 顺序与 Blb2txtConfig.CSV 分组字段声明顺序一致。
_CSV_FIELDS: list[tuple[str, str, str, str]] = [
    ("csv_comma", "csv_comma", "--csv-comma", "CSV 逗号分隔"),
    ("csv_semicolon", "csv_semicolon", "--csv-semicolon", "CSV 分号分隔"),
    ("csv_space", "csv_space", "--csv-space", "CSV 空格分隔"),
    ("csv_tab", "csv_tab", "--csv-tab", "CSV 制表符分隔"),
    ("csv_double_quote", "csv_double_quote", "--csv-double-quote", "CSV 双引号"),
    ("csv_single_quote", "csv_single_quote", "--csv-single-quote", "CSV 单引号"),
]


class Blb2txtTablesCsvTab(AbstractParamTab):
    """blb2txt 表格 CSV 选项卡。

    封装 ``-et`` 与 6 个 CSV flag 共 7 个参数的 GUI 控件。

    控件映射：
        - ``-et``（``extract_tables``，int | None）使用 :class:`QSpinBox`，
          范围 0-1；spinbox 值为 0 时对应 ``None``（不启用 ``-et``），
          为 1 时对应 ``-et 1``。复用 :meth:`AbstractParamTab._collect_int`
          / :meth:`_apply_int` 辅助方法。
        - 6 个 CSV flag（bool）使用 :class:`QCheckBox`，默认未勾选。

    注意：
        6 个 CSV 分隔符 flag（逗号 / 分号 / 空格 / 制表符）在实际使用中
        通常是互斥的，但本 Tab 不强制互斥逻辑，由用户自行选择组合。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_tables_csv"

    @classmethod
    def tab_title(cls) -> str:
        return "表格CSV（blb2txt）"

    @classmethod
    def tab_group(cls) -> str:
        return "格式选项"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BLB2TXT

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("表格CSV")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "blb2txt 表格与 CSV 参数。"
            "提取表格 (--extract-tables / -et, 0/1, 默认 1)、"
            "CSV 逗号分隔 (--csv-comma, 布尔)、"
            "CSV 分号分隔 (--csv-semicolon, 布尔)、"
            "CSV 空格分隔 (--csv-space, 布尔)、"
            "CSV 制表符分隔 (--csv-tab, 布尔)、"
            "CSV 双引号 (--csv-double-quote, 布尔)、"
            "CSV 单引号 (--csv-single-quote, 布尔)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从本 Tab 的控件读取值，写入 ``cfg`` 对应字段。"""
        self._collect_int(cfg, "--extract-tables", self.extract_tables_spin)
        for suffix, field_name, _option, _label in _CSV_FIELDS:
            chk = getattr(self, f"{suffix}_chk")
            setattr(cfg, field_name, chk.isChecked())

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""
        self._apply_int(cfg, "--extract-tables", self.extract_tables_spin)
        for suffix, field_name, _option, _label in _CSV_FIELDS:
            chk = getattr(self, f"{suffix}_chk")
            chk.setChecked(bool(getattr(cfg, field_name)))

    def _build_ui(self) -> None:
        """构建表格 CSV 选项卡界面。"""
        layout = QFormLayout(self)

        # -et 提取表格（0/1）
        self.extract_tables_spin = QSpinBox(self)
        self.extract_tables_spin.setRange(0, 1)
        self.extract_tables_spin.setValue(0)
        self.extract_tables_spin.setToolTip(
            "提取表格（0 表示不启用 -et，对应 None；1 表示 -et 1）"
        )
        self.extract_tables_spin.valueChanged.connect(
            lambda: self._emit_changed()
        )
        layout.addRow("提取表格 (-et)：", self.extract_tables_spin)

        # 6 个 CSV flag
        for suffix, _field_name, option, label in _CSV_FIELDS:
            chk = QCheckBox(f"{label} ({option})", self)
            chk.toggled.connect(lambda: self._emit_changed())
            setattr(self, f"{suffix}_chk", chk)
            layout.addRow(chk)

        self.setLayout(layout)


__all__ = ["Blb2txtTablesCsvTab"]
