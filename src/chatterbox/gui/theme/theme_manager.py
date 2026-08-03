"""主题管理器单例：ThemeManager。

提供 ``ThemeManager(QObject)`` 单例，集中管理 GUI 主题（亮/暗/跟随系统）、
密度与字号缩放。所有视觉变化通过 ``QPalette`` 实现，不引入自定义 QSS。

主题应用：
- ``apply_theme("light")`` / ``apply_theme("dark")``：构造对应调色板并应用
- ``apply_theme("auto")``：根据 ``QGuiApplication.styleHints().colorScheme()``
  判断亮/暗，调用对应构造

跟随系统：
- 监听 ``QGuiApplication.paletteChanged`` 信号，仅在 auto 模式下重新应用主题
- 使用 ``_applying`` 标志位屏蔽递归（setPalette 会再次触发 paletteChanged）

约束：
- 使用 PySide6（QPalette / QColor），Qt6 原生风格。
- 禁止引入自定义 QSS（``setStyleSheet``）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import (
    QGuiApplication,
    QPalette,
    QColor,
    QBrush,
    QFont,
)
from PySide6.QtWidgets import QApplication


class ThemeManager(QObject):
    """主题管理器单例（QObject）。

    集中管理亮/暗主题、密度与字号缩放，通过 ``QPalette`` 应用视觉变化，
    不引入自定义 QSS。

    Usage:
        >>> mgr = ThemeManager.instance()
        >>> mgr.apply_theme("dark")
        >>> mgr.current_theme()
        'dark'
    """

    theme_changed = Signal(str)

    _instance: "ThemeManager | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._theme_setting: str = "auto"
        self._current_theme: str = "light"
        self._current_density: str = "comfortable"
        self._current_font_scale: float = 1.0
        self._applying: bool = False

        # 监听系统调色板变化（用于 auto 模式跟随系统主题）
        app = QGuiApplication.instance()
        if app is not None:
            app.paletteChanged.connect(self._on_palette_changed)

    @classmethod
    def instance(cls) -> "ThemeManager":
        """返回全局唯一实例（首次调用时创建）。

        Note:
            QObject 不能用 ``__new__`` 直接单例（会有 parent 问题），
            此处用类变量 ``_instance`` 持有，首次调用时 ``cls()`` 创建。
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # 调色板构造
    # ------------------------------------------------------------------
    @staticmethod
    def _build_light_palette() -> QPalette:
        """构造亮色调色板。

        基于 ``QPalette()`` 默认，背景调整为浅色 ``#f8f8f8``、文本为深色
        ``#1f2937``。
        """
        palette = QPalette()
        bg = QColor("#f8f8f8")
        text = QColor("#1f2937")
        base = QColor("#ffffff")
        alt_base = QColor("#f0f0f0")
        button = QColor("#e8e8e8")
        highlight = QColor("#3b82f6")
        highlighted_text = QColor("#ffffff")
        placeholder = QColor("#9ca3af")

        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, alt_base)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.Button, button)
        palette.setColor(QPalette.ColorRole.ButtonText, text)
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
        palette.setColor(QPalette.ColorRole.ToolTipText, text)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(QPalette.ColorRole.HighlightedText, highlighted_text)
        palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
        return palette

    @staticmethod
    def _build_dark_palette() -> QPalette:
        """构造暗色调色板。

        背景 ``#1e1e2e``、文本 ``#e5e7eb``、基色 ``#2d2d3f``、
        提示文本 ``#9ca3af``、高亮 ``#3b82f6``。
        """
        palette = QPalette()
        bg = QColor("#1e1e2e")
        text = QColor("#e5e7eb")
        base = QColor("#2d2d3f")
        alt_base = QColor("#252535")
        button = QColor("#2d2d3f")
        highlight = QColor("#3b82f6")
        highlighted_text = QColor("#ffffff")
        placeholder = QColor("#9ca3af")

        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, alt_base)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.Button, button)
        palette.setColor(QPalette.ColorRole.ButtonText, text)
        palette.setColor(QPalette.ColorRole.ToolTipBase, base)
        palette.setColor(QPalette.ColorRole.ToolTipText, text)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(QPalette.ColorRole.HighlightedText, highlighted_text)
        palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
        return palette

    # ------------------------------------------------------------------
    # 主题应用
    # ------------------------------------------------------------------
    def apply_theme(self, theme: str) -> None:
        """应用主题（light / dark / auto）。

        - ``"light"``：构造亮色调色板
        - ``"dark"``：构造暗色调色板
        - ``"auto"``：根据 ``QGuiApplication.styleHints().colorScheme()``
          判断亮/暗后调用对应构造

        调用 ``QApplication.setPalette(palette)`` 一次性应用，设置
        ``self._current_theme``（auto 模式下记录实际解析后的 light/dark），
        并发射 ``theme_changed`` 信号。

        Args:
            theme: ``"light"``、``"dark"`` 或 ``"auto"``。
        """
        self._theme_setting = theme
        self._applying = True
        try:
            if theme == "light":
                palette = self._build_light_palette()
                resolved = "light"
            elif theme == "dark":
                palette = self._build_dark_palette()
                resolved = "dark"
            elif theme == "auto":
                scheme = QGuiApplication.styleHints().colorScheme()
                if scheme == Qt.ColorScheme.Dark:
                    palette = self._build_dark_palette()
                    resolved = "dark"
                else:
                    palette = self._build_light_palette()
                    resolved = "light"
            else:
                raise ValueError(f"Unknown theme: {theme!r}")

            QApplication.setPalette(palette)
            self._current_theme = resolved
        finally:
            self._applying = False
        self.theme_changed.emit(self._current_theme)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def current_theme(self) -> str:
        """返回实际生效主题（``"light"`` 或 ``"dark"``，不返回 ``"auto"``）。"""
        return self._current_theme

    def current_density(self) -> str:
        """返回当前密度（``"comfortable"`` 或 ``"compact"``）。"""
        return self._current_density

    def current_font_scale(self) -> float:
        """返回当前字号缩放系数。"""
        return self._current_font_scale

    # ------------------------------------------------------------------
    # 密度与字号
    # ------------------------------------------------------------------
    def apply_density(self, density: str) -> None:
        """设置当前密度。

        仅记录状态；间距令牌通过 ``DesignTokens`` 读取时传入 density 参数。

        Args:
            density: ``"comfortable"`` 或 ``"compact"``。
        """
        self._current_density = density

    def apply_font_scale(self, scale: float) -> None:
        """设置字号缩放并应用全局字体。

        基础字号 9pt × scale，保留原字体族，仅修改 pointSize。

        Args:
            scale: 字号缩放系数（``1.0`` 为默认）。
        """
        self._current_font_scale = scale
        app = QApplication.instance()
        if app is None:
            return
        current_font = app.font()
        new_font = QFont(current_font)
        new_font.setPointSize(max(1, round(9 * scale)))
        QApplication.setFont(new_font)

    # ------------------------------------------------------------------
    # 跟随系统
    # ------------------------------------------------------------------
    def _on_palette_changed(self, palette: QPalette) -> None:
        """系统调色板变化时重新应用主题（仅 auto 模式）。

        仅当 ``self._theme_setting == "auto"`` 时响应，重新调用
        ``apply_theme("auto")``。通过 ``self._applying`` 标志位屏蔽
        ``setPalette`` 引发的递归调用。
        """
        if self._applying:
            return
        if self._theme_setting == "auto":
            self.apply_theme("auto")


__all__ = ["ThemeManager"]
