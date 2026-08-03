"""日志面板控件：订阅 ``LogSignals`` 显示日志，支持清空与保存。

提供 ``LogPanel``，封装 QPlainTextEdit + 操作按钮：
- 通过 ``LogSignals.get_instance().log_message`` 信号实时接收日志
- 限制最大行数（``maximumBlockCount=5000``）避免内存爆炸
- 支持清空日志、保存当前日志到文件
- 提供 ``append`` 公开方法供外部主动追加文本
- 日志级别着色、级别过滤下拉、自动滚动开关、搜索框过滤

Task 11f 优化（Qt6 原生动画）：
- 新日志到达时通过「最近日志横幅」展开动画反馈，避免整页跳动
- 横幅使用 :class:`QPropertyAnimation` 动画 ``maximumHeight`` 属性
  从 0 展开到 ``_BANNER_HEIGHT``（OutCubic 缓动），保持短暂时间后
  再动画收回至 0
- 三段动画通过 :class:`QSequentialAnimationGroup` 编排：
  展开 → 保持 → 收回
- 动画通过 :class:`AnimationManager` 统一管理，支持「禁用动画」降级
- 高频日志流场景下：动画进行中仅更新横幅文本，不重启动画
"""

from __future__ import annotations

import html
import logging

from PySide6.QtCore import (
    QEasingCurve,
    QPauseAnimation,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QColor, QMouseEvent, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chatterbox.gui.theme.design_tokens import DesignTokens
from chatterbox.gui.widgets.animation_manager import AnimationManager
from chatterbox.utils.signals import LogSignals

logger = logging.getLogger(__name__)

# 最大保留行数，超过后自动从顶部丢弃
_MAX_BLOCK_COUNT = 5000

# 日志级别对应的 CSS 颜色名由 DesignTokens.log_level_colors() 运行时提供

# 级别过滤下拉选项
_FILTER_ALL = "全部"
_FILTER_ERRORS = "仅错误"
_FILTER_WARN_PLUS = "仅警告以上"

# Task 11f：最近日志横幅动画参数
_BANNER_HEIGHT = 28          # 横幅展开后的最大高度（像素）
_BANNER_EXPAND_MS = 150      # 展开动画时长（OutCubic 缓动）
_BANNER_COLLAPSE_MS = 150    # 收回动画时长（InCubic 缓动）
_BANNER_HOLD_MS = 800        # 展开后保持时长（毫秒）
_BANNER_MAX_CHARS = 120      # 横幅文本最大字符数（超出截断加省略号）

# T-C4：级别统计徽章颜色由 DesignTokens 运行时提供
# （color_info / color_warning / color_failure）


class _ClickableLabel(QLabel):
    """可点击的 QLabel，左键点击发出 ``clicked`` 信号。

    用于级别统计徽章，点击切换级别过滤下拉。不引入 QSS，遵循 Qt6 原生风格。
    """

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class LogPanel(QWidget):
    """日志面板控件。

    继承 QWidget，封装只读 QPlainTextEdit 与"清空日志"/"保存日志"按钮，
    自动连接 ``LogSignals.get_instance().log_message`` 信号实时显示日志。
    支持日志级别着色、级别过滤、自动滚动开关、搜索框过滤。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 原始日志列表（与 text_edit 的 maximumBlockCount 对齐）
        self._raw_logs: list[str] = []
        # 标志：在程序性 clear/批量 append 期间抑制滚动监听，避免误取消自动滚动
        self._suppress_scroll_handler: bool = False

        # T-C4：级别统计计数（键：INFO/WARNING/ERROR/CRITICAL/DEBUG）
        # ERROR 徽章显示 ERROR + CRITICAL 之和
        self._level_counts: dict[str, int] = {
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
            "DEBUG": 0,
        }

        # Task 6：日志批量刷新缓冲区与定时器
        # 高并发下避免每条日志单独调用 appendHtml 触发 Qt 文本布局重计算
        self._pending_logs: list[str] = []
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.setInterval(50)
        self._batch_timer.timeout.connect(self._flush_pending_logs)

        # 文本框
        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(_MAX_BLOCK_COUNT)
        # 等宽字体更适合日志
        font = self.text_edit.font()
        font.setFamily("Consolas")
        self.text_edit.setFont(font)

        # Task 11f：最近日志横幅（maximumHeight 从 0 展开动画）
        # 使用 QFrame + QLabel，原生 StyledPanel 外观，不引入 QSS
        self._recent_banner = QLabel(self)
        self._recent_banner.setFrameShape(QFrame.Shape.StyledPanel)
        self._recent_banner.setWordWrap(False)
        self._recent_banner.setMaximumHeight(0)
        self._recent_banner.setIndent(8)
        # 等宽字体与 text_edit 一致，便于识别日志文本
        banner_font = self._recent_banner.font()
        banner_font.setFamily("Consolas")
        self._recent_banner.setFont(banner_font)
        # 横幅动画组引用（持有以防止 GC）
        self._banner_anim_group: QSequentialAnimationGroup | None = None

        # 控制栏：级别过滤 + 自动滚动 + 搜索框 + 操作按钮
        self.level_filter = QComboBox(self)
        self.level_filter.addItem(_FILTER_ALL)
        self.level_filter.addItem(_FILTER_ERRORS)
        self.level_filter.addItem(_FILTER_WARN_PLUS)
        self.level_filter.setToolTip(
            "过滤显示的日志级别：\n"
            "- 全部：显示所有级别\n"
            "- 仅错误：ERROR + CRITICAL\n"
            "- 仅警告以上：WARNING + ERROR + CRITICAL"
        )

        self.auto_scroll_check = QCheckBox("自动滚动", self)
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.setToolTip(
            "勾选后新日志自动滚动到底部。\n"
            "用户手动向上滚动会自动取消勾选，便于查看历史。"
        )

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("搜索日志（不区分大小写）…")
        self.search_box.setToolTip("按关键字过滤日志，不区分大小写")

        # T-C4：级别统计徽章（INFO/WARNING/ERROR）
        # 颜色通过 QPalette 设置 WindowText 角色，不使用 QSS
        # 颜色值由 DesignTokens 运行时按当前主题提供
        # 点击徽章切换级别过滤下拉为对应级别
        self.info_badge = self._make_badge("INFO", DesignTokens.color_info())
        self.warn_badge = self._make_badge("WARNING", DesignTokens.color_warning())
        self.error_badge = self._make_badge("ERROR", DesignTokens.color_failure())
        self.info_badge.clicked.connect(lambda: self._on_badge_clicked("INFO"))
        self.warn_badge.clicked.connect(lambda: self._on_badge_clicked("WARNING"))
        self.error_badge.clicked.connect(lambda: self._on_badge_clicked("ERROR"))

        self.clear_btn = QPushButton("清空日志", self)
        self.clear_btn.setToolTip("清空所有日志")
        self.save_btn = QPushButton("保存日志", self)
        self.save_btn.setToolTip("保存日志到文件")

        # T-C4：保存日志菜单按钮（QPushButton + QMenu）
        # 提供两个选项：保存当前过滤结果 / 保存全部
        save_menu = QMenu(self.save_btn)
        self._action_save_filtered = save_menu.addAction("保存当前过滤结果")
        self._action_save_all = save_menu.addAction("保存全部")
        self.save_btn.setMenu(save_menu)
        self._action_save_filtered.triggered.connect(self._save_filtered)
        self._action_save_all.triggered.connect(self._save_all)

        # 控制栏布局
        # 在 search_box 与 clear_btn 间加 VLine 分隔「过滤」组与「操作」组
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        control_row = QHBoxLayout()
        control_row.addWidget(self.level_filter)
        control_row.addWidget(self.auto_scroll_check)
        control_row.addWidget(self.search_box)
        control_row.addWidget(sep)
        control_row.addWidget(self.info_badge)
        control_row.addWidget(self.warn_badge)
        control_row.addWidget(self.error_badge)
        control_row.addStretch()
        control_row.addWidget(self.clear_btn)
        control_row.addWidget(self.save_btn)

        # 主布局：控制栏 → 最近日志横幅 → 文本框
        layout = QVBoxLayout(self)
        layout.addLayout(control_row)
        layout.addWidget(self._recent_banner)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        # 信号连接
        self.clear_btn.clicked.connect(self.clear_log)
        self.level_filter.currentIndexChanged.connect(self._rerender)
        self.search_box.textChanged.connect(self._rerender)
        self.auto_scroll_check.toggled.connect(self._on_auto_scroll_toggled)
        self.text_edit.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        # 订阅全局日志信号
        LogSignals.get_instance().log_message.connect(self._append_log)

        logger.debug("LogPanel 已初始化")

    # ----------------------------------------------------------------------
    # T-C4：级别统计徽章
    # ----------------------------------------------------------------------
    @staticmethod
    def _make_badge(label: str, color: QColor) -> _ClickableLabel:
        """创建级别统计徽章 QLabel。

        颜色通过 :class:`QPalette` 设置 ``WindowText`` 角色（前景），
        不使用 QSS。徽章使用原生 ``StyledPanel`` 外观，点击发出
        ``clicked`` 信号用于切换级别过滤。

        Args:
            label: 级别名（INFO/WARNING/ERROR）。
            color: 徽章前景色。

        Returns:
            可点击的 QLabel 徽章，初始文本为 ``f"{label} 0"``。
        """
        badge = _ClickableLabel()
        badge.setText(f"{label} 0")
        # 通过 QPalette 设置 WindowText 角色颜色（前景），不使用 QSS
        palette = badge.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        badge.setPalette(palette)
        badge.setFrameShape(QFrame.Shape.StyledPanel)
        badge.setMargin(2)
        badge.setCursor(Qt.CursorShape.PointingHandCursor)
        badge.setToolTip(f"点击切换级别过滤为{label}相关")
        return badge

    def _on_badge_clicked(self, level: str) -> None:
        """徽章点击槽：切换级别过滤下拉为对应级别。

        - INFO → ``_FILTER_ALL``（全部）
        - WARNING → ``_FILTER_WARN_PLUS``（仅警告以上）
        - ERROR → ``_FILTER_ERRORS``（仅错误，含 ERROR + CRITICAL）
        """
        if level == "INFO":
            self.level_filter.setCurrentText(_FILTER_ALL)
        elif level == "WARNING":
            self.level_filter.setCurrentText(_FILTER_WARN_PLUS)
        elif level == "ERROR":
            self.level_filter.setCurrentText(_FILTER_ERRORS)

    def _update_badges(self) -> None:
        """根据 ``_level_counts`` 更新徽章文本。

        ERROR 徽章包含 ERROR + CRITICAL 计数之和。
        """
        info_count = self._level_counts["INFO"]
        warn_count = self._level_counts["WARNING"]
        error_count = self._level_counts["ERROR"] + self._level_counts["CRITICAL"]
        self.info_badge.setText(f"INFO {info_count}")
        self.warn_badge.setText(f"WARNING {warn_count}")
        self.error_badge.setText(f"ERROR {error_count}")

    # ----------------------------------------------------------------------
    # Task 11f：最近日志横幅动画
    # ----------------------------------------------------------------------
    def _show_recent_banner(self, text: str) -> None:
        """显示最近日志横幅并触发展开动画。

        横幅通过 :class:`QPropertyAnimation` 动画 ``maximumHeight`` 属性
        从 0 展开到 ``_BANNER_HEIGHT``，保持 ``_BANNER_HOLD_MS`` 毫秒后
        再动画收回至 0。三段动画通过 :class:`QSequentialAnimationGroup`
        编排：展开 → 保持 → 收回。

        高频日志流场景下：动画进行中仅更新横幅文本，不重启动画，
        避免频繁打断视觉反馈。

        动画通过 :class:`AnimationManager` 创建，支持「禁用动画」降级
        （禁用时跳过横幅显示，纯文本日志仍正常追加到 text_edit）。

        Args:
            text: 要显示的日志文本（将被截断到 ``_BANNER_MAX_CHARS``）。
        """
        # 禁用动画时跳过横幅显示（横幅本身是纯视觉反馈）
        anim_mgr = AnimationManager.instance()
        if not anim_mgr.is_enabled():
            return

        # 截断过长文本
        if len(text) > _BANNER_MAX_CHARS:
            display_text = text[:_BANNER_MAX_CHARS] + "…"
        else:
            display_text = text
        self._recent_banner.setText(display_text)

        # 动画进行中：仅更新文本，不重启动画（高频日志流优化）
        if (
            self._banner_anim_group is not None
            and self._banner_anim_group.state() == QSequentialAnimationGroup.State.Running
        ):
            return

        # 停止既有动画组（清理）
        if self._banner_anim_group is not None:
            try:
                self._banner_anim_group.stop()
            except RuntimeError:
                pass
            self._banner_anim_group = None

        # 确保横幅从 maximumHeight=0 开始
        self._recent_banner.setMaximumHeight(0)

        # 创建三段动画组：展开 → 保持 → 收回
        group = QSequentialAnimationGroup(self)

        # 展开：maximumHeight 0 → _BANNER_HEIGHT（OutCubic 缓动）
        expand_anim = anim_mgr.make_property_animation(
            target=self._recent_banner,
            prop=b"maximumHeight",
            start=0,
            end=_BANNER_HEIGHT,
            duration=_BANNER_EXPAND_MS,
            easing=QEasingCurve.Type.OutCubic,
        )
        group.addAnimation(expand_anim)

        # 保持：暂停 _BANNER_HOLD_MS 毫秒
        group.addAnimation(QPauseAnimation(_BANNER_HOLD_MS))

        # 收回：maximumHeight _BANNER_HEIGHT → 0（InCubic 缓动）
        collapse_anim = anim_mgr.make_property_animation(
            target=self._recent_banner,
            prop=b"maximumHeight",
            start=_BANNER_HEIGHT,
            end=0,
            duration=_BANNER_COLLAPSE_MS,
            easing=QEasingCurve.Type.InCubic,
        )
        group.addAnimation(collapse_anim)

        self._banner_anim_group = group
        group.start()

    # ----------------------------------------------------------------------
    # 过滤与渲染
    # ----------------------------------------------------------------------
    @staticmethod
    def _detect_level(text: str) -> str:
        """从日志文本中解析级别关键词，返回大写级别名（如 ``'ERROR'``）。

        日志格式为 ``[%(asctime)s] [%(levelname)s] %(name)s: %(message)s``，
        匹配 ``[LEVEL]`` 形式。
        """
        upper = text.upper()
        for level in ("CRITICAL", "ERROR", "WARNING", "DEBUG", "INFO"):
            if f"[{level}]" in upper:
                return level
        return ""

    @classmethod
    def _level_color(cls, level: str) -> str:
        """返回级别对应的 CSS 颜色名，无颜色返回空字符串。

        颜色映射由 :meth:`DesignTokens.log_level_colors` 运行时按当前主题提供。
        """
        return DesignTokens.log_level_colors().get(level, "")

    def _format_line_html(self, text: str) -> str:
        """将日志文本 HTML 转义并按级别包裹颜色 span，返回 HTML 片段。"""
        escaped = html.escape(text).replace("\n", "<br>")
        level = self._detect_level(text)
        color = self._level_color(level)
        if color:
            return f'<span style="color:{color};">{escaped}</span>'
        return escaped

    def _passes_filter(self, text: str) -> bool:
        """判断日志行是否通过当前级别过滤与搜索关键词过滤。"""
        level = self._detect_level(text)
        filter_text = self.level_filter.currentText()
        if filter_text == _FILTER_ERRORS:
            if level not in ("ERROR", "CRITICAL"):
                return False
        elif filter_text == _FILTER_WARN_PLUS:
            if level not in ("ERROR", "CRITICAL", "WARNING"):
                return False
        # _FILTER_ALL: 不按级别过滤
        search = self.search_box.text().strip().lower()
        if search and search not in text.lower():
            return False
        return True

    def _rerender(self) -> None:
        """根据当前过滤条件从原始日志重新渲染 text_edit。"""
        # Task 6：清空待刷新缓冲区并停止定时器
        # rerender 会从 _raw_logs 重建（其中已包含 _pending_logs 中的日志），
        # 若不清空会导致 flush 时重复追加
        self._pending_logs.clear()
        self._batch_timer.stop()
        self._suppress_scroll_handler = True
        try:
            self.text_edit.clear()
            for line in self._raw_logs:
                if self._passes_filter(line):
                    self.text_edit.appendHtml(self._format_line_html(line))
        finally:
            self._suppress_scroll_handler = False
        if self.auto_scroll_check.isChecked():
            sb = self.text_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    # ----------------------------------------------------------------------
    # 槽函数
    # ----------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        """私有槽：追加文本到原始列表，按过滤条件加入批量缓冲区。

        使用 try/except 防护，避免异常 hook 触发的日志再次抛出异常
        导致无限递归（sys.excepthook -> logger -> handler -> _append_log）。

        Task 6：日志不再直接调用 ``appendHtml``，而是加入 ``_pending_logs``
        缓冲区，由 ``_batch_timer``（50ms 单次定时器）触发
        ``_flush_pending_logs`` 合并为单次 ``appendHtml`` 调用，
        避免高并发下频繁触发 Qt 文本布局重计算导致 UI 卡顿。

        Task 11f：日志通过过滤后，在 flush 时触发最近日志横幅展开动画
        （``_show_recent_banner``），通过 QPropertyAnimation 动画
        ``maximumHeight`` 从 0 展开提供视觉反馈，避免整页跳动。

        T-C4：按 ``_detect_level`` 累加 ``_level_counts`` 并实时更新徽章。
        """
        try:
            self._raw_logs.append(text)
            # 控制原始列表大小，与 text_edit 的 maximumBlockCount 对齐
            if len(self._raw_logs) > _MAX_BLOCK_COUNT:
                cut = int(_MAX_BLOCK_COUNT * 0.8)
                self._raw_logs = self._raw_logs[-cut:]

            # T-C4：累加级别计数并更新徽章
            level = self._detect_level(text)
            if level in self._level_counts:
                self._level_counts[level] += 1
                self._update_badges()

            if not self._passes_filter(text):
                return

            # Task 6：加入批量缓冲区，等待定时器合并 flush
            self._pending_logs.append(text)
            if not self._batch_timer.isActive():
                self._batch_timer.start()
        except Exception:
            # 静默吞掉，避免与 sys.excepthook 形成递归
            pass

    def _flush_pending_logs(self) -> None:
        """Task 6：将待刷新日志缓冲区合并为单次 ``appendHtml`` 调用。

        高并发场景下（如 16 个 worker 各发 10 条日志），避免每条日志
        单独触发 Qt 文本布局重计算。50ms 内到达的日志合并为一个 HTML
        字符串，仅调用一次 ``appendHtml``。

        - 缓冲区为空时停止定时器并返回（空操作）
        - 通过过滤的日志用 ``<br>`` 连接为单个 HTML 片段
        - 根据自动滚动状态决定 append 后的滚动行为
        - flush 后触发最近日志横幅（使用最后一条日志文本）
        """
        if not self._pending_logs:
            self._batch_timer.stop()
            return

        # 合并所有待刷新日志为单个 HTML 字符串
        combined_html = "<br>".join(
            self._format_line_html(line) for line in self._pending_logs
        )
        last_log = self._pending_logs[-1]

        self._pending_logs.clear()
        self._batch_timer.stop()

        sb = self.text_edit.verticalScrollBar()
        if self.auto_scroll_check.isChecked():
            # 自动滚动：appendHtml 会移动光标到末尾
            self.text_edit.appendHtml(combined_html)
            sb.setValue(sb.maximum())
        else:
            # 未勾选自动滚动：保存滚动位置，append 后恢复
            saved = sb.value()
            self.text_edit.appendHtml(combined_html)
            sb.setValue(saved)

        # Task 11f：触发最近日志横幅展开动画（用最后一条通过过滤的日志）
        self._show_recent_banner(last_log)

    def _on_scroll_changed(self, value: int) -> None:
        """滚动条变化：若用户手动滚动到非底部，取消自动滚动勾选。"""
        if self._suppress_scroll_handler:
            return
        if not self.auto_scroll_check.isChecked():
            return
        sb = self.text_edit.verticalScrollBar()
        # 容差：距离底部 5 像素以内视为已在底部
        if value < sb.maximum() - 5:
            self.auto_scroll_check.blockSignals(True)
            self.auto_scroll_check.setChecked(False)
            self.auto_scroll_check.blockSignals(False)

    def _on_auto_scroll_toggled(self, checked: bool) -> None:
        """自动滚动复选框切换：勾选时立即滚动到底部。"""
        if checked:
            sb = self.text_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear_log(self) -> None:
        """清空日志文本框与原始日志列表。

        Task 11f：同时停止最近日志横幅动画并重置横幅高度为 0。
        Task 6：同时清空待刷新缓冲区并停止批量定时器。
        T-C4：同时重置 ``_level_counts`` 为全 0 并更新徽章。
        """
        self._raw_logs.clear()
        # Task 6：清空待刷新缓冲区与定时器
        self._pending_logs.clear()
        self._batch_timer.stop()
        self.text_edit.clear()
        # T-C4：重置级别计数并更新徽章
        for key in self._level_counts:
            self._level_counts[key] = 0
        self._update_badges()
        # 停止横幅动画并重置
        if self._banner_anim_group is not None:
            try:
                self._banner_anim_group.stop()
            except RuntimeError:
                pass
            self._banner_anim_group = None
        self._recent_banner.setMaximumHeight(0)
        self._recent_banner.setText("")

    def save_log(self) -> None:
        """打开文件保存对话框，将当前过滤后的日志内容写入文件。

        向后兼容方法，等价于 :meth:`_save_filtered`。
        """
        self._save_filtered()

    def _save_filtered(self) -> None:
        """保存当前通过级别与搜索过滤的日志到文件。

        重新过滤 ``_raw_logs`` 列表，仅保存通过当前级别与搜索过滤条件的
        日志行。通过 :class:`QFileDialog.getSaveFileName` 选择保存路径，
        写入 UTF-8 文本文件。
        """
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前过滤结果",
            "chatterbox.log",
            "日志文件 (*.log);;文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not path:
            return

        lines = [line for line in self._raw_logs if self._passes_filter(line)]
        content = "\n".join(lines)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            logger.error("保存过滤日志失败 %r: %s", path, exc)
            return

        logger.info("过滤日志已保存到 %s", path)

    def _save_all(self) -> None:
        """保存全部原始日志到文件。

        遍历 ``_raw_logs`` 原始列表，写入 UTF-8 文本文件。
        通过 :class:`QFileDialog.getSaveFileName` 选择保存路径。
        """
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存全部日志",
            "chatterbox.log",
            "日志文件 (*.log);;文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not path:
            return

        content = "\n".join(self._raw_logs)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            logger.error("保存全部日志失败 %r: %s", path, exc)
            return

        logger.info("全部日志已保存到 %s", path)

    # ----------------------------------------------------------------------
    # 公开方法
    # ----------------------------------------------------------------------
    def append(self, text: str) -> None:
        """公开方法：手动追加日志文本。

        Args:
            text: 要追加的文本。
        """
        self._append_log(text)

    # ----------------------------------------------------------------------
    # Task 6：窗口销毁时 flush 剩余日志
    # ----------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        """Task 6：窗口关闭时 flush 剩余日志到 UI，避免丢失未刷新的日志。"""
        try:
            self._flush_pending_logs()
        except Exception:
            # 静默吞掉，避免关闭时异常导致问题
            pass
        super().closeEvent(event)
