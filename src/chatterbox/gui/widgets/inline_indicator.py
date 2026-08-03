"""内联指示器组件：在行内显示状态图标与可选的可点击文本。

提供 :class:`InlineIndicator`，用于在表单/路径输入行下方显示一行
状态反馈（如「balcon 路径无效，点击修复」）：

- 通过 Unicode 字符（``✓`` / ``✗`` / ``⚠`` / ``ℹ``）表示状态图标，
  颜色取自 :class:`DesignTokens`（success / failure / warning / info）。
- 颜色通过 :class:`QPalette` 的 ``WindowText`` 角色应用到内部
  :class:`QLabel`，不使用自定义 QSS，保持 Qt6 原生风格。
- 文本可点击：当 ``text`` 非空且状态非 ``hidden`` 时，文本以
  ``<a href="#">text</a>`` 富文本形式显示，``QLabel`` 的 cursor 设为
  ``PointingHandCursor``，``linkActivated`` 信号转发为
  :attr:`InlineIndicator.clicked`。
- 初始状态为 ``"hidden"``（整个 widget 隐藏）。

约束：
- 使用 PySide6（QWidget / QLabel / QHBoxLayout）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS（``setStyleSheet``），颜色仅通过 ``QPalette`` 应用。
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from chatterbox.gui.theme.design_tokens import DesignTokens


# 状态 → (Unicode 图标, 颜色获取 callable)
# 颜色在 set_state 调用时按当前主题实时求值，避免模块加载时固化。
_STATE_CONFIG: dict[str, tuple[str, Callable[[], QColor]]] = {
    "ok": ("✓", DesignTokens.color_success),
    "error": ("✗", DesignTokens.color_failure),
    "warning": ("⚠", DesignTokens.color_warning),
    "info": ("ℹ", DesignTokens.color_info),
}


class InlineIndicator(QWidget):
    """内联状态指示器：图标 + 可选可点击文本。

    状态取值（str）：``"ok"`` / ``"error"`` / ``"warning"`` / ``"info"``
    / ``"hidden"``。前四种显示对应 Unicode 图标与颜色，``"hidden"``
    隐藏整个 widget。

    颜色通过 :class:`QPalette` 应用到内部 :class:`QLabel` 的
    ``WindowText`` 角色，不使用 QSS。当 ``text`` 非空时，文本以
    ``<a href="#">text</a>`` 富文本显示，cursor 设为
    ``PointingHandCursor``，``linkActivated`` 转发为 :attr:`clicked`。
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(self)
        self._label.setAutoFillBackground(False)
        # 允许鼠标点击富文本中的链接以触发 linkActivated
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        # linkActivated 携带 url 字符串，转发为无参 clicked 信号
        self._label.linkActivated.connect(lambda *_args: self.clicked.emit())
        layout.addWidget(self._label)

        self._state: str = "hidden"
        self.setVisible(False)

    def set_state(self, state: str, text: str = "", tooltip: str = "") -> None:
        """设置指示器状态、文本与 tooltip。

        Args:
            state: 状态名（``"ok"`` / ``"error"`` / ``"warning"`` /
                ``"info"`` / ``"hidden"``）。未知状态容错为 ``"info"``。
            text: 显示文本（如「balcon 路径无效，点击修复」）。
                为空时仅显示图标。
            tooltip: 鼠标悬停提示。
        """
        self._state = state

        if state == "hidden":
            self.setVisible(False)
            return

        config = _STATE_CONFIG.get(state)
        if config is None:
            # 未知状态容错：当作 info 处理
            config = _STATE_CONFIG["info"]
        icon, color_method = config
        color: QColor = color_method()

        # 颜色通过 QPalette 的 WindowText 角色应用，不使用 QSS
        palette = self._label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        self._label.setPalette(palette)
        self._label.setAutoFillBackground(False)

        # 文本：图标 + 可选的可点击链接富文本
        if text:
            self._label.setText(f'{icon} <a href="#">{text}</a>')
            self._label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self._label.setText(icon)
            self._label.unsetCursor()

        self._label.setToolTip(tooltip)
        self.setToolTip(tooltip)

        self.setVisible(True)


__all__ = ["InlineIndicator"]
