"""多语音（外文词）选项卡模块。

提供 :class:`MultiVoiceTab`，封装 balcon 多语音相关参数的 GUI 控件，
包括附加语音名称、语言 ID 列表、语速/音调/音量与罗马数字/数字读取开关。

Task 4c 优化（Qt6 原生控件升级）：
- ``voice1_rate`` / ``voice1_pitch`` / ``voice1_volume`` 改用
  :class:`SliderSpinDial`（QSlider + QSpinBox + 可选 QDial）三向联动复合控件
- ``voice1_volume`` 增加 :class:`QDial` 旋钮（与 VoiceTab 一致）
- ``voice1_langid`` 改用 :class:`QPlainTextEdit`（非 QTextEdit，避免富文本开销）
- ``voice1_length`` 保留 QSpinBox（离散精确值）

约束：
- 使用 PySide6（QLineEdit、QPlainTextEdit、QSpinBox、QCheckBox、QFormLayout、
  QGroupBox、QHBoxLayout、QWidget）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，保留 Qt6 原版样式。
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider
from chatterbox.gui.widgets.slider_spin_dial import SliderSpinDial

logger = logging.getLogger(__name__)


class MultiVoiceTab(AbstractTab):
    """多语音（外文词）选项卡。

    封装 ``--voice1-name``、``--voice1-langid``、``--voice1-rate``、
    ``--voice1-pitch``、``--voice1-volume``、``--voice1-roman``、
    ``--voice1-digit``、``--voice1-length`` 字段的 GUI 控件。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "multi_voice"

    @classmethod
    def tab_title(cls) -> str:
        return "多语音（外文词）"

    @classmethod
    def tab_group(cls) -> str:
        return "高级"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("高级")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "多语音（外文词）参数。"
            "附加语音名称 (--voice1-name)、"
            "语言 ID (--voice1-langid, 多值, 逗号分隔或多次指定)、"
            "附加语音语速 (--voice1-rate, 范围 -10~10, 默认 0)、"
            "附加语音音调 (--voice1-pitch, 范围 -10~10, 默认 0, 单位半音)、"
            "附加语音音量 (--voice1-volume, 范围 0~100, 默认 100, 单位百分比)、"
            "用主语音读罗马数字 (--voice1-roman, 布尔)、"
            "用主语音读数字 (--voice1-digit, 布尔)、"
            "外文文本最小长度 (--voice1-length, 范围 0~1000, 默认 0 = 自动, 单位字符)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """从控件读值，写入 ``cfg`` 的多语音相关字段。

        - voice1_name：QLineEdit 空则 None
        - voice1_langid：QPlainTextEdit 按行分割（空行忽略）得到 list[str]
        - voice1_rate/pitch：值 0 且 default 为 0 则 None
        - voice1_volume：default 100，故 0 不设 None（始终保留 int）
        - voice1_length：值 0 设 None
        - voice1_roman/digit：bool
        """
        name = self.voice1_name_edit.text().strip()
        cfg.voice1_name = name if name else None

        raw = self.voice1_langid_edit.toPlainText()
        lines = [line.strip() for line in raw.splitlines()]
        cfg.voice1_langid = [line for line in lines if line]

        rate = self.voice1_rate_widget.value()
        cfg.voice1_rate = rate if rate != 0 else None

        pitch = self.voice1_pitch_widget.value()
        cfg.voice1_pitch = pitch if pitch != 0 else None

        # volume 默认 100，0 是有效值，直接保留
        cfg.voice1_volume = self.voice1_volume_widget.value()

        cfg.voice1_roman = self.voice1_roman_chk.isChecked()
        cfg.voice1_digit = self.voice1_digit_chk.isChecked()

        length = self.voice1_length_spin.value()
        cfg.voice1_length = length if length != 0 else None

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg`` 读值，还原多语音相关控件状态。"""
        self.voice1_name_edit.setText(cfg.voice1_name or "")

        lines = cfg.voice1_langid if cfg.voice1_langid else []
        self.voice1_langid_edit.setPlainText("\n".join(lines))

        self.voice1_rate_widget.setValue(
            cfg.voice1_rate if cfg.voice1_rate is not None else 0
        )
        self.voice1_pitch_widget.setValue(
            cfg.voice1_pitch if cfg.voice1_pitch is not None else 0
        )
        self.voice1_volume_widget.setValue(
            cfg.voice1_volume if cfg.voice1_volume is not None else 100
        )

        self.voice1_roman_chk.setChecked(bool(cfg.voice1_roman))
        self.voice1_digit_chk.setChecked(bool(cfg.voice1_digit))

        self.voice1_length_spin.setValue(
            cfg.voice1_length if cfg.voice1_length is not None else 0
        )

    def refresh_voices(self, voices: list[str]) -> None:
        """MultiVoiceTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """MultiVoiceTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建多语音选项卡界面。"""
        # 附加语音名称
        self.voice1_name_edit = QLineEdit(self)
        self.voice1_name_edit.setPlaceholderText("从语音列表复制名称")
        self.voice1_name_edit.textChanged.connect(lambda: self._emit_changed())

        # 语言 ID（多行，每行一个）—— 使用 QPlainTextEdit 避免 QTextEdit 富文本开销
        self.voice1_langid_edit = QPlainTextEdit(self)
        self.voice1_langid_edit.setPlaceholderText(
            "每行一个语言 ID，如 1033 或 0x0409"
        )
        self.voice1_langid_edit.setMaximumBlockCount(100)
        self.voice1_langid_edit.textChanged.connect(lambda: self._emit_changed())

        # 语速 / 音调 / 音量 —— 使用 SliderSpinDial 三向联动复合控件
        self.voice1_rate_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.voice1_rate_widget.setDescription(
            "附加语音语速 (--voice1-rate)。范围 -10 到 10，默认 0"
        )
        self.voice1_pitch_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.voice1_pitch_widget.setDescription(
            "附加语音音调 (--voice1-pitch)。范围 -10 到 10，默认 0，单位半音"
        )
        # volume 增加 QDial 旋钮
        self.voice1_volume_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=100,
            value=100,
            tick_interval=10,
            step=1,
            with_dial=True,
        )
        self.voice1_volume_widget.setDescription(
            "附加语音音量 (--voice1-volume)。范围 0 到 100，默认 0（使用 balcon 默认），单位百分比"
        )

        # 罗马数字 / 数字
        self.voice1_roman_chk = QCheckBox(
            "用主语音读罗马数字 (--voice1-roman)", self
        )
        self.voice1_roman_chk.toggled.connect(lambda: self._emit_changed())
        self.voice1_digit_chk = QCheckBox(
            "用主语音读数字 (--voice1-digit)", self
        )
        self.voice1_digit_chk.toggled.connect(lambda: self._emit_changed())

        # 外文文本最小长度
        self.voice1_length_spin = QSpinBox(self)
        self.voice1_length_spin.setRange(0, 1000)
        self.voice1_length_spin.setSpecialValueText("自动")
        self.voice1_length_spin.setValue(0)
        self.voice1_length_spin.setToolTip(
            "外文文本最小长度（字符）。短于此长度的文本不切换到附加语音，0=自动"
        )
        self.voice1_length_spin.valueChanged.connect(lambda: self._emit_changed())

        # === 顶部：附加语音名称 + 语言 ID ===
        outer = QFormLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addRow("附加语音名称 (--voice1-name)：", self.voice1_name_edit)
        outer.addRow("语言 ID (--voice1-langid)，每行一个：", self.voice1_langid_edit)

        # === 中部：语速 / 音调 / 音量 QGroupBox ===
        voice_params_group = QGroupBox("附加语音参数", self)
        voice_params_form = QFormLayout(voice_params_group)
        voice_params_form.setContentsMargins(8, 12, 8, 8)

        # 第一行：语速 + 音调（2 列 QHBoxLayout）
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(QLabel("语速："))
        row1.addWidget(self.voice1_rate_widget, 1)
        row1.addSpacing(16)
        row1.addWidget(QLabel("音调："))
        row1.addWidget(self.voice1_pitch_widget, 1)
        row1_container = QWidget()
        row1_container.setLayout(row1)
        voice_params_form.addRow(row1_container)

        # 第二行：音量（含 QDial 旋钮，单独一行）
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(QLabel("音量："))
        row2.addWidget(self.voice1_volume_widget, 1)
        row2_container = QWidget()
        row2_container.setLayout(row2)
        voice_params_form.addRow(row2_container)

        # 外文文本最小长度
        voice_params_form.addRow(
            "外文文本最小长度 (--voice1-length)：", self.voice1_length_spin
        )

        voice_params_group.setLayout(voice_params_form)
        outer.addRow(voice_params_group)

        # === 底部：罗马数字 / 数字 checkbox ===
        options_group = QGroupBox("读取选项", self)
        options_form = QFormLayout(options_group)
        options_form.setContentsMargins(8, 12, 8, 8)
        options_form.addRow(self.voice1_roman_chk)
        options_form.addRow(self.voice1_digit_chk)
        options_group.setLayout(options_form)
        outer.addRow(options_group)

        self.setLayout(outer)

    def _make_slider_spin_dial(
        self,
        minimum: int,
        maximum: int,
        value: int,
        tick_interval: int,
        step: int,
        with_dial: bool = False,
    ) -> SliderSpinDial:
        """创建 SliderSpinDial 复合控件并配置参数。"""
        widget = SliderSpinDial(with_dial=with_dial, parent=self)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setTickInterval(tick_interval)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        widget.valueChanged.connect(lambda _: self._emit_changed())
        return widget


__all__ = ["MultiVoiceTab"]
