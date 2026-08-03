"""InlineIndicator 单元测试。

验证 T-D1 内联指示器组件：
- 默认 hidden 状态，``isVisible()`` 返回 False（在父 widget ``show()`` 后验证）
- ``set_state("ok", ...)`` 后 widget 可见，label 文本包含给定文本
- ``set_state("error", ...)`` 后 label 文本包含给定文本
- ``set_state("warning", ...)`` 后 WindowText 颜色为 ``color_warning()``
- ``set_state("info", ...)`` 后 WindowText 颜色为 ``color_info()``
- ``set_state("hidden")`` 后 widget 不可见
- ``clicked`` 信号在 ``linkActivated`` 触发时发射
- tooltip 设置正确

测试在 offscreen Qt 平台下运行，无需真实显示设备。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from balcon_batch_tts.gui.theme.design_tokens import DesignTokens
from balcon_batch_tts.gui.widgets.inline_indicator import InlineIndicator


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """返回全局 QApplication 单例（offscreen 模式）。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def host(qapp: QApplication) -> QWidget:
    """返回一个已 show 的父 widget。

    父 widget 可见后，子 widget 的 ``isVisible()`` 仅取决于其自身显式
    可见性（``setVisible(True/False)``），从而可准确反映 InlineIndicator
    的 hidden / 显示状态。
    """
    parent = QWidget()
    parent.show()
    qapp.processEvents()
    return parent


@pytest.fixture
def indicator(host: QWidget) -> InlineIndicator:
    """返回挂载在已显示父 widget 下的 InlineIndicator（默认 hidden）。"""
    return InlineIndicator(host)


# ---------------------------------------------------------------------------
# 辅助：断言 QLabel 的 WindowText 颜色与给定 QColor 一致
# ---------------------------------------------------------------------------
def _assert_windowtext_color(label, expected: QColor) -> None:
    color = label.palette().color(QPalette.ColorRole.WindowText)
    assert color.red() == expected.red(), (
        f"red mismatch: {color.red()} != {expected.red()}"
    )
    assert color.green() == expected.green(), (
        f"green mismatch: {color.green()} != {expected.green()}"
    )
    assert color.blue() == expected.blue(), (
        f"blue mismatch: {color.blue()} != {expected.blue()}"
    )


# ---------------------------------------------------------------------------
# 默认状态
# ---------------------------------------------------------------------------
class TestInitialState:
    """构造后默认 hidden 状态契约。"""

    def test_default_hidden_not_visible(self, indicator: InlineIndicator) -> None:
        """默认 hidden，父 widget 已 show，indicator 不可见。"""
        assert not indicator.isVisible()

    def test_default_state_is_hidden(self, indicator: InlineIndicator) -> None:
        assert indicator._state == "hidden"


# ---------------------------------------------------------------------------
# set_state 文本与可见性
# ---------------------------------------------------------------------------
class TestSetText:
    """set_state 各状态的文本与可见性。"""

    def test_ok_visible_and_text(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok", "路径有效")
        assert indicator.isVisible()
        assert "路径有效" in indicator._label.text()

    def test_error_text(self, indicator: InlineIndicator) -> None:
        indicator.set_state("error", "路径无效")
        assert indicator.isVisible()
        assert "路径无效" in indicator._label.text()

    def test_ok_text_contains_icon(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok", "路径有效")
        assert "✓" in indicator._label.text()

    def test_error_text_contains_icon(self, indicator: InlineIndicator) -> None:
        indicator.set_state("error", "路径无效")
        assert "✗" in indicator._label.text()

    def test_text_as_link(self, indicator: InlineIndicator) -> None:
        """非空文本以 <a href="#"> 富文本形式显示，便于视觉提示。"""
        indicator.set_state("ok", "路径有效")
        text = indicator._label.text()
        assert '<a href="#">路径有效</a>' in text

    def test_empty_text_shows_only_icon(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok")
        assert indicator._label.text() == "✓"


# ---------------------------------------------------------------------------
# 颜色（通过 QPalette WindowText 角色）
# ---------------------------------------------------------------------------
class TestColors:
    """set_state 各状态的颜色通过 QPalette.WindowText 应用。"""

    def test_warning_color(self, indicator: InlineIndicator) -> None:
        indicator.set_state("warning", "警告")
        _assert_windowtext_color(indicator._label, DesignTokens.color_warning())

    def test_info_color(self, indicator: InlineIndicator) -> None:
        indicator.set_state("info", "提示")
        _assert_windowtext_color(indicator._label, DesignTokens.color_info())

    def test_ok_color(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok", "有效")
        _assert_windowtext_color(indicator._label, DesignTokens.color_success())

    def test_error_color(self, indicator: InlineIndicator) -> None:
        indicator.set_state("error", "无效")
        _assert_windowtext_color(indicator._label, DesignTokens.color_failure())

    def test_autofill_background_false(self, indicator: InlineIndicator) -> None:
        """QLabel 保持透明背景（setAutoFillBackground(False)）。"""
        indicator.set_state("ok", "有效")
        assert indicator._label.autoFillBackground() is False


# ---------------------------------------------------------------------------
# hidden 状态
# ---------------------------------------------------------------------------
class TestHidden:
    """set_state("hidden") 行为。"""

    def test_hidden_after_visible(self, indicator: InlineIndicator) -> None:
        """先显示再隐藏：widget 不可见。"""
        indicator.set_state("ok", "路径有效")
        assert indicator.isVisible()
        indicator.set_state("hidden")
        assert not indicator.isVisible()

    def test_hidden_default_state(self, indicator: InlineIndicator) -> None:
        """默认 hidden：widget 不可见。"""
        assert not indicator.isVisible()
        indicator.set_state("hidden")
        assert not indicator.isVisible()


# ---------------------------------------------------------------------------
# clicked 信号（通过 linkActivated 模拟点击）
# ---------------------------------------------------------------------------
class TestClickedSignal:
    """clicked 信号在 linkActivated 触发时发射。"""

    def test_clicked_emitted_on_link_activation(
        self, indicator: InlineIndicator
    ) -> None:
        received: list[bool] = []
        indicator.clicked.connect(lambda: received.append(True))
        indicator.set_state("ok", "路径有效")
        # 模拟点击 label 中的链接
        indicator._label.linkActivated.emit("#")
        assert len(received) == 1

    def test_clicked_not_emitted_when_hidden(
        self, indicator: InlineIndicator
    ) -> None:
        received: list[bool] = []
        indicator.clicked.connect(lambda: received.append(True))
        # hidden 状态下 label 不显示，但仍可验证信号未触发
        indicator.set_state("hidden")
        assert len(received) == 0


# ---------------------------------------------------------------------------
# tooltip
# ---------------------------------------------------------------------------
class TestTooltip:
    """tooltip 设置正确。"""

    def test_tooltip_on_label(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok", "路径有效", "点击修复路径")
        assert indicator._label.toolTip() == "点击修复路径"

    def test_tooltip_on_widget(self, indicator: InlineIndicator) -> None:
        indicator.set_state("error", "路径无效", "错误提示")
        assert indicator.toolTip() == "错误提示"

    def test_empty_tooltip(self, indicator: InlineIndicator) -> None:
        indicator.set_state("ok", "路径有效")
        assert indicator._label.toolTip() == ""
