"""ThemeManager 单元测试。

验证 T-A2 主题管理器单例：
- ``instance()`` 单例契约
- ``apply_theme("light")`` / ``apply_theme("dark")`` / ``apply_theme("auto")``
- ``current_theme()`` 返回实际主题（light/dark，不返回 auto）
- ``apply_density()`` / ``apply_font_scale()`` 状态记录
- ``theme_changed`` 信号在主题切换时发射

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.gui.theme.theme_manager import ThemeManager


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 辅助：捕获 theme_changed 信号，测试结束自动断开连接
# ---------------------------------------------------------------------------
@pytest.fixture
def theme_changed_spy(qapp) -> "list[str]":
    """捕获 ``theme_changed`` 信号参数，测试结束自动断开连接。

    Returns:
        接收到的主题名列表（每次 ``theme_changed`` 发射追加一个元素）。
    """
    mgr = ThemeManager.instance()
    received: list[str] = []
    slot = lambda theme: received.append(theme)
    mgr.theme_changed.connect(slot)
    yield received
    try:
        mgr.theme_changed.disconnect(slot)
    except (RuntimeError, TypeError):
        pass


# ---------------------------------------------------------------------------
# 单例契约
# ---------------------------------------------------------------------------
class TestSingleton:
    """``instance()`` 单例契约。"""

    def test_instance_returns_same_object(self, qapp: QApplication) -> None:
        mgr1 = ThemeManager.instance()
        mgr2 = ThemeManager.instance()
        assert mgr1 is mgr2


# ---------------------------------------------------------------------------
# 主题应用
# ---------------------------------------------------------------------------
class TestApplyTheme:
    """验证 ``apply_theme`` 各模式。"""

    def test_apply_light(self, qapp: QApplication, theme_changed_spy: list) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_theme("light")
        assert mgr.current_theme() == "light"
        assert "light" in theme_changed_spy

    def test_apply_dark(self, qapp: QApplication, theme_changed_spy: list) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_theme("dark")
        assert mgr.current_theme() == "dark"
        assert "dark" in theme_changed_spy

    def test_apply_auto_no_crash(self, qapp: QApplication) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_theme("auto")
        assert mgr.current_theme() in ("light", "dark")


# ---------------------------------------------------------------------------
# 密度与字号
# ---------------------------------------------------------------------------
class TestDensityAndFont:
    """验证密度与字号缩放。"""

    def test_apply_density(self, qapp: QApplication) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_density("compact")
        assert mgr.current_density() == "compact"

    def test_apply_font_scale(self, qapp: QApplication) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_font_scale(1.2)
        assert mgr.current_font_scale() == 1.2


# ---------------------------------------------------------------------------
# theme_changed 信号
# ---------------------------------------------------------------------------
class TestThemeChangedSignal:
    """验证 ``theme_changed`` 信号在主题切换时发射。"""

    def test_signal_emitted_on_switch(
        self, qapp: QApplication, theme_changed_spy: list
    ) -> None:
        mgr = ThemeManager.instance()
        mgr.apply_theme("dark")
        mgr.apply_theme("light")
        assert "dark" in theme_changed_spy
        assert "light" in theme_changed_spy
