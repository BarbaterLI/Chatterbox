"""file_list_widget 模块单元测试。

验证 ``FileListWidget`` 的工具切换（``set_tool``）行为，包括：
- 默认工具为 ``ToolType.BALCON``
- ``set_tool`` 切换 ``_current_tool``
- 空状态提示文案随工具切换（balcon 含"文件"，blb2txt 含"文档"）
- 文件对话框过滤器与拖拽扩展名白名单随工具切换
- 拖拽 ``dropEvent`` 按当前工具扩展名白名单过滤文件
- Task 11e：拖拽 QGraphicsDropShadowEffect 阴影动画反馈

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QMimeData,
    QPoint,
    QPropertyAnimation,
    Qt,
    QUrl,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QPalette

import pytest
from unittest.mock import MagicMock

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.theme.design_tokens import DesignTokens
from balcon_batch_tts.gui.widgets.animation_manager import AnimationManager
from balcon_batch_tts.gui.widgets.file_list_widget import (
    _BALCON_DRAG_EXTENSIONS,
    _BALCON_FILE_FILTER,
    _BLB2TXT_DRAG_EXTENSIONS,
    _BLB2TXT_FILE_FILTER,
    _DRAG_ANIM_DURATION_MS,
    _DRAG_SHADOW_BLUR_RADIUS_MAX,
    _DRAG_SHADOW_BLUR_RADIUS_MIN,
    FileListWidget,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_animation_manager():
    """每个测试前后重置 AnimationManager 单例状态。

    保证 ``set_enabled`` 的修改不会跨测试污染。
    """
    AnimationManager.reset_instance()
    yield
    AnimationManager.reset_instance()


# ---------------------------------------------------------------------------
# 默认工具与 set_tool 状态切换
# ---------------------------------------------------------------------------
class TestCurrentTool:
    """``_current_tool`` 状态契约。"""

    def test_default_tool_is_balcon(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        assert widget._current_tool is ToolType.BALCON

    def test_set_tool_to_blb2txt(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        assert widget._current_tool is ToolType.BLB2TXT

    def test_set_tool_back_to_balcon(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.set_tool(ToolType.BALCON)
        assert widget._current_tool is ToolType.BALCON

    def test_set_tool_same_value_is_noop(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        assert widget._current_tool is ToolType.BALCON


# ---------------------------------------------------------------------------
# 空状态提示文案
# ---------------------------------------------------------------------------
class TestEmptyStateText:
    """空状态提示文案随工具切换。"""

    def test_balcon_empty_state_contains_file_word(
        self, qapp: QApplication
    ) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        assert "文件" in widget.empty_label.text()

    def test_blb2txt_empty_state_contains_document_word(
        self, qapp: QApplication
    ) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        assert "文档" in widget.empty_label.text()

    def test_empty_state_text_changes_on_tool_switch(
        self, qapp: QApplication
    ) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        balcon_text = widget.empty_label.text()
        widget.set_tool(ToolType.BLB2TXT)
        blb2txt_text = widget.empty_label.text()
        assert balcon_text != blb2txt_text

    def test_blb2txt_text_does_not_contain_file_word(
        self, qapp: QApplication
    ) -> None:
        """blb2txt 模式空状态应使用"文档"而非"文件"。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        text = widget.empty_label.text()
        assert "文档" in text
        # T-D3: 文案主体应为"拖入文档或点击添加"，不含"文件"
        assert "拖入文档或点击添加" in text
        assert "文件" not in text


# ---------------------------------------------------------------------------
# T-D3: 空状态文案差异化（主提示 + 副提示）
# ---------------------------------------------------------------------------
class TestEmptyStateTD3:
    """T-D3: 空状态文案按工具类型差异化，含副提示行。"""

    def test_balcon_empty_state_contains_extensions(
        self, qapp: QApplication
    ) -> None:
        """balcon 工具下空状态文案含支持扩展名列表。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        text = widget.empty_label.text()
        for ext in (
            ".txt", ".srt", ".lrc", ".vtt",
            ".ssa", ".ass", ".smi", ".md", ".xml",
        ):
            assert ext in text, f"balcon 空状态文案缺失扩展名: {ext}"

    def test_blb2txt_empty_state_contains_document_types_and_pdf_hint(
        self, qapp: QApplication
    ) -> None:
        """blb2txt 工具下空状态文案含文档类型与 PDF 提示。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        text = widget.empty_label.text()
        assert "PDF" in text
        assert "主版本" in text
        for ext in (
            ".pdf", ".docx", ".doc", ".xlsx", ".xls",
            ".pptx", ".ppt", ".epub", ".html", ".txt",
        ):
            assert ext in text, f"blb2txt 空状态文案缺失扩展名: {ext}"

    def test_sub_label_exists_with_recursive_scan_text(
        self, qapp: QApplication
    ) -> None:
        """副提示「拖入文件夹将递归扫描」存在。"""
        widget = FileListWidget()
        assert widget.empty_sub_label is not None
        assert "拖入文件夹将递归扫描" in widget.empty_sub_label.text()

    def test_sub_label_color_is_neutral_gray(
        self, qapp: QApplication
    ) -> None:
        """副提示颜色为中性灰（DesignTokens.color_neutral()）。"""
        widget = FileListWidget()
        palette = widget.empty_sub_label.palette()
        color = palette.color(QPalette.ColorRole.WindowText)
        assert color == DesignTokens.color_neutral()

    def test_empty_state_text_updates_on_tool_switch(
        self, qapp: QApplication
    ) -> None:
        """切换工具后空状态文案更新为 T-D3 spec 格式。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        balcon_text = widget.empty_label.text()
        assert "拖入文件或点击添加" in balcon_text
        widget.set_tool(ToolType.BLB2TXT)
        blb2txt_text = widget.empty_label.text()
        assert "拖入文档或点击添加" in blb2txt_text
        assert balcon_text != blb2txt_text


# ---------------------------------------------------------------------------
# 文件对话框过滤器选择
# ---------------------------------------------------------------------------
class TestFileFilterSelection:
    """``_get_file_filter`` 根据工具返回对应过滤器。"""

    def test_balcon_filter(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        assert widget._get_file_filter() == _BALCON_FILE_FILTER

    def test_blb2txt_filter(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        assert widget._get_file_filter() == _BLB2TXT_FILE_FILTER


# ---------------------------------------------------------------------------
# 模块级常量内容
# ---------------------------------------------------------------------------
class TestFilterConstants:
    """模块级过滤器常量内容契约。"""

    def test_balcon_filter_has_txt_and_subtitles(self) -> None:
        assert "*.txt" in _BALCON_FILE_FILTER
        assert "*.srt" in _BALCON_FILE_FILTER
        assert "*.lrc" in _BALCON_FILE_FILTER

    def test_balcon_filter_has_all_files_fallback(self) -> None:
        assert "所有文件 (*.*)" in _BALCON_FILE_FILTER

    def test_blb2txt_filter_has_core_documents(self) -> None:
        for ext in ("*.pdf", "*.docx", "*.epub", "*.fb2", "*.html"):
            assert ext in _BLB2TXT_FILE_FILTER

    def test_blb2txt_filter_has_all_spec_extensions(self) -> None:
        """blb2txt 过滤器应包含 spec 列出的全部 30 个扩展名。"""
        required = [
            "*.azw", "*.azw3", "*.chm", "*.djvu", "*.doc", "*.docx",
            "*.epub", "*.fb2", "*.htm", "*.html", "*.lit", "*.md",
            "*.mht", "*.mobi", "*.odp", "*.ods", "*.odt", "*.pdb",
            "*.pdf", "*.ppt", "*.pptx", "*.prc", "*.rtf", "*.tcr",
            "*.txt", "*.txtz", "*.wpd", "*.wri", "*.xls", "*.xlsx",
        ]
        for ext in required:
            assert ext in _BLB2TXT_FILE_FILTER, f"缺失扩展名: {ext}"

    def test_blb2txt_filter_has_all_files_fallback(self) -> None:
        assert "所有文件 (*.*)" in _BLB2TXT_FILE_FILTER


# ---------------------------------------------------------------------------
# 拖拽扩展名白名单
# ---------------------------------------------------------------------------
class TestDragExtensions:
    """拖拽扩展名白名单常量契约。"""

    def test_balcon_allows_txt(self) -> None:
        assert ".txt" in _BALCON_DRAG_EXTENSIONS

    def test_balcon_allows_subtitle_extensions(self) -> None:
        for ext in (".srt", ".lrc", ".ssa", ".ass", ".smi", ".vtt"):
            assert ext in _BALCON_DRAG_EXTENSIONS

    def test_balcon_rejects_pdf(self) -> None:
        assert ".pdf" not in _BALCON_DRAG_EXTENSIONS

    def test_blb2txt_allows_pdf(self) -> None:
        assert ".pdf" in _BLB2TXT_DRAG_EXTENSIONS

    def test_blb2txt_allows_txt(self) -> None:
        assert ".txt" in _BLB2TXT_DRAG_EXTENSIONS

    def test_blb2txt_rejects_srt(self) -> None:
        """blb2txt 不支持字幕文件扩展名。"""
        assert ".srt" not in _BLB2TXT_DRAG_EXTENSIONS

    def test_get_allowed_extensions_balcon(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        assert widget._get_allowed_extensions() is _BALCON_DRAG_EXTENSIONS

    def test_get_allowed_extensions_blb2txt(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        assert widget._get_allowed_extensions() is _BLB2TXT_DRAG_EXTENSIONS


# ---------------------------------------------------------------------------
# dropEvent 扩展名过滤行为
# ---------------------------------------------------------------------------
class TestDropEventFiltering:
    """``dropEvent`` 按当前工具扩展名白名单过滤文件。

    使用 ``MagicMock`` 包装 ``QDropEvent``（保留真实 ``QMimeData``），
    规避 PySide6 中 ``QDropEvent`` 直接构造时 ``mimeData()`` 返回基类
    ``QObject`` 的绑定问题。``isAccepted()`` 由 ``acceptProposedAction``
    调用驱动，``ignore()`` 不改变状态（保持 ``False``）。
    """

    def _make_drop_event(self, file_paths: list[str]) -> MagicMock:
        """构造 mock QDropEvent，携带真实 QMimeData（含 uri-list）。"""
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in file_paths])
        event = MagicMock()
        event.mimeData.return_value = mime
        event._accepted = False

        def _accept() -> None:
            event._accepted = True

        def _is_accepted() -> bool:
            return event._accepted

        event.acceptProposedAction.side_effect = _accept
        event.ignore.side_effect = lambda: None
        event.isAccepted.side_effect = _is_accepted
        return event

    def test_balcon_accepts_txt_drop(
        self, qapp: QApplication, tmp_path
    ) -> None:
        txt = tmp_path / "sample.txt"
        txt.write_text("hello", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        event = self._make_drop_event([str(txt)])
        widget.dropEvent(event)
        assert event.isAccepted()
        assert len(widget.get_files()) == 1

    def test_balcon_rejects_pdf_drop(
        self, qapp: QApplication, tmp_path
    ) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_text("fake-pdf", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        event = self._make_drop_event([str(pdf)])
        widget.dropEvent(event)
        # balcon 模式拒绝 .pdf，事件未被接受且列表为空
        assert not event.isAccepted()
        assert widget.get_files() == []

    def test_blb2txt_accepts_pdf_drop(
        self, qapp: QApplication, tmp_path
    ) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_text("fake-pdf", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        event = self._make_drop_event([str(pdf)])
        widget.dropEvent(event)
        assert event.isAccepted()
        assert len(widget.get_files()) == 1

    def test_blb2txt_accepts_txt_drop(
        self, qapp: QApplication, tmp_path
    ) -> None:
        txt = tmp_path / "sample.txt"
        txt.write_text("hello", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        event = self._make_drop_event([str(txt)])
        widget.dropEvent(event)
        assert event.isAccepted()
        assert len(widget.get_files()) == 1

    def test_blb2txt_rejects_srt_drop(
        self, qapp: QApplication, tmp_path
    ) -> None:
        srt = tmp_path / "sub.srt"
        srt.write_text("1\n00:00:01 --> 00:00:02\nHi", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        event = self._make_drop_event([str(srt)])
        widget.dropEvent(event)
        assert not event.isAccepted()
        assert widget.get_files() == []

    def test_mixed_drop_filters_by_extension(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """blb2txt 模式拖入 .pdf + .srt，仅 .pdf 被接受。"""
        pdf = tmp_path / "book.pdf"
        pdf.write_text("fake-pdf", encoding="utf-8")
        srt = tmp_path / "sub.srt"
        srt.write_text("1\n00:00:01 --> 00:00:02\nHi", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        event = self._make_drop_event([str(pdf), str(srt)])
        widget.dropEvent(event)
        assert event.isAccepted()
        files = widget.get_files()
        assert len(files) == 1
        assert files[0].lower().endswith(".pdf")


# ---------------------------------------------------------------------------
# Task 11e：拖拽 QGraphicsDropShadowEffect 阴影动画反馈
# ---------------------------------------------------------------------------
class TestDragShadowEffect:
    """``QGraphicsDropShadowEffect`` 阴影动画契约。

    验证：
    - 阴影效果已应用到 ``stacked_widget``
    - 初始 ``blurRadius`` 为 0（不可见）
    - 阴影颜色与偏移参数符合 spec
    - ``_set_drag_highlight(True/False)`` 创建动画并改变 ``blurRadius``
    - 动画禁用时（``AnimationManager.set_enabled(False)``）duration=0
    - 拖拽事件正确触发阴影动画
    """

    def test_shadow_effect_applied_to_stacked_widget(
        self, qapp: QApplication
    ) -> None:
        """QGraphicsDropShadowEffect 应已应用到 stacked_widget。"""
        widget = FileListWidget()
        effect = widget.stacked_widget.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)

    def test_shadow_effect_initial_blur_radius_is_zero(
        self, qapp: QApplication
    ) -> None:
        """初始 blurRadius 应为 0（阴影不可见）。"""
        widget = FileListWidget()
        assert widget._shadow_effect.blurRadius() == _DRAG_SHADOW_BLUR_RADIUS_MIN

    def test_shadow_effect_color_matches_spec(
        self, qapp: QApplication
    ) -> None:
        """阴影颜色应与 ``DesignTokens.color_drag_shadow()`` 一致。"""
        widget = FileListWidget()
        assert widget._shadow_effect.color() == DesignTokens.color_drag_shadow()

    def test_shadow_effect_offset_is_set(
        self, qapp: QApplication
    ) -> None:
        """阴影偏移应大于 0（让阴影可见）。"""
        widget = FileListWidget()
        offset = widget._shadow_effect.offset()
        assert offset.x() > 0 or offset.y() > 0

    def test_set_drag_highlight_true_starts_animation(
        self, qapp: QApplication
    ) -> None:
        """``_set_drag_highlight(True)`` 应创建并启动动画。"""
        widget = FileListWidget()
        assert widget._shadow_anim is None

        widget._set_drag_highlight(True)
        assert widget._shadow_anim is not None
        assert isinstance(widget._shadow_anim, QPropertyAnimation)

    def test_set_drag_highlight_true_animation_targets_blur_radius(
        self, qapp: QApplication
    ) -> None:
        """动画目标属性应为 ``blurRadius``。"""
        widget = FileListWidget()
        widget._set_drag_highlight(True)
        # QPropertyAnimation.propertyName() 返回 QByteArray
        assert widget._shadow_anim.propertyName() == b"blurRadius"

    def test_set_drag_highlight_true_animation_end_value_is_max(
        self, qapp: QApplication
    ) -> None:
        """动画结束值应为 ``_DRAG_SHADOW_BLUR_RADIUS_MAX``。"""
        widget = FileListWidget()
        widget._set_drag_highlight(True)
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MAX

    def test_set_drag_highlight_true_animation_start_value_is_current(
        self, qapp: QApplication
    ) -> None:
        """动画起始值应为当前 ``blurRadius``。"""
        widget = FileListWidget()
        # 手动设置一个非零起始值
        widget._shadow_effect.setBlurRadius(5.0)
        widget._set_drag_highlight(True)
        assert widget._shadow_anim.startValue() == 5.0

    def test_set_drag_highlight_false_animation_end_value_is_min(
        self, qapp: QApplication
    ) -> None:
        """``_set_drag_highlight(False)`` 动画结束值应为 ``_DRAG_SHADOW_BLUR_RADIUS_MIN``。"""
        widget = FileListWidget()
        # 先进入高亮状态
        widget._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MAX)
        widget._set_drag_highlight(False)
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MIN

    def test_set_drag_highlight_stops_previous_animation(
        self, qapp: QApplication
    ) -> None:
        """连续调用 ``_set_drag_highlight`` 应停止前一个动画。"""
        widget = FileListWidget()
        widget._set_drag_highlight(True)
        first_anim = widget._shadow_anim
        assert first_anim is not None

        # 连续调用应停止前一个动画并创建新的
        widget._set_drag_highlight(True)
        second_anim = widget._shadow_anim
        assert second_anim is not None
        # 应是新的动画对象（前一个已停止）
        assert second_anim is not first_anim

    def test_set_drag_highlight_same_value_is_noop(
        self, qapp: QApplication
    ) -> None:
        """当起止值相同（已在目标值）时不应创建动画。"""
        widget = FileListWidget()
        # 当前 blurRadius 已为 MIN，再次调用 highlight(False) 应无动画
        assert widget._shadow_effect.blurRadius() == _DRAG_SHADOW_BLUR_RADIUS_MIN
        widget._set_drag_highlight(False)
        assert widget._shadow_anim is None

    def test_set_drag_highlight_animation_duration_matches_spec(
        self, qapp: QApplication
    ) -> None:
        """动画时长应与 ``_DRAG_ANIM_DURATION_MS`` 一致。"""
        widget = FileListWidget()
        widget._set_drag_highlight(True)
        assert widget._shadow_anim.duration() == _DRAG_ANIM_DURATION_MS

    def test_set_drag_highlight_animation_respects_disabled(
        self, qapp: QApplication
    ) -> None:
        """``AnimationManager.set_enabled(False)`` 时动画 duration 应为 0。"""
        AnimationManager.instance().set_enabled(False)
        widget = FileListWidget()
        widget._set_drag_highlight(True)
        assert widget._shadow_anim is not None
        assert widget._shadow_anim.duration() == 0

    def test_set_drag_highlight_disabled_skips_when_already_at_target(
        self, qapp: QApplication
    ) -> None:
        """禁用动画且已在目标值时不应创建动画对象。"""
        AnimationManager.instance().set_enabled(False)
        widget = FileListWidget()
        # blurRadius 已为 MIN，调用 highlight(False) 仍应无动画
        widget._set_drag_highlight(False)
        assert widget._shadow_anim is None

    def test_drag_enter_event_triggers_highlight_on(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``dragEnterEvent`` 接受 uri-list 时应启动高亮动画。"""
        widget = FileListWidget()

        # 构造真实的 QDragEnterEvent
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "test.txt"))])
        event = QDragEnterEvent(
            QPoint(0, 0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        widget.dragEnterEvent(event)
        assert event.isAccepted()
        assert widget._shadow_anim is not None
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MAX

    def test_drag_enter_event_ignores_non_uri_list(
        self, qapp: QApplication
    ) -> None:
        """``dragEnterEvent`` 不接受非 uri-list 时不应启动高亮。"""
        widget = FileListWidget()

        mime = QMimeData()
        mime.setText("plain text")
        event = QDragEnterEvent(
            QPoint(0, 0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        widget.dragEnterEvent(event)
        assert not event.isAccepted()
        assert widget._shadow_anim is None

    def test_drag_leave_event_triggers_highlight_off(
        self, qapp: QApplication
    ) -> None:
        """``dragLeaveEvent`` 应启动收回阴影动画。"""
        widget = FileListWidget()
        # 先模拟进入高亮状态
        widget._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MAX)

        event = QDragLeaveEvent()
        widget.dragLeaveEvent(event)
        assert widget._shadow_anim is not None
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MIN

    def test_drop_event_triggers_highlight_off(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``dropEvent`` 应在结束时启动收回阴影动画。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        # 先模拟进入高亮状态
        widget._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MAX)

        txt = tmp_path / "sample.txt"
        txt.write_text("hello", encoding="utf-8")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(txt))])
        event = MagicMock()
        event.mimeData.return_value = mime
        event._accepted = False

        def _accept() -> None:
            event._accepted = True

        event.acceptProposedAction.side_effect = _accept
        event.ignore.side_effect = lambda: None
        event.isAccepted.side_effect = lambda: event._accepted

        widget.dropEvent(event)
        # dropEvent 后应启动收回动画
        assert widget._shadow_anim is not None
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MIN

    def test_drop_event_non_uri_list_triggers_highlight_off(
        self, qapp: QApplication
    ) -> None:
        """``dropEvent`` 非 uri-list 时也应启动收回阴影动画。"""
        widget = FileListWidget()
        widget._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MAX)

        mime = QMimeData()
        mime.setText("plain text")
        event = MagicMock()
        event.mimeData.return_value = mime
        event._accepted = False
        event.acceptProposedAction.side_effect = lambda: None
        event.ignore.side_effect = lambda: None
        event.isAccepted.side_effect = lambda: event._accepted

        widget.dropEvent(event)
        assert widget._shadow_anim is not None
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MIN


# ---------------------------------------------------------------------------
# Task：添加文件夹功能（按钮 + _collect_files_from_folder + dropEvent 文件夹）
# ---------------------------------------------------------------------------
class TestAddFolderButton:
    """「添加文件夹」按钮存在性与信号连接。"""

    def test_add_folder_btn_exists(self, qapp: QApplication) -> None:
        widget = FileListWidget()
        assert widget.add_folder_btn is not None
        assert widget.add_folder_btn.text() == "添加文件夹"

    def test_add_folder_btn_connected_to_dialog(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """点击按钮应触发 ``add_folder_dialog``（通过 monkeypatch 验证）。"""
        widget = FileListWidget()
        called = {"count": 0, "arg": None}

        def _fake_dialog(self_ignored=None) -> None:
            called["count"] += 1

        # 替换实例方法（绑定到 widget）
        widget.add_folder_dialog = _fake_dialog.__get__(widget, type(widget))  # type: ignore[method-assign]
        widget.add_folder_btn.click()
        assert called["count"] == 1


# ---------------------------------------------------------------------------
# _collect_files_from_folder 工具方法
# ---------------------------------------------------------------------------
class TestCollectFilesFromFolder:
    """``_collect_files_from_folder`` 递归扫描行为契约。"""

    def test_collect_returns_empty_for_empty_folder(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """空文件夹应返回空列表。"""
        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), frozenset({".txt"})
        )
        assert result == []

    def test_collect_returns_matching_files_in_root(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """根目录中的匹配文件应被收集。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "c.pdf").write_text("c", encoding="utf-8")

        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), frozenset({".txt"})
        )
        # 应只包含两个 .txt 文件
        assert len(result) == 2
        result_lower = [p.lower() for p in result]
        assert any(p.endswith("a.txt") for p in result_lower)
        assert any(p.endswith("b.txt") for p in result_lower)

    def test_collect_recurses_into_subfolders(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """应递归扫描子文件夹。"""
        (tmp_path / "root.txt").write_text("r", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "sub.txt").write_text("s", encoding="utf-8")
        deep = sub / "deep"
        deep.mkdir()
        (deep / "deep.txt").write_text("d", encoding="utf-8")

        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), frozenset({".txt"})
        )
        assert len(result) == 3
        result_lower = [p.lower() for p in result]
        assert any(p.endswith("root.txt") for p in result_lower)
        assert any(p.endswith("sub.txt") for p in result_lower)
        assert any(p.endswith("deep.txt") for p in result_lower)

    def test_collect_filters_by_extension(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """非匹配扩展名应被过滤掉。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.pdf").write_text("b", encoding="utf-8")
        (tmp_path / "c.docx").write_text("c", encoding="utf-8")

        # balcon 扩展名白名单（不含 .pdf / .docx）
        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), _BALCON_DRAG_EXTENSIONS
        )
        assert len(result) == 1
        assert result[0].lower().endswith("a.txt")

    def test_collect_with_blb2txt_extensions(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """使用 blb2txt 扩展名白名单应正确收集文档类型。"""
        (tmp_path / "book.pdf").write_text("p", encoding="utf-8")
        (tmp_path / "doc.docx").write_text("d", encoding="utf-8")
        (tmp_path / "subtitle.srt").write_text("s", encoding="utf-8")

        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), _BLB2TXT_DRAG_EXTENSIONS
        )
        result_lower = [p.lower() for p in result]
        assert any(p.endswith("book.pdf") for p in result_lower)
        assert any(p.endswith("doc.docx") for p in result_lower)
        # .srt 不在 blb2txt 白名单中
        assert not any(p.endswith("subtitle.srt") for p in result_lower)

    def test_collect_returns_absolute_paths(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """返回路径应为绝对路径。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), frozenset({".txt"})
        )
        assert len(result) == 1
        assert os.path.isabs(result[0])

    def test_collect_case_insensitive_extension(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """扩展名匹配应大小写不敏感（.TXT 与 .txt 都匹配）。"""
        (tmp_path / "upper.TXT").write_text("u", encoding="utf-8")
        (tmp_path / "lower.txt").write_text("l", encoding="utf-8")

        result = FileListWidget._collect_files_from_folder(
            str(tmp_path), frozenset({".txt"})
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# add_folder_dialog 行为（通过 monkeypatch QFileDialog 验证）
# ---------------------------------------------------------------------------
class TestAddFolderDialog:
    """``add_folder_dialog`` 行为契约。"""

    def test_add_folder_dialog_adds_scanned_files(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """选择文件夹后应递归扫描并添加匹配文件到列表。"""
        # 准备测试文件夹
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "c.pdf").write_text("c", encoding="utf-8")  # balcon 模式被过滤

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        # monkeypatch QFileDialog.getExistingDirectory 返回 tmp_path
        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: str(tmp_path),
        )

        widget.add_folder_dialog()
        files = widget.get_files()
        assert len(files) == 2
        files_lower = [p.lower() for p in files]
        assert any(p.endswith("a.txt") for p in files_lower)
        assert any(p.endswith("b.txt") for p in files_lower)

    def test_add_folder_dialog_empty_folder_no_change(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """选择空文件夹时列表应保持不变。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        assert widget.get_files() == []

        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: str(tmp_path),
        )

        widget.add_folder_dialog()
        assert widget.get_files() == []

    def test_add_folder_dialog_cancel_no_change(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """用户取消对话框（返回空字符串）时列表应保持不变。"""
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: "",
        )

        widget.add_folder_dialog()
        assert widget.get_files() == []

    def test_add_folder_dialog_blb2txt_mode(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """blb2txt 模式应使用文档扩展名白名单。"""
        (tmp_path / "book.pdf").write_text("p", encoding="utf-8")
        (tmp_path / "sub.srt").write_text("s", encoding="utf-8")  # 不被 blb2txt 接受

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)

        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: str(tmp_path),
        )

        widget.add_folder_dialog()
        files = widget.get_files()
        assert len(files) == 1
        assert files[0].lower().endswith("book.pdf")

    def test_add_folder_dialog_emits_files_changed(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """添加文件夹中的文件应发射 ``files_changed`` 信号。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: str(tmp_path),
        )

        received: list[list[str]] = []
        widget.files_changed.connect(lambda files: received.append(files))

        widget.add_folder_dialog()
        assert len(received) == 1
        assert len(received[0]) == 1
        assert received[0][0].lower().endswith("a.txt")

    def test_add_folder_dialog_deduplicates_existing(
        self, qapp: QApplication, tmp_path, monkeypatch
    ) -> None:
        """已存在的文件不应重复添加。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        # 先手动添加 a.txt
        widget.add_files([str(tmp_path / "a.txt")])
        assert len(widget.get_files()) == 1

        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            lambda *args, **kwargs: str(tmp_path),
        )

        # 再次通过文件夹扫描添加
        widget.add_folder_dialog()
        assert len(widget.get_files()) == 1  # 去重


# ---------------------------------------------------------------------------
# dropEvent 拖拽文件夹行为
# ---------------------------------------------------------------------------
class TestDropFolderEvent:
    """``dropEvent`` 拖拽文件夹行为契约。

    复用 ``TestDropEventFiltering._make_drop_event`` 构造工具，
    但需将其提取为模块级辅助函数以便复用。
    """

    def _make_drop_event(self, paths: list[str]) -> MagicMock:
        """构造 mock QDropEvent，携带真实 QMimeData（含 uri-list）。"""
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        event = MagicMock()
        event.mimeData.return_value = mime
        event._accepted = False

        def _accept() -> None:
            event._accepted = True

        def _is_accepted() -> bool:
            return event._accepted

        event.acceptProposedAction.side_effect = _accept
        event.ignore.side_effect = lambda: None
        event.isAccepted.side_effect = _is_accepted
        return event

    def test_drop_folder_scans_and_adds_files(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽文件夹应递归扫描并添加匹配文件。"""
        # 准备文件夹结构
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b", encoding="utf-8")
        (sub / "c.pdf").write_text("c", encoding="utf-8")  # balcon 模式被过滤

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        event = self._make_drop_event([str(tmp_path)])
        widget.dropEvent(event)

        assert event.isAccepted()
        files = widget.get_files()
        assert len(files) == 2
        files_lower = [p.lower() for p in files]
        assert any(p.endswith("a.txt") for p in files_lower)
        assert any(p.endswith("b.txt") for p in files_lower)

    def test_drop_empty_folder_ignored(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽空文件夹应忽略事件（无匹配文件）。"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        event = self._make_drop_event([str(empty_dir)])
        widget.dropEvent(event)

        assert not event.isAccepted()
        assert widget.get_files() == []

    def test_drop_folder_with_only_unsupported_files_ignored(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽仅含不支持扩展名文件的文件夹应忽略事件。"""
        (tmp_path / "a.pdf").write_text("a", encoding="utf-8")
        (tmp_path / "b.docx").write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)  # balcon 不支持 .pdf/.docx

        event = self._make_drop_event([str(tmp_path)])
        widget.dropEvent(event)

        assert not event.isAccepted()
        assert widget.get_files() == []

    def test_drop_folder_blb2txt_mode(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """blb2txt 模式拖拽文件夹应使用文档扩展名白名单。"""
        (tmp_path / "book.pdf").write_text("p", encoding="utf-8")
        (tmp_path / "doc.docx").write_text("d", encoding="utf-8")
        (tmp_path / "subtitle.srt").write_text("s", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)

        event = self._make_drop_event([str(tmp_path)])
        widget.dropEvent(event)

        assert event.isAccepted()
        files = widget.get_files()
        assert len(files) == 2
        files_lower = [p.lower() for p in files]
        assert any(p.endswith("book.pdf") for p in files_lower)
        assert any(p.endswith("doc.docx") for p in files_lower)

    def test_drop_mixed_files_and_folders(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽混合（文件 + 文件夹）应分别处理。"""
        # 单独的文件
        standalone_txt = tmp_path / "standalone.txt"
        standalone_txt.write_text("s", encoding="utf-8")
        # 文件夹
        folder = tmp_path / "folder"
        folder.mkdir()
        (folder / "inside.txt").write_text("i", encoding="utf-8")
        # 不支持扩展名的文件
        unsupported_pdf = tmp_path / "unsupported.pdf"
        unsupported_pdf.write_text("u", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        event = self._make_drop_event(
            [str(standalone_txt), str(folder), str(unsupported_pdf)]
        )
        widget.dropEvent(event)

        assert event.isAccepted()
        files = widget.get_files()
        files_lower = [p.lower() for p in files]
        # 应包含 standalone.txt 和 inside.txt（来自文件夹扫描）
        assert any(p.endswith("standalone.txt") for p in files_lower)
        assert any(p.endswith("inside.txt") for p in files_lower)
        # 不应包含 unsupported.pdf
        assert not any(p.endswith("unsupported.pdf") for p in files_lower)

    def test_drop_multiple_folders(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽多个文件夹应全部扫描并合并添加。"""
        folder1 = tmp_path / "f1"
        folder1.mkdir()
        (folder1 / "a.txt").write_text("a", encoding="utf-8")
        folder2 = tmp_path / "f2"
        folder2.mkdir()
        (folder2 / "b.txt").write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        event = self._make_drop_event([str(folder1), str(folder2)])
        widget.dropEvent(event)

        assert event.isAccepted()
        files = widget.get_files()
        assert len(files) == 2
        files_lower = [p.lower() for p in files]
        assert any(p.endswith("a.txt") for p in files_lower)
        assert any(p.endswith("b.txt") for p in files_lower)

    def test_drop_folder_triggers_drag_highlight_off(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽文件夹放下后应收回阴影动画。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)
        widget._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MAX)

        event = self._make_drop_event([str(tmp_path)])
        widget.dropEvent(event)

        assert widget._shadow_anim is not None
        assert widget._shadow_anim.endValue() == _DRAG_SHADOW_BLUR_RADIUS_MIN

    def test_drop_folder_emits_files_changed(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽文件夹添加文件应发射 ``files_changed`` 信号。"""
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BALCON)

        received: list[list[str]] = []
        widget.files_changed.connect(lambda files: received.append(files))

        event = self._make_drop_event([str(tmp_path)])
        widget.dropEvent(event)

        assert len(received) == 1
        assert len(received[0]) == 1
        assert received[0][0].lower().endswith("a.txt")
