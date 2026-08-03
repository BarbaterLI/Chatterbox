"""animation_manager 模块单元测试。

验证 ``AnimationManager`` 单例的行为：
- ``instance()`` 单例契约
- ``is_enabled()`` / ``set_enabled(bool)`` 读写开关
- ``make_property_animation(...)`` 工厂方法
- ``make_variant_animation(...)`` 工厂方法
- 禁用动画时返回 duration=0 的动画
- 默认动画参数（duration / easing）
- ``reset_instance()`` 重置（测试隔离）

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QVariantAnimation,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel

from balcon_batch_tts.gui.widgets.animation_manager import AnimationManager


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_animation_manager():
    """每个测试前重置 AnimationManager 单例，保证隔离。"""
    AnimationManager.reset_instance()
    yield
    AnimationManager.reset_instance()


# ---------------------------------------------------------------------------
# 单例契约
# ---------------------------------------------------------------------------
class TestSingleton:
    """``instance()`` 单例契约。"""

    def test_instance_returns_same_object(
        self, qapp: QApplication
    ) -> None:
        mgr1 = AnimationManager.instance()
        mgr2 = AnimationManager.instance()
        assert mgr1 is mgr2

    def test_reset_instance_creates_new_object(
        self, qapp: QApplication
    ) -> None:
        mgr1 = AnimationManager.instance()
        AnimationManager.reset_instance()
        mgr2 = AnimationManager.instance()
        assert mgr1 is not mgr2


# ---------------------------------------------------------------------------
# 启用/禁用开关
# ---------------------------------------------------------------------------
class TestEnabledSwitch:
    """``is_enabled()`` / ``set_enabled(bool)`` 契约。"""

    def test_default_is_enabled(self, qapp: QApplication) -> None:
        mgr = AnimationManager.instance()
        # 默认启用（除非平台 prefers-reduced-motion，offscreen 环境应为 False）
        assert mgr.is_enabled() is True

    def test_set_enabled_false(self, qapp: QApplication) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        assert mgr.is_enabled() is False

    def test_set_enabled_true(self, qapp: QApplication) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        mgr.set_enabled(True)
        assert mgr.is_enabled() is True

    def test_set_enabled_coerces_to_bool(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(0)  # falsy int
        assert mgr.is_enabled() is False
        mgr.set_enabled(1)  # truthy int
        assert mgr.is_enabled() is True


# ---------------------------------------------------------------------------
# make_property_animation
# ---------------------------------------------------------------------------
class TestMakePropertyAnimation:
    """``make_property_animation(...)`` 工厂方法契约。"""

    def test_returns_property_animation(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
            duration=200,
        )
        assert isinstance(anim, QPropertyAnimation)

    def test_start_and_end_values_set(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        label = QLabel()
        start = QPoint(0, 0)
        end = QPoint(100, 0)
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=start, end=end, duration=200,
        )
        assert anim.startValue() == start
        assert anim.endValue() == end

    def test_duration_set_when_enabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(True)
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
            duration=300,
        )
        assert anim.duration() == 300

    def test_duration_zero_when_disabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
            duration=300,
        )
        assert anim.duration() == 0

    def test_default_easing_inoutquad(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
        )
        assert anim.easingCurve().type() == QEasingCurve.Type.InOutQuad

    def test_custom_easing(self, qapp: QApplication) -> None:
        mgr = AnimationManager.instance()
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
            easing=QEasingCurve.Type.OutCubic,
        )
        assert anim.easingCurve().type() == QEasingCurve.Type.OutCubic

    def test_default_duration_200(self, qapp: QApplication) -> None:
        mgr = AnimationManager.instance()
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
        )
        assert anim.duration() == 200


# ---------------------------------------------------------------------------
# make_variant_animation
# ---------------------------------------------------------------------------
class TestMakeVariantAnimation:
    """``make_variant_animation(...)`` 工厂方法契约。"""

    def test_returns_variant_animation(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
            duration=200,
        )
        assert isinstance(anim, QVariantAnimation)

    def test_start_and_end_values_set(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        start = QColor("#4CAF50")
        end = QColor("#F44336")
        anim = mgr.make_variant_animation(start=start, end=end)
        assert anim.startValue() == start
        assert anim.endValue() == end

    def test_duration_set_when_enabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(True)
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
            duration=500,
        )
        assert anim.duration() == 500

    def test_duration_zero_when_disabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
            duration=500,
        )
        assert anim.duration() == 0

    def test_value_changed_callback_connected(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        received: list = []
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
            duration=0,  # 瞬时完成以便测试回调
            on_value_changed=lambda v: received.append(v),
        )
        anim.start()
        qapp.processEvents()
        # 至少收到一次回调
        assert len(received) >= 1

    def test_default_easing_inoutquad(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
        )
        assert anim.easingCurve().type() == QEasingCurve.Type.InOutQuad


# ---------------------------------------------------------------------------
# 禁用动画的端到端行为
# ---------------------------------------------------------------------------
class TestDisabledAnimationBehavior:
    """禁用动画时工厂方法返回的动画仍可用，但瞬时完成。"""

    def test_property_animation_starts_when_disabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        label = QLabel()
        anim = mgr.make_property_animation(
            target=label, prop=b"pos",
            start=QPoint(0, 0), end=QPoint(100, 0),
            duration=200,
        )
        anim.start()
        qapp.processEvents()
        # duration=0 时动画应快速进入 Stopped 状态
        # 注意：可能仍为 Running（依赖事件循环），但最终会停止
        # 此处仅验证不抛异常
        assert anim.duration() == 0

    def test_variant_animation_starts_when_disabled(
        self, qapp: QApplication
    ) -> None:
        mgr = AnimationManager.instance()
        mgr.set_enabled(False)
        anim = mgr.make_variant_animation(
            start=QColor("#4CAF50"), end=QColor("#F44336"),
            duration=200,
        )
        anim.start()
        qapp.processEvents()
        assert anim.duration() == 0
