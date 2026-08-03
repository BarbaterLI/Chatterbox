"""DesignTokens 单元测试。

验证 T-A1 设计令牌模块：
- 颜色 classmethod 返回 ``QColor`` 实例且 RGB 值符合预期（亮主题默认值）
- 通过 mock ``ThemeManager.current_theme()`` 返回 ``"dark"`` 时，颜色返回暗主题对应值
- ``spacing_*`` 按密度返回正确值
- ``font_*`` 按 scale 返回正确值
- ``failure_rate_colors()`` 返回 4 个关键点
- ``log_level_colors()`` 包含 ERROR / WARNING / DEBUG 键
- ``color_status`` 各状态返回对应颜色，未知状态容错
- ``anim_duration_*`` 返回正确毫秒值
- ThemeManager 不可用时兜底返回 ``"light"``
"""
from __future__ import annotations

import os
import sys

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.gui.theme.design_tokens import DesignTokens


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 暗主题 fixture：注入模拟的 ThemeManager 模块，使 _current_theme 返回 "dark"
# ---------------------------------------------------------------------------
_THEME_MODULE_KEY = "balcon_batch_tts.gui.theme.theme_manager"


@pytest.fixture
def dark_theme():
    """注入模拟的 ThemeManager 模块，使 ``_current_theme`` 返回 ``"dark"``。

    通过 ``sys.modules`` 注入一个 ``MagicMock`` 模块，其 ``ThemeManager``
    属性的 ``instance().current_theme()`` 返回 ``"dark"``，模拟 T-A2
    ThemeManager 在暗主题下的行为。测试结束后恢复原状。
    """
    mock_module = MagicMock()
    mock_instance = MagicMock()
    mock_instance.current_theme.return_value = "dark"
    mock_module.ThemeManager.instance.return_value = mock_instance

    original = sys.modules.get(_THEME_MODULE_KEY)
    sys.modules[_THEME_MODULE_KEY] = mock_module
    yield
    if original is not None:
        sys.modules[_THEME_MODULE_KEY] = original
    else:
        sys.modules.pop(_THEME_MODULE_KEY, None)


# ---------------------------------------------------------------------------
# 辅助：断言 QColor 与 hex 字符串 RGB 匹配
# ---------------------------------------------------------------------------
def _assert_color_hex(color: QColor, hex_expected: str) -> None:
    """断言 QColor 的 RGB 分量与 hex 字符串一致。"""
    expected = QColor(hex_expected)
    assert color.red() == expected.red(), (
        f"red mismatch: {color.red()} != {expected.red()} ({hex_expected})"
    )
    assert color.green() == expected.green(), (
        f"green mismatch: {color.green()} != {expected.green()} ({hex_expected})"
    )
    assert color.blue() == expected.blue(), (
        f"blue mismatch: {color.blue()} != {expected.blue()} ({hex_expected})"
    )


# ---------------------------------------------------------------------------
# 颜色令牌（亮主题默认值）
# ---------------------------------------------------------------------------
class TestLightThemeColors:
    """验证亮主题（默认）下颜色令牌返回正确的 QColor。"""

    def test_color_success(self, qapp):
        color = DesignTokens.color_success()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#22c55e")

    def test_color_failure(self, qapp):
        color = DesignTokens.color_failure()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#dc3545")

    def test_color_warning(self, qapp):
        color = DesignTokens.color_warning()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#eab308")

    def test_color_info(self, qapp):
        color = DesignTokens.color_info()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#3b82f6")

    def test_color_neutral(self, qapp):
        color = DesignTokens.color_neutral()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#555555")

    def test_color_drag_shadow(self, qapp):
        color = DesignTokens.color_drag_shadow()
        assert isinstance(color, QColor)
        _assert_color_hex(color, "#7c93ff")


# ---------------------------------------------------------------------------
# 暗主题颜色（通过 mock ThemeManager.current_theme() 返回 "dark"）
# ---------------------------------------------------------------------------
class TestDarkThemeColors:
    """验证暗主题下颜色令牌返回调亮后的 QColor。"""

    def test_color_success_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_success(), "#4ade80")

    def test_color_failure_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_failure(), "#f87171")

    def test_color_warning_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_warning(), "#facc15")

    def test_color_info_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_info(), "#60a5fa")

    def test_color_neutral_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_neutral(), "#9ca3af")

    def test_color_drag_shadow_dark(self, dark_theme, qapp):
        _assert_color_hex(DesignTokens.color_drag_shadow(), "#7c93ff")


# ---------------------------------------------------------------------------
# color_status
# ---------------------------------------------------------------------------
class TestColorStatus:
    """验证 color_status 按 state 返回对应颜色，未知状态容错。"""

    def test_idle(self, qapp):
        _assert_color_hex(DesignTokens.color_status("idle"), "#999999")

    def test_running(self, qapp):
        _assert_color_hex(DesignTokens.color_status("running"), "#3b82f6")

    def test_success(self, qapp):
        _assert_color_hex(DesignTokens.color_status("success"), "#22c55e")

    def test_error(self, qapp):
        _assert_color_hex(DesignTokens.color_status("error"), "#ef4444")

    def test_unknown_returns_idle_color(self, qapp):
        """未知状态返回 idle 颜色（容错）。"""
        unknown_color = DesignTokens.color_status("unknown")
        idle_color = DesignTokens.color_status("idle")
        _assert_color_hex(unknown_color, "#999999")
        assert unknown_color.red() == idle_color.red()
        assert unknown_color.green() == idle_color.green()
        assert unknown_color.blue() == idle_color.blue()

    def test_status_returns_qcolor(self, qapp):
        assert isinstance(DesignTokens.color_status("idle"), QColor)

    def test_status_dark_theme(self, dark_theme, qapp):
        """暗主题下各状态颜色调亮。"""
        _assert_color_hex(DesignTokens.color_status("idle"), "#9ca3af")
        _assert_color_hex(DesignTokens.color_status("running"), "#60a5fa")
        _assert_color_hex(DesignTokens.color_status("success"), "#4ade80")
        _assert_color_hex(DesignTokens.color_status("error"), "#f87171")

    def test_unknown_dark_theme(self, dark_theme, qapp):
        """暗主题下未知状态返回 idle 暗色。"""
        _assert_color_hex(DesignTokens.color_status("unknown"), "#9ca3af")


# ---------------------------------------------------------------------------
# failure_rate_colors
# ---------------------------------------------------------------------------
class TestFailureRateColors:
    """验证 failure_rate_colors 返回 4 个关键点。"""

    def test_returns_4_keypoints(self, qapp):
        colors = DesignTokens.failure_rate_colors()
        assert len(colors) == 4

    def test_keypoints_rates(self, qapp):
        colors = DesignTokens.failure_rate_colors()
        rates = [r for r, _ in colors]
        assert rates == [0.0, 0.15, 0.30, 0.50]

    def test_keypoints_are_qcolor(self, qapp):
        colors = DesignTokens.failure_rate_colors()
        for _, color in colors:
            assert isinstance(color, QColor)

    def test_light_theme_values(self, qapp):
        colors = DesignTokens.failure_rate_colors()
        _assert_color_hex(colors[0][1], "#22c55e")
        _assert_color_hex(colors[1][1], "#eab308")
        _assert_color_hex(colors[2][1], "#f97316")
        _assert_color_hex(colors[3][1], "#ef4444")

    def test_dark_theme_values(self, dark_theme, qapp):
        colors = DesignTokens.failure_rate_colors()
        _assert_color_hex(colors[0][1], "#4ade80")
        _assert_color_hex(colors[1][1], "#facc15")
        _assert_color_hex(colors[2][1], "#fb923c")
        _assert_color_hex(colors[3][1], "#f87171")


# ---------------------------------------------------------------------------
# log_level_colors
# ---------------------------------------------------------------------------
class TestLogLevelColors:
    """验证 log_level_colors 包含 ERROR / WARNING / DEBUG 键。"""

    def test_contains_error(self, qapp):
        assert "ERROR" in DesignTokens.log_level_colors()

    def test_contains_warning(self, qapp):
        assert "WARNING" in DesignTokens.log_level_colors()

    def test_contains_debug(self, qapp):
        assert "DEBUG" in DesignTokens.log_level_colors()

    def test_contains_critical(self, qapp):
        assert "CRITICAL" in DesignTokens.log_level_colors()

    def test_error_is_red_light(self, qapp):
        assert DesignTokens.log_level_colors()["ERROR"] == "red"

    def test_warning_light(self, qapp):
        assert DesignTokens.log_level_colors()["WARNING"] == "#cc9a00"

    def test_debug_light(self, qapp):
        assert DesignTokens.log_level_colors()["DEBUG"] == "gray"

    def test_dark_theme_values(self, dark_theme, qapp):
        colors = DesignTokens.log_level_colors()
        assert colors["ERROR"] == "#f87171"
        assert colors["CRITICAL"] == "#f87171"
        assert colors["WARNING"] == "#facc15"
        assert colors["DEBUG"] == "#9ca3af"


# ---------------------------------------------------------------------------
# 间距令牌
# ---------------------------------------------------------------------------
class TestSpacing:
    """验证 spacing_* 按密度返回正确值。"""

    def test_spacing_xs_comfortable(self):
        assert DesignTokens.spacing_xs() == 4

    def test_spacing_xs_compact(self):
        assert DesignTokens.spacing_xs("compact") == 2

    def test_spacing_sm_comfortable(self):
        assert DesignTokens.spacing_sm() == 8

    def test_spacing_sm_compact(self):
        assert DesignTokens.spacing_sm("compact") == 4

    def test_spacing_md_comfortable(self):
        assert DesignTokens.spacing_md() == 12

    def test_spacing_md_compact(self):
        assert DesignTokens.spacing_md("compact") == 8

    def test_spacing_lg_comfortable(self):
        assert DesignTokens.spacing_lg() == 16

    def test_spacing_lg_compact(self):
        assert DesignTokens.spacing_lg("compact") == 12

    def test_spacing_returns_int(self):
        assert isinstance(DesignTokens.spacing_xs(), int)
        assert isinstance(DesignTokens.spacing_lg("compact"), int)


# ---------------------------------------------------------------------------
# 字号令牌
# ---------------------------------------------------------------------------
class TestFont:
    """验证 font_* 按 scale 返回正确值。"""

    def test_font_sm_default(self):
        assert DesignTokens.font_sm() == 9

    def test_font_md_default(self):
        assert DesignTokens.font_md() == 10

    def test_font_lg_default(self):
        assert DesignTokens.font_lg() == 12

    def test_font_sm_scaled(self):
        assert DesignTokens.font_sm(1.5) == 14  # 9 * 1.5 = 13.5 → 14

    def test_font_md_scaled(self):
        assert DesignTokens.font_md(1.2) == 12  # 10 * 1.2 = 12

    def test_font_lg_scaled(self):
        assert DesignTokens.font_lg(2.0) == 24  # 12 * 2.0 = 24

    def test_font_returns_int(self):
        assert isinstance(DesignTokens.font_sm(), int)
        assert isinstance(DesignTokens.font_md(1.5), int)


# ---------------------------------------------------------------------------
# 动画时长令牌
# ---------------------------------------------------------------------------
class TestAnimDuration:
    """验证 anim_duration_* 返回正确毫秒值。"""

    def test_short(self):
        assert DesignTokens.anim_duration_short() == 150

    def test_default(self):
        assert DesignTokens.anim_duration_default() == 200

    def test_long(self):
        assert DesignTokens.anim_duration_long() == 400

    def test_returns_int(self):
        assert isinstance(DesignTokens.anim_duration_short(), int)


# ---------------------------------------------------------------------------
# 兜底逻辑：ThemeManager 不可用时返回 light
# ---------------------------------------------------------------------------
class TestFallback:
    """验证 ThemeManager 未实现时兜底返回 light 主题。"""

    def test_current_theme_fallback_to_light(self):
        """ThemeManager 模块不存在时，_current_theme 返回 'light'。"""
        # theme_manager 模块尚未实现（T-A2），应兜底返回 "light"
        assert DesignTokens._current_theme() == "light"

    def test_color_success_fallback(self, qapp):
        """兜底时 color_success 返回亮主题值。"""
        _assert_color_hex(DesignTokens.color_success(), "#22c55e")
