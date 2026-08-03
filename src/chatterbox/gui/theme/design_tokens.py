"""设计令牌模块：集中管理 GUI 主题的颜色、间距、字号与动画时长。

提供 :class:`DesignTokens`，所有方法均为 ``@classmethod``，无需实例化。
颜色令牌按当前主题（light/dark）返回 :class:`QColor`，主题通过
``ThemeManager.instance().current_theme()`` 读取；当 T-A2 的
``ThemeManager`` 尚未实现时，兜底返回 ``"light"``。

亮/暗双色映射表内嵌于本模块，暗主题颜色适当调亮以适配深色背景。
现有 widget 中的硬编码颜色（``_FAILED_COLOR``、``_FAILURE_RATE_COLORS``、
``_DRAG_SHADOW_COLOR``、``_LEVEL_COLORS``、``_NEUTRAL_COLOR``、
状态图标 SVG 颜色）均在令牌化（T-E1）后由本模块统一提供。

约束：
- 使用 PySide6（QColor）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，仅提供令牌值供 widget 读取。
"""
from __future__ import annotations

from PySide6.QtGui import QColor


class DesignTokens:
    """设计令牌集合（classmethod 类，无需实例化）。

    集中管理 GUI 主题的颜色、间距、字号与动画时长，供 widget 与
    ThemeManager 读取。颜色令牌按当前主题返回 :class:`QColor`。
    """

    # ------------------------------------------------------------------
    # 主题读取（延迟导入，避免循环依赖与 T-A2 未实现时的 ImportError）
    # ------------------------------------------------------------------
    @staticmethod
    def _current_theme() -> str:
        """读取当前主题名，兜底返回 ``"light"``。

        尝试从 :class:`ThemeManager` 读取当前主题；若 T-A2 的
        ``ThemeManager`` 尚未实现（ImportError）或接口缺失
        （AttributeError），返回 ``"light"`` 默认值。
        """
        try:
            from chatterbox.gui.theme.theme_manager import ThemeManager

            return ThemeManager.instance().current_theme()
        except (ImportError, AttributeError):
            return "light"

    # ------------------------------------------------------------------
    # 颜色令牌：亮/暗双色映射表（hex 字符串）
    # ------------------------------------------------------------------
    _COLOR_SUCCESS: dict[str, str] = {
        "light": "#22c55e",
        "dark": "#4ade80",
    }
    _COLOR_FAILURE: dict[str, str] = {
        "light": "#dc3545",
        "dark": "#f87171",
    }
    _COLOR_WARNING: dict[str, str] = {
        "light": "#eab308",
        "dark": "#facc15",
    }
    _COLOR_INFO: dict[str, str] = {
        "light": "#3b82f6",
        "dark": "#60a5fa",
    }
    _COLOR_NEUTRAL: dict[str, str] = {
        "light": "#555555",
        "dark": "#9ca3af",
    }
    _COLOR_DRAG_SHADOW: dict[str, str] = {
        "light": "#7c93ff",
        "dark": "#7c93ff",
    }

    _COLOR_STATUS: dict[str, dict[str, str]] = {
        "idle": {"light": "#999999", "dark": "#9ca3af"},
        "running": {"light": "#3b82f6", "dark": "#60a5fa"},
        "success": {"light": "#22c55e", "dark": "#4ade80"},
        "error": {"light": "#ef4444", "dark": "#f87171"},
    }

    # 失败率 → 颜色关键点（亮/暗）
    _FAILURE_RATE_COLORS: dict[str, list[tuple[float, str]]] = {
        "light": [
            (0.0, "#22c55e"),
            (0.15, "#eab308"),
            (0.30, "#f97316"),
            (0.50, "#ef4444"),
        ],
        "dark": [
            (0.0, "#4ade80"),
            (0.15, "#facc15"),
            (0.30, "#fb923c"),
            (0.50, "#f87171"),
        ],
    }

    # 日志级别 → CSS 颜色名（亮/暗）
    _LOG_LEVEL_COLORS: dict[str, dict[str, str]] = {
        "light": {
            "ERROR": "red",
            "CRITICAL": "red",
            "WARNING": "#cc9a00",
            "DEBUG": "gray",
        },
        "dark": {
            "ERROR": "#f87171",
            "CRITICAL": "#f87171",
            "WARNING": "#facc15",
            "DEBUG": "#9ca3af",
        },
    }

    # ------------------------------------------------------------------
    # 颜色令牌：classmethod
    # ------------------------------------------------------------------
    @classmethod
    def color_success(cls) -> QColor:
        """成功色（亮 ``#22c55e`` / 暗 ``#4ade80``）。"""
        return QColor(cls._COLOR_SUCCESS[cls._current_theme()])

    @classmethod
    def color_failure(cls) -> QColor:
        """失败色（亮 ``#dc3545`` / 暗 ``#f87171``）。"""
        return QColor(cls._COLOR_FAILURE[cls._current_theme()])

    @classmethod
    def color_warning(cls) -> QColor:
        """警告色（亮 ``#eab308`` / 暗 ``#facc15``）。"""
        return QColor(cls._COLOR_WARNING[cls._current_theme()])

    @classmethod
    def color_info(cls) -> QColor:
        """信息色（亮 ``#3b82f6`` / 暗 ``#60a5fa``）。"""
        return QColor(cls._COLOR_INFO[cls._current_theme()])

    @classmethod
    def color_neutral(cls) -> QColor:
        """中性灰（亮 ``#555555`` / 暗 ``#9ca3af``）。"""
        return QColor(cls._COLOR_NEUTRAL[cls._current_theme()])

    @classmethod
    def color_drag_shadow(cls) -> QColor:
        """拖拽阴影色（亮/暗均 ``#7c93ff``）。"""
        return QColor(cls._COLOR_DRAG_SHADOW[cls._current_theme()])

    @classmethod
    def color_status(cls, state: str) -> QColor:
        """按状态名返回状态色。

        Args:
            state: 状态名（``"idle"``、``"running"``、``"success"``、
                ``"error"``）。未知状态视为 ``"idle"``（容错）。

        Returns:
            对应状态的 :class:`QColor`。
        """
        theme = cls._current_theme()
        mapping = cls._COLOR_STATUS.get(state)
        if mapping is None:
            # 未知状态容错：返回 idle 颜色
            return QColor(cls._COLOR_STATUS["idle"][theme])
        return QColor(mapping[theme])

    @classmethod
    def failure_rate_colors(cls) -> list[tuple[float, QColor]]:
        """返回失败率 → 颜色关键点列表（4 个，用于线性插值）。

        亮主题：``0.0→#22c55e``、``0.15→#eab308``、
        ``0.30→#f97316``、``0.50→#ef4444``
        暗主题：对应调亮版本。
        """
        theme = cls._current_theme()
        return [
            (rate, QColor(hex_)) for rate, hex_ in cls._FAILURE_RATE_COLORS[theme]
        ]

    @classmethod
    def log_level_colors(cls) -> dict[str, str]:
        """返回日志级别 → CSS 颜色名映射。

        与现有 ``_LEVEL_COLORS`` 一致，包含
        ``ERROR`` / ``CRITICAL`` / ``WARNING`` / ``DEBUG`` 四个键。
        """
        return dict(cls._LOG_LEVEL_COLORS[cls._current_theme()])

    # ------------------------------------------------------------------
    # 间距令牌（像素）
    # ------------------------------------------------------------------
    _SPACING: dict[str, dict[str, int]] = {
        "xs": {"compact": 2, "comfortable": 4},
        "sm": {"compact": 4, "comfortable": 8},
        "md": {"compact": 8, "comfortable": 12},
        "lg": {"compact": 12, "comfortable": 16},
    }

    @classmethod
    def spacing_xs(cls, density: str = "comfortable") -> int:
        """超小间距（compact: 2 / comfortable: 4）。"""
        return cls._SPACING["xs"][density]

    @classmethod
    def spacing_sm(cls, density: str = "comfortable") -> int:
        """小间距（compact: 4 / comfortable: 8）。"""
        return cls._SPACING["sm"][density]

    @classmethod
    def spacing_md(cls, density: str = "comfortable") -> int:
        """中间距（compact: 8 / comfortable: 12）。"""
        return cls._SPACING["md"][density]

    @classmethod
    def spacing_lg(cls, density: str = "comfortable") -> int:
        """大间距（compact: 12 / comfortable: 16）。"""
        return cls._SPACING["lg"][density]

    # ------------------------------------------------------------------
    # 字号令牌
    # ------------------------------------------------------------------
    @classmethod
    def font_sm(cls, scale: float = 1.0) -> int:
        """小字号（基础 9 × scale）。"""
        return max(1, round(9 * scale))

    @classmethod
    def font_md(cls, scale: float = 1.0) -> int:
        """中字号（基础 10 × scale）。"""
        return max(1, round(10 * scale))

    @classmethod
    def font_lg(cls, scale: float = 1.0) -> int:
        """大字号（基础 12 × scale）。"""
        return max(1, round(12 * scale))

    # ------------------------------------------------------------------
    # 动画时长令牌（毫秒）
    # ------------------------------------------------------------------
    @classmethod
    def anim_duration_short(cls) -> int:
        """短动画时长（150ms）。"""
        return 150

    @classmethod
    def anim_duration_default(cls) -> int:
        """默认动画时长（200ms）。"""
        return 200

    @classmethod
    def anim_duration_long(cls) -> int:
        """长动画时长（400ms）。"""
        return 400


__all__ = ["DesignTokens"]
