"""三向联动复合控件：QSlider + QSpinBox + 可选 QDial。

提供 ``SliderSpinDial``，封装三个 Qt6 原生数值控件的同步联动：
- ``QSlider``（水平滑动条）：直观拖动，适合范围连续参数（语速/音调/音量/停顿）
- ``QSpinBox``（数字输入框）：精确输入，与 slider 双向同步
- ``QDial``（旋钮，可选）：拟物化旋钮，适合音量主控等圆周型语义参数

任一控件变化将同步其他两个，通过 ``_syncing`` 标志屏蔽联动信号循环。

对外暴露与 ``QSpinBox`` 兼容的子集接口：``value()`` / ``setValue()`` /
``setRange()`` / ``setSingleStep()`` / ``setTickInterval()`` / ``setSuffix()``，
以及 ``valueChanged(int)`` 信号。

约束：保留 Qt6 原版样式，不引入自定义 QSS。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDial,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QWidget,
)

logger = logging.getLogger(__name__)


class SliderSpinDial(QWidget):
    """QSlider + QSpinBox + 可选 QDial 三向联动复合控件。

    Args:
        with_dial: 是否包含 QDial 旋钮。默认 ``False``（仅 slider + spinbox）。
        parent: 父控件。

    三向联动规则：
        - slider.valueChanged → 更新 spinbox 与 dial（若存在）
        - spinbox.valueChanged → 更新 slider 与 dial（若存在）
        - dial.valueChanged → 更新 slider 与 spinbox
        - 任一控件触发后，``_syncing`` 标志屏蔽后续联动信号，防止递归
        - 最终发射 ``valueChanged(int)`` 信号（仅一次）
    """

    # 对外统一信号：值变化（无论来源是 slider / spinbox / dial）
    valueChanged = Signal(int)

    def __init__(
        self,
        with_dial: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._syncing = False
        self._with_dial = with_dial

        # QSlider（水平）
        self.slider = QSlider()
        self.slider.setOrientation(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(0)
        self.slider.setMinimumWidth(40)  # 允许 slider 收缩，避免撑宽布局

        # QSpinBox（精确输入）
        self.spinbox = QSpinBox()
        self.spinbox.setRange(0, 100)
        self.spinbox.setValue(0)
        self.spinbox.setMinimumWidth(50)  # 限制 spinbox 最小宽度（数字+按钮）

        # QDial（可选旋钮）
        self.dial: QDial | None = None
        if with_dial:
            self.dial = QDial()
            self.dial.setRange(0, 100)
            self.dial.setValue(0)
            self.dial.setNotchesVisible(True)
            self.dial.setFixedSize(36, 36)  # 保持紧凑尺寸，避免撑宽布局

        # 布局：slider (stretch=1) + spinbox + [dial]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.spinbox)
        if self.dial is not None:
            layout.addWidget(self.dial)
        self.setLayout(layout)

        # 连接信号（统一入口 _on_any_changed）
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spinbox.valueChanged.connect(self._on_spinbox_changed)
        if self.dial is not None:
            self.dial.valueChanged.connect(self._on_dial_changed)

        logger.debug(
            "SliderSpinDial 已初始化 (with_dial=%s)", with_dial
        )

    # ----------------------------------------------------------------------
    # 内部槽函数：三向联动
    # ----------------------------------------------------------------------
    def _on_slider_changed(self, value: int) -> None:
        """slider 值变化：同步 spinbox / dial，并发射 valueChanged。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            if self.spinbox.value() != value:
                self.spinbox.setValue(value)
            if self.dial is not None and self.dial.value() != value:
                self.dial.setValue(value)
        finally:
            self._syncing = False
        self.valueChanged.emit(value)

    def _on_spinbox_changed(self, value: int) -> None:
        """spinbox 值变化：同步 slider / dial，并发射 valueChanged。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            if self.slider.value() != value:
                self.slider.setValue(value)
            if self.dial is not None and self.dial.value() != value:
                self.dial.setValue(value)
        finally:
            self._syncing = False
        self.valueChanged.emit(value)

    def _on_dial_changed(self, value: int) -> None:
        """dial 值变化：同步 slider / spinbox，并发射 valueChanged。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            if self.slider.value() != value:
                self.slider.setValue(value)
            if self.spinbox.value() != value:
                self.spinbox.setValue(value)
        finally:
            self._syncing = False
        self.valueChanged.emit(value)

    # ----------------------------------------------------------------------
    # 公开接口（与 QSpinBox 兼容子集）
    # ----------------------------------------------------------------------
    def value(self) -> int:
        """返回当前值（以 spinbox 为权威源）。"""
        return self.spinbox.value()

    def setValue(self, value: int) -> None:
        """设置值，同步三个控件。

        Args:
            value: 目标值，超出范围时由 QSpinBox 自动夹紧。
        """
        self._syncing = True
        try:
            self.spinbox.setValue(value)
            # slider / dial 在 spinbox 夹紧后的值同步
            clamped = self.spinbox.value()
            self.slider.setValue(clamped)
            if self.dial is not None:
                self.dial.setValue(clamped)
        finally:
            self._syncing = False
        # 程序设置也发射一次信号，便于上层统一处理
        self.valueChanged.emit(self.spinbox.value())

    def setRange(self, minimum: int, maximum: int) -> None:
        """设置范围，同步三个控件。

        Args:
            minimum: 最小值。
            maximum: 最大值。
        """
        self.spinbox.setRange(minimum, maximum)
        self.slider.setRange(minimum, maximum)
        if self.dial is not None:
            self.dial.setRange(minimum, maximum)

    def setSingleStep(self, step: int) -> None:
        """设置单步增量，同步三个控件。

        Args:
            step: 单步值。
        """
        self.spinbox.setSingleStep(step)
        self.slider.setSingleStep(step)
        if self.dial is not None:
            self.dial.setSingleStep(step)

    def setTickInterval(self, interval: int) -> None:
        """设置 slider 刻度间隔（仅 QSlider 支持，spinbox/dial 忽略）。

        Args:
            interval: 刻度间隔值。
        """
        self.slider.setTickInterval(interval)
        # 显示刻度位置（TicksBelow 适合水平 slider）
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        if self.dial is not None:
            # QDial 的 notch target 与 tickInterval 语义不同，此处仅保证
            # dial 显示的刻度数与 slider 一致（按 interval 比例换算）
            # QDial.setNotchTarget 接受浮点数，表示相邻刻度之间的像素距离
            # 这里不强制设置，保留 setNotchesVisible(True) 即可
            pass

    def setSuffix(self, suffix: str) -> None:
        """设置 spinbox 后缀（如 " ms"），slider / dial 不支持后缀故忽略。

        Args:
            suffix: 后缀字符串。
        """
        self.spinbox.setSuffix(suffix)

    def setDescription(self, text: str) -> None:
        """统一设置 slider / spinbox / dial 三者的 tooltip。

        用于向用户传达参数含义、范围、单位与默认值，避免逐个控件调用
        ``setToolTip``。若 ``dial`` 为 ``None``（未启用旋钮）则跳过。

        Args:
            text: tooltip 文本。
        """
        self.slider.setToolTip(text)
        self.spinbox.setToolTip(text)
        if self.dial is not None:
            self.dial.setToolTip(text)

    def minimum(self) -> int:
        """返回最小值。"""
        return self.spinbox.minimum()

    def maximum(self) -> int:
        """返回最大值。"""
        return self.spinbox.maximum()


__all__ = ["SliderSpinDial"]
