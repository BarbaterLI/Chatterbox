"""图标工厂：基于内嵌 SVG 字符串生成 QIcon，无需外部资源文件。

提供 :class:`IconProvider`，封装工具图标、Tab 分组图标与状态图标的
SVG 字典与渲染逻辑。所有 SVG 内嵌于本模块，避免对外部 ``.qrc`` /
``.svg`` 文件的依赖。

约束：
- 使用 PySide6（QIcon、QPixmap、QPainter、QSvgRenderer）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 不引入自定义 QSS，不强制继承 QSS color（保留 Qt 原版样式）。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from chatterbox.core.tool_type import ToolType
from chatterbox.gui.theme.design_tokens import DesignTokens

try:  # QSvgRenderer 在 PySide6 标准发行中通常可用，但作容错处理。
    from PySide6.QtSvg import QSvgRenderer
    _SVG_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失的兜底路径
    QSvgRenderer = None  # type: ignore[assignment,misc]
    _SVG_AVAILABLE = False

logger = logging.getLogger(__name__)

# 图标渲染像素尺寸（图标原始 viewBox 为 24x24，按此尺寸渲染保证清晰）
_RENDER_SIZE = 32

# 中性灰由 DesignTokens.color_neutral() 运行时按当前主题提供

# 中文分组名 → 英文 SVG 字典 key
# 包含 balcon 分组（输入输出/语音音频/字幕歌词/高级）与 blb2txt 分组
# （输入输出复用/文本处理/字典注释/表格CSV/EML/归档图像/其他）。
_GROUP_NAME_MAP: dict[str, str] = {
    "输入输出": "input_output",
    "语音音频": "voice_audio",
    "字幕歌词": "subtitle_lyrics",
    "高级": "advanced",
    "文本处理": "text_processing",
    "字典注释": "dictionary_notes",
    "表格CSV": "tables_csv",
    "EML": "eml",
    "归档图像": "archives_images",
    "其他": "misc",
}


class IconProvider:
    """图标提供者，内嵌 SVG 字符串生成 QIcon。

    所有方法均为 ``@classmethod``，无需实例化即可调用。SVG 字符串内嵌于
    类属性，工具/分组图标使用 ``currentColor`` 描边，渲染时替换为中性灰；
    状态图标直接以对应颜色填充，不依赖外部着色。
    """

    # 工具图标 SVG 字典（10 个）：24x24 viewBox，stroke 风格
    _TOOL_SVGS: dict[str, str] = {
        "add": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="12" y1="5" x2="12" y2="19"/>'
            '<line x1="5" y1="12" x2="19" y2="12"/>'
            '</svg>'
        ),
        "remove": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="3 6 5 6 21 6"/>'
            '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
            '<path d="M10 11v6M14 11v6"/>'
            '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
            '</svg>'
        ),
        "clear": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="18" y1="6" x2="6" y2="18"/>'
            '<line x1="6" y1="6" x2="18" y2="18"/>'
            '</svg>'
        ),
        "refresh": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="23 4 23 10 17 10"/>'
            '<polyline points="1 20 1 14 7 14"/>'
            '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36 '
            'A9 9 0 0 0 20.49 15"/>'
            '</svg>'
        ),
        "start": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<polygon points="5 3 19 12 5 21 5 3"/>'
            '</svg>'
        ),
        "stop": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="5" y="5" width="14" height="14" rx="1"/>'
            '</svg>'
        ),
        "preview": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
            '<circle cx="12" cy="12" r="3"/>'
            '</svg>'
        ),
        "save": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11 '
            'a2 2 0 0 1-2 2z"/>'
            '<polyline points="17 21 17 13 7 13 7 21"/>'
            '<polyline points="7 3 7 8 15 8"/>'
            '</svg>'
        ),
        "load": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
            '2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
            '</svg>'
        ),
        "settings": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="3"/>'
            '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 '
            '-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 '
            '0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 '
            '1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 '
            '1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09 '
            'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 '
            '0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 '
            '0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 '
            '1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 '
            '1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 '
            '4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
            '</svg>'
        ),
    }

    # 工具类型图标 SVG 字典（3 个）：balcon 喇叭 / blb2txt 文档提取 / sapi 声波
    # balcon/blb2txt 为 24x24 viewBox，sapi 为 16x16 viewBox，统一 stroke 风格
    _TOOL_TYPE_SVGS: dict[ToolType, str] = {
        ToolType.BALCON: (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M11 5 6 9H3a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h3l5 4z"/>'
            '<path d="M16 9a3 3 0 0 1 0 6"/>'
            '<path d="M19 7a7 7 0 0 1 0 10"/>'
            '</svg>'
        ),
        ToolType.BLB2TXT: (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M4 3h6l3 3v15a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 '
            '1 1-1z"/>'
            '<path d="M10 3v3h3"/>'
            '<line x1="6" y1="11" x2="9" y2="11"/>'
            '<line x1="6" y1="15" x2="9" y2="15"/>'
            '<path d="M16 12h6"/>'
            '<path d="M19 9l3 3-3 3"/>'
            '</svg>'
        ),
        ToolType.SAPI: (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
            'fill="none" stroke="currentColor" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="8" cy="8" r="2" fill="currentColor"/>'
            '<path d="M4 8a4 4 0 0 1 8 0"/>'
            '<path d="M2 8a6 6 0 0 1 12 0"/>'
            '</svg>'
        ),
    }

    # 分组图标 SVG 字典（10 个）：balcon 4 个 + blb2txt 6 个
    _TAB_GROUP_SVGS: dict[str, str] = {
        "input_output": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 7h6l2 2h6"/>'
            '<path d="M21 17h-6l-2-2H7"/>'
            '<polyline points="7 3 3 7 7 11"/>'
            '<polyline points="17 13 21 17 17 21"/>'
            '</svg>'
        ),
        "voice_audio": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
            '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
            '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
            '</svg>'
        ),
        "subtitle_lyrics": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="2" y="5" width="20" height="14" rx="2"/>'
            '<line x1="6" y1="11" x2="12" y2="11"/>'
            '<line x1="14" y1="11" x2="18" y2="11"/>'
            '<line x1="6" y1="15" x2="9" y2="15"/>'
            '<line x1="11" y1="15" x2="18" y2="15"/>'
            '</svg>'
        ),
        "advanced": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="4" y1="6" x2="20" y2="6"/>'
            '<line x1="4" y1="12" x2="20" y2="12"/>'
            '<line x1="4" y1="18" x2="20" y2="18"/>'
            '<circle cx="9" cy="6" r="2" fill="#ffffff"/>'
            '<circle cx="15" cy="12" r="2" fill="#ffffff"/>'
            '<circle cx="8" cy="18" r="2" fill="#ffffff"/>'
            '</svg>'
        ),
        # blb2txt 分组图标（6 个）：文本处理/字典注释/表格CSV/EML/归档图像/其他
        "text_processing": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 20h9"/>'
            '<path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 '
            '3.5z"/>'
            '</svg>'
        ),
        "dictionary_notes": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
            '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 '
            '0 1 6.5 2z"/>'
            '</svg>'
        ),
        "tables_csv": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="3" y="3" width="18" height="18" rx="1"/>'
            '<line x1="3" y1="9" x2="21" y2="9"/>'
            '<line x1="3" y1="15" x2="21" y2="15"/>'
            '<line x1="12" y1="3" x2="12" y2="21"/>'
            '</svg>'
        ),
        "eml": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="2" y="4" width="20" height="16" rx="2"/>'
            '<polyline points="22 6 12 13 2 6"/>'
            '</svg>'
        ),
        "archives_images": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="21 8 21 21 3 21 3 8"/>'
            '<rect x="1" y="3" width="22" height="5"/>'
            '<line x1="10" y1="12" x2="14" y2="12"/>'
            '</svg>'
        ),
        "misc": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="currentColor">'
            '<circle cx="5" cy="12" r="1.5"/>'
            '<circle cx="12" cy="12" r="1.5"/>'
            '<circle cx="19" cy="12" r="1.5"/>'
            '</svg>'
        ),
    }

    # 状态图标 SVG 字典（4 个）：24x24 viewBox，圆形使用 currentColor
    # 渲染时由 DesignTokens.color_status(state) 提供具体颜色
    _STATUS_SVGS: dict[str, str] = {
        "idle": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="8" fill="currentColor"/>'
            '</svg>'
        ),
        "running": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="8" fill="currentColor"/>'
            '</svg>'
        ),
        "success": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="8" fill="currentColor"/>'
            '</svg>'
        ),
        "error": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="8" fill="currentColor"/>'
            '</svg>'
        ),
    }

    @classmethod
    def tool_icon(cls, tool_or_name: ToolType | str) -> QIcon:
        """按 ToolType 枚举或名称返回工具图标。

        支持两种调用方式（多态）：

        - 传入 :class:`ToolType` 枚举：返回工具标识图标
          （``BALCON`` 喇叭 / ``BLB2TXT`` 文档提取），用于工具切换器。
        - 传入字符串名称：返回工具栏动作图标（如 ``"add"``、``"start"``），
          用于工具栏按钮。

        由于 ``ToolType`` 继承 ``str``，本方法优先以 ``isinstance(...,
        ToolType)`` 判定枚举路径，再回退到字符串名称路径。

        Args:
            tool_or_name: :class:`ToolType` 枚举或工具图标名称字符串。

        Returns:
            对应的 QIcon；若参数未知或 SVG 不可用，返回空 QIcon。
        """
        # 优先匹配 ToolType 枚举（避免与 str 路径混淆）
        if isinstance(tool_or_name, ToolType):
            svg = cls._TOOL_TYPE_SVGS.get(tool_or_name)
            if svg is None:  # pragma: no cover - 枚举新增成员未补 SVG
                logger.warning("未知 ToolType %r", tool_or_name)
                return QIcon()
            return cls._svg_to_icon(svg, color=DesignTokens.color_neutral().name())
        # 字符串名称路径（原有行为，供工具栏动作图标使用）
        svg = cls._TOOL_SVGS.get(tool_or_name)
        if svg is None:
            logger.warning("未知工具图标名 %r", tool_or_name)
            return QIcon()
        return cls._svg_to_icon(svg, color=DesignTokens.color_neutral().name())

    @classmethod
    def tab_icon(cls, group: str) -> QIcon:
        """按分组名返回 Tab 分组图标。

        支持中文分组名（如 ``"输入输出"``）与英文 key（如
        ``"input_output"``），内部统一映射到英文 SVG 字典。

        Args:
            group: 分组名（中文或英文）。

        Returns:
            对应的 QIcon；若分组未知或 SVG 不可用，返回空 QIcon。
        """
        key = _GROUP_NAME_MAP.get(group, group)
        svg = cls._TAB_GROUP_SVGS.get(key)
        if svg is None:
            logger.warning("未知 Tab 分组 %r", group)
            return QIcon()
        return cls._svg_to_icon(svg, color=DesignTokens.color_neutral().name())

    @classmethod
    def status_icon(cls, state: str) -> QIcon:
        """按状态名返回状态图标（圆形）。

        颜色由 :meth:`DesignTokens.color_status` 运行时按当前主题提供
        （idle/running/success/error 四态）。

        Args:
            state: 状态名（``"idle"``、``"running"``、``"success"``、
                ``"error"``）。

        Returns:
            对应的 QIcon；若状态未知或 SVG 不可用，返回空 QIcon。
        """
        svg = cls._STATUS_SVGS.get(state)
        if svg is None:
            logger.warning("未知状态图标 %r", state)
            return QIcon()
        # 状态图标颜色由 DesignTokens 运行时按当前主题提供
        color = DesignTokens.color_status(state).name()
        return cls._svg_to_icon(svg, color=color)

    @classmethod
    def _svg_to_icon(cls, svg: str, color: str | None = None) -> QIcon:
        """将 SVG 字符串渲染为 QIcon。

        Args:
            svg: SVG 字符串。
            color: 可选颜色（如 ``"#555555"``）。若提供，将 SVG 中的
                ``currentColor`` 替换为该颜色。

        Returns:
            渲染后的 QIcon；若 QSvgRenderer 不可用或渲染失败，返回空 QIcon。
        """
        if not _SVG_AVAILABLE:
            return QIcon()

        if color:
            svg = svg.replace("currentColor", color)

        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if not renderer.isValid():
            logger.warning("SVG 渲染失败，返回空 QIcon")
            return QIcon()

        pixmap = QPixmap(QSize(_RENDER_SIZE, _RENDER_SIZE))
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter)
        finally:
            painter.end()

        return QIcon(pixmap)


__all__ = ["IconProvider"]
