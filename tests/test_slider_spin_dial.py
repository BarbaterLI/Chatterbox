"""slider_spin_dial 模块单元测试。

验证 ``SliderSpinDial`` 的三向联动行为，覆盖：
- 默认构造与控件存在性（slider / spinbox / 可选 dial）
- ``value()`` / ``setValue()`` 接口
- ``setRange()`` / ``setSingleStep()`` / ``setTickInterval()`` / ``setSuffix()``
- ``valueChanged(int)`` 信号发射
- 三向联动：slider → spinbox / dial；spinbox → slider / dial；dial → slider / spinbox
- 防递归：``_syncing`` 标志屏蔽信号循环（无 RecursionError）
- 边界值：最小值 / 最大值 / 超出范围夹紧
- QDial ``setNotchesVisible(True)`` 已设置

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDial,
    QSlider,
    QSpinBox,
)

from balcon_batch_tts.gui.widgets.slider_spin_dial import SliderSpinDial


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 构造与控件存在性
# ---------------------------------------------------------------------------
class TestConstruction:
    """构造与子控件存在性契约。"""

    def test_default_without_dial(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        assert widget.dial is None
        assert isinstance(widget.slider, QSlider)
        assert isinstance(widget.spinbox, QSpinBox)

    def test_with_dial_true_creates_dial(self, qapp: QApplication) -> None:
        widget = SliderSpinDial(with_dial=True)
        assert widget.dial is not None
        assert isinstance(widget.dial, QDial)

    def test_dial_notches_visible(self, qapp: QApplication) -> None:
        widget = SliderSpinDial(with_dial=True)
        assert widget.dial is not None
        assert widget.dial.notchesVisible() is True

    def test_slider_orientation_horizontal(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        assert (
            widget.slider.orientation()
            == Qt.Orientation.Horizontal
        )

    def test_default_range_0_to_100(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        assert widget.minimum() == 0
        assert widget.maximum() == 100
        assert widget.value() == 0


# ---------------------------------------------------------------------------
# value / setValue 接口
# ---------------------------------------------------------------------------
class TestValueInterface:
    """``value()`` / ``setValue()`` 契约。"""

    def test_set_value_syncs_all_three(self, qapp: QApplication) -> None:
        widget = SliderSpinDial(with_dial=True)
        widget.setValue(50)
        assert widget.value() == 50
        assert widget.slider.value() == 50
        assert widget.spinbox.value() == 50
        assert widget.dial is not None
        assert widget.dial.value() == 50

    def test_set_value_without_dial(self, qapp: QApplication) -> None:
        widget = SliderSpinDial(with_dial=False)
        widget.setValue(30)
        assert widget.value() == 30
        assert widget.slider.value() == 30
        assert widget.spinbox.value() == 30

    def test_set_value_clamps_to_range(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        widget.setRange(-10, 10)
        widget.setValue(100)
        assert widget.value() == 10
        widget.setValue(-100)
        assert widget.value() == -10

    def test_set_value_zero(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        widget.setValue(50)
        widget.setValue(0)
        assert widget.value() == 0

    def test_set_value_max(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        widget.setValue(100)
        assert widget.value() == 100


# ---------------------------------------------------------------------------
# setRange / setSingleStep / setTickInterval / setSuffix
# ---------------------------------------------------------------------------
class TestConfigInterfaces:
    """``setRange`` / ``setSingleStep`` / ``setTickInterval`` / ``setSuffix`` 契约。"""

    def test_set_range_syncs_all(self, qapp: QApplication) -> None:
        widget = SliderSpinDial(with_dial=True)
        widget.setRange(-50, 50)
        assert widget.spinbox.minimum() == -50
        assert widget.spinbox.maximum() == 50
        assert widget.slider.minimum() == -50
        assert widget.slider.maximum() == 50
        assert widget.dial is not None
        assert widget.dial.minimum() == -50
        assert widget.dial.maximum() == 50

    def test_set_single_step_syncs_all(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        widget.setSingleStep(5)
        assert widget.spinbox.singleStep() == 5
        assert widget.slider.singleStep() == 5
        assert widget.dial is not None
        assert widget.dial.singleStep() == 5

    def test_set_tick_interval_sets_slider(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        widget.setTickInterval(10)
        assert widget.slider.tickInterval() == 10
        # setTickInterval 应同时启用刻度显示
        assert (
            widget.slider.tickPosition()
            != QSlider.TickPosition.NoTicks
        )

    def test_set_suffix_only_affects_spinbox(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        widget.setSuffix(" ms")
        assert widget.spinbox.suffix() == " ms"


# ---------------------------------------------------------------------------
# 三向联动
# ---------------------------------------------------------------------------
class TestThreeWaySync:
    """三向联动契约：任一控件变化同步其他两个。"""

    def test_slider_change_syncs_spinbox(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=False)
        widget.slider.setValue(42)
        assert widget.spinbox.value() == 42
        assert widget.value() == 42

    def test_spinbox_change_syncs_slider(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=False)
        widget.spinbox.setValue(37)
        assert widget.slider.value() == 37
        assert widget.value() == 37

    def test_slider_change_syncs_dial(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        widget.slider.setValue(60)
        assert widget.dial is not None
        assert widget.dial.value() == 60

    def test_spinbox_change_syncs_dial(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        widget.spinbox.setValue(25)
        assert widget.dial is not None
        assert widget.dial.value() == 25

    def test_dial_change_syncs_slider_and_spinbox(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        assert widget.dial is not None
        widget.dial.setValue(75)
        assert widget.slider.value() == 75
        assert widget.spinbox.value() == 75
        assert widget.value() == 75


# ---------------------------------------------------------------------------
# 防递归：_syncing 标志
# ---------------------------------------------------------------------------
class TestRecursionGuard:
    """``_syncing`` 标志屏蔽信号循环。"""

    def test_no_recursion_on_slider_change(
        self, qapp: QApplication
    ) -> None:
        """拖动 slider 不应触发 RecursionError。"""
        widget = SliderSpinDial(with_dial=True)
        # 反复设置值不应抛出异常
        for v in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
            widget.slider.setValue(v)
            assert widget.value() == v

    def test_no_recursion_on_spinbox_change(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        for v in [5, 15, 25, 35, 45]:
            widget.spinbox.setValue(v)
            assert widget.value() == v

    def test_no_recursion_on_dial_change(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        assert widget.dial is not None
        for v in [10, 20, 30, 40, 50]:
            widget.dial.setValue(v)
            assert widget.value() == v

    def test_no_recursion_on_set_value(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        for v in [0, 50, 100, 50, 0]:
            widget.setValue(v)
            assert widget.value() == v


# ---------------------------------------------------------------------------
# valueChanged 信号
# ---------------------------------------------------------------------------
class TestValueChangedSignal:
    """``valueChanged(int)`` 信号契约。"""

    def test_signal_emitted_on_slider_change(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        received: list[int] = []
        widget.valueChanged.connect(lambda v: received.append(v))
        widget.slider.setValue(42)
        # slider 变化应发射一次
        assert 42 in received

    def test_signal_emitted_on_spinbox_change(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        received: list[int] = []
        widget.valueChanged.connect(lambda v: received.append(v))
        widget.spinbox.setValue(37)
        assert 37 in received

    def test_signal_emitted_on_dial_change(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial(with_dial=True)
        received: list[int] = []
        widget.valueChanged.connect(lambda v: received.append(v))
        assert widget.dial is not None
        widget.dial.setValue(60)
        assert 60 in received

    def test_signal_emitted_on_set_value(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        received: list[int] = []
        widget.valueChanged.connect(lambda v: received.append(v))
        widget.setValue(55)
        assert received == [55]

    def test_signal_emitted_once_per_change(
        self, qapp: QApplication
    ) -> None:
        """联动过程仅发射一次 valueChanged（防递归）。"""
        widget = SliderSpinDial(with_dial=True)
        received: list[int] = []
        widget.valueChanged.connect(lambda v: received.append(v))
        widget.slider.setValue(70)
        # 应仅发射一次（70），不因联动重复发射
        assert received.count(70) == 1
        assert len(received) == 1


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------
class TestBoundaryValues:
    """边界值契约。"""

    def test_set_value_at_minimum(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        widget.setRange(-10, 10)
        widget.setValue(-10)
        assert widget.value() == -10
        assert widget.slider.value() == -10

    def test_set_value_at_maximum(self, qapp: QApplication) -> None:
        widget = SliderSpinDial()
        widget.setRange(-10, 10)
        widget.setValue(10)
        assert widget.value() == 10
        assert widget.slider.value() == 10

    def test_set_value_above_maximum_clamps(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        widget.setRange(0, 100)
        widget.setValue(200)
        assert widget.value() == 100

    def test_set_value_below_minimum_clamps(
        self, qapp: QApplication
    ) -> None:
        widget = SliderSpinDial()
        widget.setRange(0, 100)
        widget.setValue(-50)
        assert widget.value() == 0

    def test_negative_range_supported(
        self, qapp: QApplication
    ) -> None:
        """支持负数范围（如语速 -10~10）。"""
        widget = SliderSpinDial(with_dial=True)
        widget.setRange(-10, 10)
        widget.setValue(-5)
        assert widget.value() == -5
        assert widget.slider.value() == -5
        assert widget.dial is not None
        assert widget.dial.value() == -5
