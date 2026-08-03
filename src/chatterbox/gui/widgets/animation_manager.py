"""动画统一管理器：AnimationManager。

提供 ``AnimationManager`` 单例类，集中管理 Qt6 原生动画的创建与降级：

- ``is_enabled()`` / ``set_enabled(bool)``：读写「禁用动画」开关
- ``make_property_animation(...)``：工厂方法创建 ``QPropertyAnimation``
- ``make_variant_animation(...)``：工厂方法创建 ``QVariantAnimation``
- 当 ``is_enabled() == False`` 时，工厂方法返回 duration=0 的动画（瞬时完成）
- 自动检测平台 ``prefers-reduced-motion``（通过 ``QGuiApplication.styleHints()``）
- 与 ``AppSettings.disable_animations`` 联动

设计目标：
    - 集中管理所有动画，便于全局降级
    - 工厂方法屏蔽动画创建细节，调用方仅关心起止值与回调
    - 尊重无障碍设置（``prefers-reduced-motion``）

约束：仅使用 Qt6 原生动画类，不引入第三方动画库。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QVariantAnimation,
)
from PySide6.QtGui import QGuiApplication

logger = logging.getLogger(__name__)

# 默认动画时长（毫秒）
_DEFAULT_DURATION_MS = 200

# 默认缓动曲线
_DEFAULT_EASING = QEasingCurve.Type.InOutQuad


def _detect_prefers_reduced_motion() -> bool:
    """检测平台是否启用了 ``prefers-reduced-motion``。

    通过 ``QGuiApplication.styleHints()`` 获取平台样式提示。当前 PySide6
    暂未直接暴露 ``prefersReducedMotion`` 属性，但保留扩展点：未来 Qt
    版本若支持，此处可自动启用降级。

    Returns:
        ``True`` 表示检测到 reduced-motion，应禁用动画；``False`` 表示
        未检测到或无法判断。
    """
    try:
        app = QGuiApplication.instance()
        if app is None:
            return False
        # PySide6 6.x 暂无 prefersReducedMotion，但保留扩展点
        # 未来可通过 styleHints() 的新属性检测
        # 例如：return bool(app.styleHints().prefersReducedMotion())
        return False
    except (AttributeError, RuntimeError):
        return False


class AnimationManager:
    """动画统一管理器（单例）。

    Usage:
        >>> anim_mgr = AnimationManager.instance()
        >>> anim_mgr.set_enabled(False)  # 禁用所有动画
        >>> anim = anim_mgr.make_property_animation(
        ...     target=widget, prop=b"pos", start=QPoint(0, 0),
        ...     end=QPoint(100, 0), duration=200,
        ... )
        >>> anim.start()

    Note:
        - 工厂方法返回的动画对象由调用方持有并 ``start()``
        - 禁用动画时工厂方法返回 duration=0 的动画，仍可正常 ``start()``，
          只是瞬时完成
        - ``is_enabled()`` 反映「动画是否启用」（``True`` = 启用），
          与 ``AppSettings.disable_animations`` 字段语义相反
    """

    _instance: AnimationManager | None = None

    def __init__(self) -> None:
        self._enabled: bool = True
        # 初始检测：若平台已启用 reduced-motion，自动禁用
        if _detect_prefers_reduced_motion():
            self._enabled = False
            logger.info(
                "检测到平台 prefers-reduced-motion，动画已自动禁用"
            )

    @classmethod
    def instance(cls) -> AnimationManager:
        """返回全局单例（首次调用时创建）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（仅供测试使用）。"""
        cls._instance = None

    # ----------------------------------------------------------------------
    # 启用/禁用
    # ----------------------------------------------------------------------
    def is_enabled(self) -> bool:
        """返回动画是否启用。"""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """设置动画启用状态。

        Args:
            enabled: ``True`` 启用动画；``False`` 禁用（所有动画瞬时完成）。
        """
        self._enabled = bool(enabled)
        logger.debug("AnimationManager.set_enabled(%s)", self._enabled)

    # ----------------------------------------------------------------------
    # 工厂方法
    # ----------------------------------------------------------------------
    def make_property_animation(
        self,
        target: Any,
        prop: bytes,
        start: Any,
        end: Any,
        duration: int = _DEFAULT_DURATION_MS,
        easing: QEasingCurve.Type = _DEFAULT_EASING,
    ) -> QPropertyAnimation:
        """创建 ``QPropertyAnimation``。

        Args:
            target: 目标对象（如 QWidget）。
            prop: 属性名（bytes，如 ``b"pos"`` / ``b"windowOpacity"``）。
            start: 起始值。
            end: 结束值。
            duration: 时长（毫秒），禁用动画时强制为 0。
            easing: 缓动曲线。

        Returns:
            配置好的 ``QPropertyAnimation``（未启动，调用方负责 ``start()``）。
        """
        anim = QPropertyAnimation(target, prop)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        if self._enabled:
            anim.setDuration(max(0, int(duration)))
        else:
            anim.setDuration(0)
        return anim

    def make_variant_animation(
        self,
        start: Any,
        end: Any,
        duration: int = _DEFAULT_DURATION_MS,
        on_value_changed: Callable[[Any], None] | None = None,
        easing: QEasingCurve.Type = _DEFAULT_EASING,
    ) -> QVariantAnimation:
        """创建 ``QVariantAnimation``（用于颜色等非属性插值）。

        Args:
            start: 起始值（如 ``QColor("#4CAF50")``）。
            end: 结束值（如 ``QColor("#F44336")``）。
            duration: 时长（毫秒），禁用动画时强制为 0。
            on_value_changed: 值变化回调（接收当前插值）。
            easing: 缓动曲线。

        Returns:
            配置好的 ``QVariantAnimation``（未启动，调用方负责 ``start()``）。
        """
        anim = QVariantAnimation()
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        if on_value_changed is not None:
            anim.valueChanged.connect(on_value_changed)
        if self._enabled:
            anim.setDuration(max(0, int(duration)))
        else:
            anim.setDuration(0)
        return anim


__all__ = ["AnimationManager"]
