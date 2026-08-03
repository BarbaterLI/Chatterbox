"""语音与静音分组 Tab 模块。

提供语音名称、语言 ID、语速 / 音调 / 音量 / 句间停顿 / 段间停顿，
以及起始静音 / 结尾静音共 9 个参数的 GUI 编辑。

Task 4b 优化（吸收 SilenceTab + Qt6 原生控件升级）：
- 7 个数值参数使用 :class:`SliderSpinDial`（QSlider + QSpinBox + 可选 QDial）
  三向联动复合控件，slider 拖动快速预览，spinbox 精确输入
- 音量参数增加 :class:`QDial` 旋钮（拟物化旋钮，与 slider / spinbox 三向联动）
- 静音参数（silence_begin / silence_end）用 :class:`QGroupBox` 包裹「静音设置」子组
- 5 个主要数值参数（rate / pitch / volume / sentence_pause / paragraph_pause）
  以 2 列 :class:`QHBoxLayout` 排列，节省纵向空间
- tab_title 改为「语音与静音」，tab_id 保持 ``"voice"``
- 语音名称列表由主窗口通过 :meth:`refresh_voices` 注入
"""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.config import BalconConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider
from chatterbox.gui.widgets.slider_spin_dial import SliderSpinDial

logger = logging.getLogger(__name__)


class VoiceTab(AbstractTab):
    """语音与静音参数分组 Tab。

    编辑 9 个参数：
    - 语音名称 (-n)、语言 ID (-id)
    - 语速 (-s)、音调 (-p)、音量 (-v)、句间停顿 (-e)、段间停顿 (-a)
    - 起始静音 (--silence-begin)、结尾静音 (--silence-end)

    7 个数值参数使用 SliderSpinDial 三向联动复合控件。
    音量参数额外增加 QDial 旋钮。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "voice"

    @classmethod
    def tab_title(cls) -> str:
        return "语音与静音"

    @classmethod
    def tab_group(cls) -> str:
        return "语音音频"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.BALCON

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("语音音频")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "语音与静音参数。"
            "语音名称 (-n)、语言 ID (-id)、"
            "语速 (-s, 范围 -10~10, 默认 0)、"
            "音调 (-p, 范围 -10~10, 默认 0, 单位半音)、"
            "音量 (-v, 范围 0~100, 默认 100, 单位百分比)、"
            "句间停顿 (-e, 单位毫秒, 默认 0)、"
            "段间停顿 (-a, 单位毫秒, 默认 0)、"
            "起始静音 (--silence-begin, 单位毫秒, 默认 0)、"
            "结尾静音 (--silence-end, 单位毫秒, 默认 0)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        """从控件读取值，写入 :class:`BalconConfig`。"""
        voice = self.voice_combo.currentText().strip()
        cfg.n_voice = voice if voice else None
        # 注意：n_voice 也可能由用户从预设/配置文件加载，不在枚举列表中。
        # apply_config 会将其作为额外项添加到下拉框，确保配置值可见。

        cfg.id_langid = self._parse_langid(self.langid_edit.text())

        # schema default 为 0 的字段：值 0 → None（避免冗余）
        rate_value = self.rate_widget.value()
        cfg.s_rate = None if rate_value == 0 else rate_value

        pitch_value = self.pitch_widget.value()
        cfg.p_pitch = None if pitch_value == 0 else pitch_value

        # v_volume 的 schema default 为 100，0 是有意义的值，始终写入
        cfg.v_volume = self.volume_widget.value()

        sentence_pause_value = self.sentence_pause_widget.value()
        cfg.e_sentence_pause = (
            None if sentence_pause_value == 0 else sentence_pause_value
        )

        paragraph_pause_value = self.paragraph_pause_widget.value()
        cfg.a_paragraph_pause = (
            None if paragraph_pause_value == 0 else paragraph_pause_value
        )

        silence_begin_value = self.silence_begin_widget.value()
        cfg.silence_begin = (
            None if silence_begin_value == 0 else silence_begin_value
        )

        silence_end_value = self.silence_end_widget.value()
        cfg.silence_end = (
            None if silence_end_value == 0 else silence_end_value
        )

    def apply_config(self, cfg: BalconConfig) -> None:
        """从 :class:`BalconConfig` 读取值，还原控件状态。

        语音名称通过 :meth:`_set_voice_combo_text` 设置：若文本在下拉列表中
        则直接选中，否则作为额外项添加后选中（确保配置值可见可选）。
        """
        self._set_voice_combo_text(cfg.n_voice or "")

        self.langid_edit.setText(
            str(cfg.id_langid) if cfg.id_langid is not None else ""
        )

        self.rate_widget.setValue(cfg.s_rate if cfg.s_rate is not None else 0)
        self.pitch_widget.setValue(
            cfg.p_pitch if cfg.p_pitch is not None else 0
        )
        self.volume_widget.setValue(
            cfg.v_volume if cfg.v_volume is not None else 100
        )
        self.sentence_pause_widget.setValue(
            cfg.e_sentence_pause if cfg.e_sentence_pause is not None else 0
        )
        self.paragraph_pause_widget.setValue(
            cfg.a_paragraph_pause
            if cfg.a_paragraph_pause is not None
            else 0
        )
        self.silence_begin_widget.setValue(
            cfg.silence_begin if cfg.silence_begin is not None else 0
        )
        self.silence_end_widget.setValue(
            cfg.silence_end if cfg.silence_end is not None else 0
        )

    def refresh_voices(self, voices: list[str]) -> None:
        """刷新语音下拉列表，保留当前选择（若仍在新列表中）。

        非可编辑模式下无法通过 ``setEditText`` 设置任意文本，故采用
        :meth:`_set_voice_combo_text` 统一处理：若当前选择不在新列表中，
        作为额外项添加后选中，确保配置值不丢失。

        Args:
            voices: balcon 枚举到的语音名称列表。
        """
        current = self.voice_combo.currentText().strip()
        self.voice_combo.clear()
        for v in voices:
            self.voice_combo.addItem(v)
        self._set_voice_combo_text(current)

    def _set_voice_combo_text(self, text: str) -> None:
        """设置语音下拉框的当前文本（非可编辑模式兼容）。

        若 ``text`` 在下拉列表中则直接选中对应项；若不在列表中且 ``text``
        非空，则作为额外项添加到末尾后选中（确保预设/配置文件中的语音名
        可见可选，即使它未被 balcon 枚举到——例如路径变更后尚未刷新）。

        Args:
            text: 目标语音名称；空字符串选中第 0 项（若有）。
        """
        if not text:
            if self.voice_combo.count() > 0:
                self.voice_combo.setCurrentIndex(0)
            return
        idx = self.voice_combo.findText(text)
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        else:
            # 语音不在枚举列表中：作为额外项添加后选中
            self.voice_combo.addItem(text)
            self.voice_combo.setCurrentIndex(self.voice_combo.count() - 1)

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """VoiceTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建语音与静音参数界面。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # === 顶部：语音名称 + 语言 ID ===
        top_form = QFormLayout()
        top_form.setContentsMargins(0, 0, 0, 0)

        # 语音名称下拉框：非可编辑模式，仅允许从枚举列表选择（禁止键盘输入）。
        # 若预设/配置文件中的语音名不在枚举列表中，_set_voice_combo_text 会
        # 将其作为额外项添加，确保配置值可见可选。
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(80)
        self.voice_combo.currentIndexChanged.connect(
            lambda: self._emit_changed()
        )
        top_form.addRow("语音名称 (-n)：", self.voice_combo)

        self.langid_edit = QLineEdit()
        self.langid_edit.setPlaceholderText(
            '语言 ID，如 "1033" 或 "0x0409"'
        )
        self.langid_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        top_form.addRow("语言 ID (-id)：", self.langid_edit)
        outer.addLayout(top_form)

        # top_form 与 params_container 间的水平分隔线
        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(hline)

        # === 中部：5 个主要数值参数，2 列 QHBoxLayout 排列 ===
        params_container = QWidget(self)
        params_form = QFormLayout(params_container)
        params_form.setContentsMargins(0, 8, 0, 8)

        # 第一行：语速 (-s) + 音调 (-p)
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(QLabel("语速 (-s)："))
        self.rate_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.rate_widget.setDescription(
            "语速 (-s)。范围 -10 到 10，默认 0，正值加快、负值减慢"
        )
        row1.addWidget(self.rate_widget, 1)
        row1.addSpacing(16)
        row1.addWidget(QLabel("音调 (-p)："))
        self.pitch_widget = self._make_slider_spin_dial(
            minimum=-10, maximum=10, value=0, tick_interval=1, step=1
        )
        self.pitch_widget.setDescription(
            "音调 (-p)。范围 -10 到 10，默认 0，单位半音"
        )
        row1.addWidget(self.pitch_widget, 1)
        row1_container = QWidget()
        row1_container.setLayout(row1)
        params_form.addRow(row1_container)

        # 第二行：音量 (-v) + 句间停顿 (-e)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(QLabel("音量 (-v)："))
        # 音量使用 with_dial=True（QDial 旋钮）
        self.volume_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=100,
            value=100,
            tick_interval=10,
            step=1,
            with_dial=True,
        )
        self.volume_widget.setDescription(
            "音量 (-v)。范围 0 到 100，默认 0（使用 balcon 默认），单位百分比"
        )
        row2.addWidget(self.volume_widget, 1)
        row2.addSpacing(16)
        row2.addWidget(QLabel("句间停顿 (-e)："))
        self.sentence_pause_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=10000,
            value=0,
            tick_interval=1000,
            step=100,
            suffix=" ms",
        )
        self.sentence_pause_widget.setDescription(
            "句间停顿 (-e)。范围 0 到 10000，默认 0，单位毫秒"
        )
        row2.addWidget(self.sentence_pause_widget, 1)
        row2_container = QWidget()
        row2_container.setLayout(row2)
        params_form.addRow(row2_container)

        # 第三行：段间停顿 (-a)（单独一行，因范围较大）
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.addWidget(QLabel("段间停顿 (-a)："))
        self.paragraph_pause_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=60000,
            value=0,
            tick_interval=10000,
            step=1000,
            suffix=" ms",
        )
        self.paragraph_pause_widget.setDescription(
            "段间停顿 (-a)。范围 0 到 10000，默认 0，单位毫秒"
        )
        row3.addWidget(self.paragraph_pause_widget, 1)
        row3_container = QWidget()
        row3_container.setLayout(row3)
        params_form.addRow(row3_container)

        outer.addWidget(params_container)

        # === 底部：静音设置 QGroupBox ===
        silence_group = QGroupBox("静音设置", self)
        silence_form = QFormLayout(silence_group)
        silence_form.setContentsMargins(8, 12, 8, 8)

        self.silence_begin_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=60000,
            value=0,
            tick_interval=10000,
            step=1000,
            suffix=" ms",
        )
        self.silence_begin_widget.setDescription(
            "起始静音 (--silence-begin)。范围 0 到 10000，默认 0 = 使用 balcon 默认，单位毫秒"
        )
        silence_form.addRow("起始静音 (--silence-begin)：", self.silence_begin_widget)

        self.silence_end_widget = self._make_slider_spin_dial(
            minimum=0,
            maximum=60000,
            value=0,
            tick_interval=10000,
            step=1000,
            suffix=" ms",
        )
        self.silence_end_widget.setDescription(
            "结尾静音 (--silence-end)。范围 0 到 10000，默认 0 = 使用 balcon 默认，单位毫秒"
        )
        silence_form.addRow("结尾静音 (--silence-end)：", self.silence_end_widget)

        silence_group.setLayout(silence_form)
        outer.addWidget(silence_group)

        # 添加伸缩空间，让顶部内容保持紧凑
        outer.addStretch(1)

        self.setLayout(outer)

    def _make_slider_spin_dial(
        self,
        minimum: int,
        maximum: int,
        value: int,
        tick_interval: int,
        step: int,
        suffix: str | None = None,
        with_dial: bool = False,
    ) -> SliderSpinDial:
        """创建 SliderSpinDial 复合控件并配置参数。

        Args:
            minimum: 最小值。
            maximum: 最大值。
            value: 初始值。
            tick_interval: slider 刻度间隔。
            step: 单步增量。
            suffix: spinbox 后缀（如 " ms"），可选。
            with_dial: 是否包含 QDial 旋钮（音量参数为 True）。
        """
        widget = SliderSpinDial(with_dial=with_dial, parent=self)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setTickInterval(tick_interval)
        if suffix:
            widget.setSuffix(suffix)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        widget.valueChanged.connect(lambda _: self._emit_changed())
        return widget

    @staticmethod
    def _parse_langid(text: str) -> int | None:
        """解析语言 ID 文本，支持十进制（如 ``1033``）与十六进制
        （如 ``0x0409``）。无法解析时返回 ``None``。
        """
        text = text.strip()
        if not text:
            return None
        try:
            if text.lower().startswith("0x"):
                return int(text, 16)
            return int(text, 10)
        except (ValueError, TypeError):
            return None


__all__ = ["VoiceTab"]
