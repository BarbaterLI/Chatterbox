"""blb2txt 文本处理选项卡模块。

提供 :class:`Blb2txtTextProcessingTab`，封装 blb2txt 文本处理相关的
14 个布尔 flag 参数（移除空格 / 连字符 / 空行 / 括号内容等）的 GUI 控件。

Task 4e 优化（Qt6 原生控件升级）：
- 14 个 flag 按语义分为 4 个 :class:`QGroupBox` 子组：
  * 「空白处理」（5 个）：移除空格 / 连字符 / 空行 / 多空格 / 空段落
  * 「括号处理」（4 个）：移除方括号 / 花括号 / 尖括号 / 圆括号内容
  * 「OCR 与内容」（3 个）：移除注释 / 移除页码 / OCR 纠正
  * 「字符转换」（2 个）：转小写 / 仅保留 ASCII
- 每个 QGroupBox 内部使用 :class:`QGridLayout` 2 列紧凑排布
- 整体放入 :class:`QScrollArea`，避免参数过多撑爆窗口高度
- 保留 :class:`QCheckBox` 布尔开关

约束：
- 使用 PySide6（QCheckBox、QGridLayout、QGroupBox、QScrollArea、QVBoxLayout、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt6 原版样式。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


# 14 个文本处理 flag 字段定义：(属性后缀, 字段名, 选项别名, 中文标签)
# 顺序与 Blb2txtConfig.TextProcessing 分组字段声明顺序一致。
_TEXT_PROCESSING_FIELDS: list[tuple[str, str, str, str]] = [
    ("remove_spaces", "remove_spaces", "-rs", "移除空格"),
    ("remove_hyphens", "remove_hyphens", "-rh", "移除连字符"),
    ("remove_lines", "remove_lines", "-rl", "移除空行"),
    ("remove_multiple", "remove_multiple", "-rm", "合并多空格"),
    ("remove_paragraphs", "remove_paragraphs", "-rp", "移除空段落"),
    ("remove_square_brackets", "remove_square_brackets", "-rsb", "移除方括号内容"),
    ("remove_curly_brackets", "remove_curly_brackets", "-rcb", "移除花括号内容"),
    ("remove_angle_brackets", "remove_angle_brackets", "-rab", "移除尖括号内容"),
    ("remove_round_brackets", "remove_round_brackets", "-rrb", "移除圆括号内容"),
    ("remove_comments", "remove_comments", "-rc", "移除注释"),
    ("remove_page_numbers", "remove_page_numbers", "-rpn", "移除页码"),
    ("ocr_correction", "ocr_correction", "-ocr", "OCR 纠正"),
    ("lowercase", "lowercase", "-ls", "转小写"),
    ("ascii_pure", "ascii_pure", "-ap", "仅保留 ASCII"),
]

# 语义分组定义：(组名, [字段后缀列表])
# 14 个 flag 分为 4 组：空白处理 / 括号处理 / OCR 与内容 / 字符转换
_FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("空白处理", [
        "remove_spaces",
        "remove_hyphens",
        "remove_lines",
        "remove_multiple",
        "remove_paragraphs",
    ]),
    ("括号处理", [
        "remove_square_brackets",
        "remove_curly_brackets",
        "remove_angle_brackets",
        "remove_round_brackets",
    ]),
    ("OCR 与内容", [
        "remove_comments",
        "remove_page_numbers",
        "ocr_correction",
    ]),
    ("字符转换", [
        "lowercase",
        "ascii_pure",
    ]),
]


class Blb2txtTextProcessingTab(AbstractTab):
    """blb2txt 文本处理选项卡。

    封装 14 个文本处理布尔 flag 字段（``remove_spaces`` 等）的 GUI 控件，
    每个字段对应一个 QCheckBox，标签显示为 ``中文名 (选项别名)``，
    如 ``"移除空格 (-rs)"``。所有 flag 默认 False（未勾选）。

    控件按语义分为 4 个 :class:`QGroupBox` 子组（空白处理 / 括号处理 /
    OCR 与内容 / 字符转换），每组内部以 :class:`QGridLayout` 2 列紧凑排布。
    整体放入 :class:`QScrollArea`，避免参数过多撑爆窗口高度。

    控件值变化时通过 :meth:`_emit_changed` 发射 :attr:`config_changed`
    信号，供主窗口监听更新预览。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "blb2txt_text_processing"

    @classmethod
    def tab_title(cls) -> str:
        return "文本处理（blb2txt）"

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
            "blb2txt 文本处理参数（14 个布尔开关, 默认全部关闭）。"
            "移除空格 (--remove-spaces / -rs)、"
            "移除连字符 (--remove-hyphens / -rh)、"
            "移除空行 (--remove-lines / -rl)、"
            "合并多空格 (--remove-multiple / -rm)、"
            "移除空段落 (--remove-paragraphs / -rp)、"
            "移除方括号内容 (--remove-square-brackets / -rsb)、"
            "移除花括号内容 (--remove-curly-brackets / -rcb)、"
            "移除尖括号内容 (--remove-angle-brackets / -rab)、"
            "移除圆括号内容 (--remove-round-brackets / -rrb)、"
            "移除注释 (--remove-comments / -rc)、"
            "移除页码 (--remove-page-numbers / -rpn)、"
            "OCR 纠正 (--ocr-correction / -ocr)、"
            "转小写 (--lowercase / -ls)、"
            "仅保留 ASCII (--ascii-pure / -ap)"
        )

    def collect_config(self, cfg: Blb2txtConfig) -> None:
        """从 14 个 QCheckBox 读取 isChecked，写入 cfg 对应字段。"""
        for suffix, field_name, _alias, _label in _TEXT_PROCESSING_FIELDS:
            chk = getattr(self, f"{suffix}_chk")
            setattr(cfg, field_name, chk.isChecked())

    def apply_config(self, cfg: Blb2txtConfig) -> None:
        """从 cfg 读值，还原 14 个 QCheckBox 状态。"""
        for suffix, field_name, _alias, _label in _TEXT_PROCESSING_FIELDS:
            chk = getattr(self, f"{suffix}_chk")
            chk.setChecked(bool(getattr(cfg, field_name)))

    def _build_ui(self) -> None:
        """构建文本处理选项卡界面（4 个 QGroupBox 子组 + QScrollArea）。"""
        # 先创建全部 14 个 QCheckBox
        for suffix, _field_name, alias, label in _TEXT_PROCESSING_FIELDS:
            chk = QCheckBox(f"{label} ({alias})", self)
            chk.toggled.connect(lambda: self._emit_changed())
            setattr(self, f"{suffix}_chk", chk)

        # 字段后缀 → QCheckBox 映射，便于按分组取用
        suffix_to_chk = {
            suffix: getattr(self, f"{suffix}_chk")
            for suffix, _field, _alias, _label in _TEXT_PROCESSING_FIELDS
        }

        # 内容容器：承载 4 个 QGroupBox
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)

        # 按 _FIELD_GROUPS 创建 QGroupBox，每组内部 QGridLayout 2 列
        for group_title, suffixes in _FIELD_GROUPS:
            group_box = QGroupBox(group_title, content)
            grid = QGridLayout(group_box)
            grid.setContentsMargins(8, 12, 8, 8)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(4)
            for idx, suffix in enumerate(suffixes):
                row = idx // 2
                col = idx % 2
                grid.addWidget(suffix_to_chk[suffix], row, col)
            # 末列拉伸，避免控件被横向拉宽
            grid.setColumnStretch(2, 1)
            content_layout.addWidget(group_box)

        # 末尾竖向拉伸，避免 QGroupBox 被均匀拉大
        content_layout.addStretch(1)

        # QScrollArea 包裹内容
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Tab 主布局
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)


__all__ = ["Blb2txtTextProcessingTab"]
