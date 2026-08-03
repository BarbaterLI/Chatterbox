"""进度控件：状态灯 + 分段着色进度条 + 计数 + ETA + 并发数显示。

提供 ``ProgressWidget``，封装 ``_SegmentedProgressBar`` 与若干 QLabel：
- 状态指示灯：圆形 SVG 图标，反映 idle/running/success/error
- 进度条范围 0..100，按成功/失败分段着色（``_SegmentedProgressBar``）
- 计数标签 "已完成 / 总数 (成功 N, 失败 N)"
- ETA 标签 "剩余: 约 Ns" / "剩余: 约 Nm Ns" / "剩余: -"
- 并发数标签 "并发: active / max_threads"
- 提供 ``set_total`` / ``update_progress`` / ``set_concurrency`` / ``reset`` /
  ``set_summary`` / ``set_state`` 方法供主窗口驱动

Task 11b 优化（Qt6 原生动画）：
- 运行中根据失败率，状态灯通过 :class:`QVariantAnimation` 颜色渐变
  （绿 → 黄 → 橙 → 红，Linear 缓动），叠加在 :class:`QGraphicsColorizeEffect` 上
- 任务完成时状态灯使用 :class:`QPropertyAnimation` 闪烁 3 次脉冲
  （300ms 间隔，InOutCubic 缓动），通过 :class:`QSequentialAnimationGroup` 串行编排
- 所有动画通过 :class:`AnimationManager` 统一管理，支持「禁用动画」降级
- 状态切换（idle/running/success/error）时自动停止动画并重置效果

约束：保留 Qt6 原版样式，不引入自定义 QSS。所有新增控件继承 Qt 默认样式。
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import (
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsColorizeEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chatterbox.gui.theme.design_tokens import DesignTokens
from chatterbox.gui.widgets.animation_manager import AnimationManager
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)

# 状态指示灯像素尺寸
_STATUS_ICON_SIZE = 16

# ETA 文本前缀
_ETA_PREFIX = "剩余: "

# 颜色渐变动画时长（毫秒）
_COLOR_ANIM_DURATION_MS = 400

# 闪烁动画参数：3 次脉冲，单次 300ms
_FLASH_PULSES = 3
_FLASH_PULSE_DURATION_MS = 300
_FLASH_STRENGTH_MIN = 0.0
_FLASH_STRENGTH_MAX = 1.0

# 合法状态名集合
_VALID_STATES = {"idle", "running", "success", "error"}

# 暂停状态进度条文案前缀
_PAUSED_PREFIX = "（已暂停）"

# 统计刷新定时器间隔（毫秒）
_STATS_TIMER_INTERVAL_MS = 1000

# 统计标签占位符（无数据时显示）
_STATS_PLACEHOLDER = "--"


class _ClickableLabel(QLabel):
    """可点击的 QLabel，左键点击发出 ``clicked`` 信号。

    用于成功/失败计数，点击切换日志面板过滤。不引入 QSS，遵循 Qt6 原生风格。
    参考 :class:`chatterbox.gui.widgets.log_panel._ClickableLabel` 实现。
    """

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _SegmentedProgressBar(QProgressBar):
    """分段着色进度条。

    重写 ``paintEvent``，按 succeeded/failed 占总宽比例绘制两段：
    - succeeded 段用 palette 默认 highlight 色（保留 Qt 原版样式）
    - failed 段叠加红色（``DesignTokens.color_failure()``）
    - 未填充部分用 palette base 色
    - 文本仍按 ``text()`` 居中绘制
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._succeeded = 0
        self._failed = 0
        self._total = 0

    def set_segments(self, succeeded: int, failed: int, total: int) -> None:
        """更新分段计数并触发重绘。

        Args:
            succeeded: 成功数。
            failed: 失败数。
            total: 总数。
        """
        self._succeeded = max(0, succeeded)
        self._failed = max(0, failed)
        self._total = max(0, total)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        palette = self.palette()
        outer = self.rect()

        # 背景 groove：palette base
        painter.fillRect(outer, palette.base())

        # 边框：palette mid（Qt 原版 groove 边框色）
        painter.setPen(palette.color(QPalette.ColorRole.Mid))
        painter.drawRect(outer.adjusted(0, 0, -1, -1))

        # 内容区（边框内）
        content = outer.adjusted(1, 1, -1, -1)
        if content.width() <= 0 or content.height() <= 0:
            return

        # 计算分段宽度比例（按占总宽比例）
        if self._total > 0:
            succeeded_frac = min(1.0, self._succeeded / self._total)
            failed_frac = min(1.0, self._failed / self._total)
        else:
            succeeded_frac = 0.0
            failed_frac = 0.0

        full_width = content.width()
        succeeded_width = min(full_width, int(full_width * succeeded_frac))
        # 失败段不能越过已绘制成功段的右边界，也不能超过总宽
        failed_width = min(
            full_width - succeeded_width,
            int(full_width * failed_frac),
        )

        # succeeded 段：palette highlight（Qt 默认）
        if succeeded_width > 0:
            painter.fillRect(
                QRect(
                    content.left(),
                    content.top(),
                    succeeded_width,
                    content.height(),
                ),
                palette.highlight(),
            )

        # failed 段：红色叠加（运行时按当前主题读取令牌）
        if failed_width > 0:
            painter.fillRect(
                QRect(
                    content.left() + succeeded_width,
                    content.top(),
                    failed_width,
                    content.height(),
                ),
                DesignTokens.color_failure(),
            )

        # 文本（保留 QProgressBar 默认 text() 行为，如 "80%"）
        if self.isTextVisible():
            painter.setPen(palette.color(QPalette.ColorRole.Text))
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, self.text())


class ProgressWidget(QWidget):
    """进度显示控件。

    继承 QWidget，封装状态指示灯、分段着色进度条、计数标签、ETA 标签与
    并发数标签，由外部通过方法驱动状态更新。

    Task 11b 动画增强：
        - ``status_label`` 应用 :class:`QGraphicsColorizeEffect`，运行中根据
          失败率通过 :class:`QVariantAnimation` 平滑过渡颜色
          （绿 → 黄 → 橙 → 红）
        - 任务完成时通过 :class:`QPropertyAnimation` 闪烁 3 次脉冲
          （``effect.strength`` 在 0..1 之间循环），由
          :class:`QSequentialAnimationGroup` 串行编排
        - 所有动画经 :class:`AnimationManager` 创建，尊重「禁用动画」开关
          与平台 ``prefers-reduced-motion``

    Task T-C3 暂停/恢复与统计扩展：
        - 控制栏新增「暂停/恢复」按钮，通过 ``pause_requested`` 信号通知
          主窗口切换 :class:`TaskScheduler` 的暂停状态，本控件不直接持有
          调度器引用
        - 统计区新增「速率」（files/s）与「平均耗时」（s/项）标签，由
          :class:`QTimer` 每秒基于 ``_start_time`` 与 ``_completed`` 刷新
        - 成功/失败计数改为 :class:`_ClickableLabel`，点击发射
          ``filter_requested`` 信号（参数 ``"success"`` 或 ``"error"``），
          供主窗口切换日志面板过滤
        - 暂停状态时进度条文案追加 ``「（已暂停）」`` 前缀
    """

    # 暂停/恢复请求信号：True=暂停，False=恢复
    pause_requested = Signal(bool)
    # 日志过滤请求信号：参数 "success" 或 "error"
    filter_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 状态指示灯
        self.status_label = QLabel(self)
        self._state = "idle"
        self._apply_state_icon("idle")
        self._update_status_tooltip("idle")

        # QGraphicsColorizeEffect：用于状态灯颜色渐变与闪烁（Task 11b）
        # strength=0 时不影响原图标显示；运行中通过动画调整 strength 与 color
        self._color_effect = QGraphicsColorizeEffect(self.status_label)
        self._color_effect.setStrength(_FLASH_STRENGTH_MIN)
        self.status_label.setGraphicsEffect(self._color_effect)

        # 动画引用（持有以防止 GC）
        self._failure_rate_anim = None  # type: ignore[var-annotated]
        self._flash_anim_group: QSequentialAnimationGroup | None = None

        # 进度条（分段着色）
        self.progress_bar = _SegmentedProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        # 计数标签：已完成 / 总数（成功/失败计数拆分为可点击标签）
        self.count_label = QLabel("0 / 0", self)

        # 成功计数标签（可点击，点击切换日志过滤为 success）
        self.success_label = _ClickableLabel("成功 0", self)
        self.success_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.success_label.setToolTip("点击切换日志面板为成功项过滤")
        self.success_label.clicked.connect(
            lambda: self.filter_requested.emit("success")
        )

        # 失败计数标签（可点击，点击切换日志过滤为 error）
        self.failed_label = _ClickableLabel("失败 0", self)
        self.failed_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.failed_label.setToolTip("点击切换日志面板为失败项过滤")
        self.failed_label.clicked.connect(
            lambda: self.filter_requested.emit("error")
        )

        # ETA 标签
        self.eta_label = QLabel(_ETA_PREFIX + "-", self)

        # 并发数标签
        self.concurrency_label = QLabel("并发: 0 / 0", self)
        self.concurrency_label.setToolTip("活跃任务数 / 最大并发数")

        # 图例标签（进度条下方，纯文本 + tooltip，无 QSS/inline style）
        # 圆点 ● 默认使用 QPalette 前景色（QLabel 文本色由 palette 决定），
        # 不使用任何 inline QSS/style 属性，符合「保留 Qt6 原版样式」约束。
        self.legend_label = QLabel("● 成功（默认色）  ● 失败（红色）", self)
        self.legend_label.setToolTip("进度条已填充部分：默认色=成功，红色=失败")

        # 暂停/恢复按钮（仅运行状态启用；不持有 TaskScheduler 引用，
        # 通过 pause_requested 信号通知主窗口切换调度器暂停状态）
        self.pause_button = QPushButton("暂停", self)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._on_pause_clicked)

        # 速率标签（files/s）：已完成数 / 已耗时秒数
        self.rate_label = QLabel(f"速率: {_STATS_PLACEHOLDER}", self)
        self.rate_label.setToolTip("已完成文件数 / 已耗时秒数")

        # 平均耗时标签（s/项）：已耗时秒数 / 已完成数
        self.avg_time_label = QLabel(f"平均: {_STATS_PLACEHOLDER}", self)
        self.avg_time_label.setToolTip("已耗时秒数 / 已完成文件数")

        # 主布局：垂直排列，第一行为状态灯/进度条/计数/ETA/并发，
        # 第二行为图例，第三行为控制栏（暂停按钮 + 速率/平均耗时）
        main_layout = QVBoxLayout(self)

        # 第一行：单行水平排列 状态灯 | 进度条(stretch=1) | 计数 | 成功 | 失败 | ETA | 并发
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.progress_bar, stretch=1)
        top_layout.addWidget(self.count_label)
        top_layout.addWidget(self.success_label)
        top_layout.addWidget(self.failed_label)
        top_layout.addWidget(self.eta_label)
        top_layout.addWidget(self.concurrency_label)
        main_layout.addLayout(top_layout)

        # 第二行：图例（进度条下方）
        main_layout.addWidget(self.legend_label)

        # 第三行：控制栏（暂停按钮 | 弹性间距 | 速率 | 平均耗时）
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.pause_button)
        control_layout.addStretch(1)
        control_layout.addWidget(self.rate_label)
        control_layout.addWidget(self.avg_time_label)
        main_layout.addLayout(control_layout)

        self.setLayout(main_layout)

        # 内部记录的成功/失败计数，用于 update_progress 时刷新文本与分段
        self._succeeded = 0
        self._failed = 0
        self._total = 0
        self._completed = 0
        # 任务开始时间（time.time()），None 表示尚未开始
        self._start_time: float | None = None
        # 上次失败率颜色（用于颜色渐变动画的起始值）
        self._current_failure_color: QColor = DesignTokens.failure_rate_colors()[0][1]

        # 暂停状态标志（True=已暂停，按钮文本为「恢复」）
        self._is_paused: bool = False

        # 统计刷新定时器：每秒刷新速率与平均耗时
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(_STATS_TIMER_INTERVAL_MS)
        self._stats_timer.timeout.connect(self._refresh_stats)

        logger.debug("ProgressWidget 已初始化")

    # ----------------------------------------------------------------------
    # 内部辅助
    # ----------------------------------------------------------------------
    def _apply_state_icon(self, state: str) -> None:
        """根据状态名设置状态指示灯图标。

        图标不可用（如 QSvg 缺失）时退化为文本占位 "●"，避免空标签塌陷。
        """
        icon = IconProvider.status_icon(state)
        if icon.isNull():
            self.status_label.setPixmap(QPixmap())
            self.status_label.setText("●")
        else:
            self.status_label.setText("")
            self.status_label.setPixmap(
                icon.pixmap(QSize(_STATUS_ICON_SIZE, _STATUS_ICON_SIZE))
            )

    def _update_status_tooltip(self, state: str) -> None:
        """根据状态更新状态指示灯的 tooltip。

        Args:
            state: 状态名（``"idle"``、``"running"``、``"success"``、
                ``"error"``）。未知状态视为 ``"idle"``。
        """
        tooltips = {
            "idle": "空闲状态",
            "running": "正在处理任务",
            "success": "全部完成（成功）",
            "error": "有失败任务",
        }
        self.status_label.setToolTip(tooltips.get(state, "空闲状态"))

    def _format_eta(self, eta_seconds: float) -> str:
        """将剩余秒数格式化为 "约 Ns"、"约 Nm Ns" 或 "约 Nh Nm"。

        - 小于 60s 显示 "约 Ns"
        - 大于等于 60s 且小于 3600s 显示 "约 Nm Ns"
        - 大于等于 3600s 显示 "约 Nh Nm"
        """
        eta_int = max(0, int(round(eta_seconds)))
        if eta_int < 60:
            return _ETA_PREFIX + f"约 {eta_int}s"
        if eta_int < 3600:
            minutes, seconds = divmod(eta_int, 60)
            return _ETA_PREFIX + f"约 {minutes}m {seconds}s"
        hours = eta_int // 3600
        minutes = (eta_int % 3600) // 60
        return _ETA_PREFIX + f"约 {hours}h {minutes}m"

    # ----------------------------------------------------------------------
    # Task T-C3 暂停/恢复与统计辅助
    # ----------------------------------------------------------------------
    def _on_pause_clicked(self) -> None:
        """暂停/恢复按钮点击槽。

        根据当前 ``_is_paused`` 标志切换状态、按钮文本与进度条文案，
        并发射 ``pause_requested`` 信号通知主窗口切换调度器暂停状态。

        - 未暂停 → 暂停：按钮文本变为「恢复」，发射 ``pause_requested(True)``
        - 已暂停 → 恢复：按钮文本变为「暂停」，发射 ``pause_requested(False)``
        """
        if not self._is_paused:
            self._set_paused(True)
            self.pause_requested.emit(True)
        else:
            self._set_paused(False)
            self.pause_requested.emit(False)

    def _set_paused(self, paused: bool) -> None:
        """更新内部暂停标志、按钮文本与进度条文案（不发射信号）。

        Args:
            paused: ``True`` 表示暂停，``False`` 表示恢复。
        """
        self._is_paused = paused
        self.pause_button.setText("恢复" if paused else "暂停")
        self._update_pause_text()

    def _update_pause_text(self) -> None:
        """根据暂停状态更新进度条文案前缀。

        暂停时格式为 ``「（已暂停）%p%」``，非暂停时为 ``「%p%」``。
        """
        if self._is_paused:
            self.progress_bar.setFormat(_PAUSED_PREFIX + "%p%")
        else:
            self.progress_bar.setFormat("%p%")

    def _refresh_stats(self) -> None:
        """刷新速率与平均耗时标签。

        基于 ``_start_time`` 与 ``_completed`` 计算：
        - 速率 = 已完成数 / 已耗时秒数（files/s）
        - 平均耗时 = 已耗时秒数 / 已完成数（s/项）

        已完成数为 0 或尚未开始时显示占位符 ``--``。
        """
        if self._start_time is None or self._completed <= 0:
            self.rate_label.setText(f"速率: {_STATS_PLACEHOLDER}")
            self.avg_time_label.setText(f"平均: {_STATS_PLACEHOLDER}")
            return

        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            self.rate_label.setText(f"速率: {_STATS_PLACEHOLDER}")
            self.avg_time_label.setText(f"平均: {_STATS_PLACEHOLDER}")
            return

        rate = self._completed / elapsed
        avg = elapsed / self._completed
        self.rate_label.setText(f"速率: {rate:.2f} files/s")
        self.avg_time_label.setText(f"平均: {avg:.2f} s/项")

    # ----------------------------------------------------------------------
    # Task 11b 动画辅助
    # ----------------------------------------------------------------------
    @staticmethod
    def _failure_rate_to_color(rate: float) -> QColor:
        """按失败率返回状态灯颜色（线性插值）。

        失败率关键点由 :meth:`DesignTokens.failure_rate_colors` 提供
        （亮主题：``0.0→#22c55e``、``0.15→#eab308``、
        ``0.30→#f97316``、``0.50→#ef4444``）。

        Args:
            rate: 失败率，范围 ``[0.0, 1.0]``，超出范围按端点处理。

        Returns:
            对应失败率的插值颜色。
        """
        rate = max(0.0, min(1.0, float(rate)))
        colors = DesignTokens.failure_rate_colors()

        # 低于第一个关键点或高于最后一个关键点，直接返回端点色
        if rate <= colors[0][0]:
            return QColor(colors[0][1])
        if rate >= colors[-1][0]:
            return QColor(colors[-1][1])

        # 在相邻关键点之间线性插值
        for i in range(len(colors) - 1):
            r1, c1 = colors[i]
            r2, c2 = colors[i + 1]
            if r1 <= rate <= r2:
                t = (rate - r1) / (r2 - r1) if r2 > r1 else 0.0
                return QColor(
                    int(c1.red() + (c2.red() - c1.red()) * t),
                    int(c1.green() + (c2.green() - c1.green()) * t),
                    int(c1.blue() + (c2.blue() - c1.blue()) * t),
                    int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
                )
        # 理论不可达
        return QColor(colors[-1][1])

    def _stop_failure_rate_animation(self) -> None:
        """停止进行中的失败率颜色动画。"""
        if self._failure_rate_anim is not None:
            try:
                self._failure_rate_anim.stop()
            except RuntimeError:
                pass
            self._failure_rate_anim = None

    def _stop_flash_animation(self) -> None:
        """停止进行中的闪烁动画并重置效果强度。"""
        if self._flash_anim_group is not None:
            try:
                self._flash_anim_group.stop()
            except RuntimeError:
                pass
            self._flash_anim_group = None
        # 重置 strength 为最小（不影响原图标）
        self._color_effect.setStrength(_FLASH_STRENGTH_MIN)

    def _animate_failure_rate_color(self, failed: int, total: int) -> None:
        """根据失败率启动颜色渐变动画（仅 running 状态调用）。

        使用 :class:`QVariantAnimation` 在 ``_COLOR_ANIM_DURATION_MS`` 内
        从当前颜色线性插值到目标颜色，每帧通过 :meth:`QGraphicsColorizeEffect.setColor`
        更新效果颜色，并设置 ``strength=1.0`` 让颜色叠加生效。

        Args:
            failed: 当前失败数。
            total: 总数。
        """
        if total <= 0:
            rate = 0.0
        else:
            rate = failed / total

        target_color = self._failure_rate_to_color(rate)
        start_color = QColor(self._current_failure_color)

        # 颜色未变化，跳过动画
        if start_color == target_color:
            return

        # 停止上一个动画
        self._stop_failure_rate_animation()

        # 启用 colorize 效果强度，让颜色叠加可见
        self._color_effect.setColor(target_color)
        self._color_effect.setStrength(_FLASH_STRENGTH_MAX)

        # 通过 AnimationManager 创建 QVariantAnimation（尊重禁用动画开关）
        # 颜色插值用 Linear 缓动，过渡更自然
        from PySide6.QtCore import QEasingCurve

        anim_mgr = AnimationManager.instance()
        self._failure_rate_anim = anim_mgr.make_variant_animation(
            start=start_color,
            end=target_color,
            duration=_COLOR_ANIM_DURATION_MS,
            on_value_changed=self._on_failure_rate_color_changed,
            easing=QEasingCurve.Type.Linear,
        )
        # 记录目标颜色为当前颜色（动画结束后更新）
        self._current_failure_color = target_color
        self._failure_rate_anim.start()

    def _on_failure_rate_color_changed(self, color: QColor) -> None:
        """``QVariantAnimation.valueChanged`` 回调：更新 colorize 效果颜色。"""
        try:
            self._color_effect.setColor(QColor(color))
        except RuntimeError:
            # 控件已销毁
            pass

    def _start_completion_flash(self) -> None:
        """启动任务完成闪烁动画（3 次脉冲）。

        通过 :class:`QSequentialAnimationGroup` 串行编排 3 个
        :class:`QPropertyAnimation`，每个动画将 ``effect.strength`` 从 0
        渐变到 1 再到 0（InOutCubic 缓动），形成 3 次脉冲反馈。
        所有动画经 :class:`AnimationManager` 创建，尊重「禁用动画」开关。
        """
        # 停止现有动画
        self._stop_flash_animation()
        self._stop_failure_rate_animation()

        anim_mgr = AnimationManager.instance()
        from PySide6.QtCore import QEasingCurve

        group = QSequentialAnimationGroup(self)
        easing = QEasingCurve.Type.InOutCubic

        # 3 次脉冲：每次 0 → 1 → 0
        for _ in range(_FLASH_PULSES):
            # 上升段：strength 0 → 1
            up_anim = anim_mgr.make_property_animation(
                target=self._color_effect,
                prop=b"strength",
                start=_FLASH_STRENGTH_MIN,
                end=_FLASH_STRENGTH_MAX,
                duration=_FLASH_PULSE_DURATION_MS,
                easing=easing,
            )
            # 下降段：strength 1 → 0
            down_anim = anim_mgr.make_property_animation(
                target=self._color_effect,
                prop=b"strength",
                start=_FLASH_STRENGTH_MAX,
                end=_FLASH_STRENGTH_MIN,
                duration=_FLASH_PULSE_DURATION_MS,
                easing=easing,
            )
            group.addAnimation(up_anim)
            group.addAnimation(down_anim)

        self._flash_anim_group = group
        group.start()

    # ----------------------------------------------------------------------
    # 公开方法
    # ----------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        """设置状态指示灯。

        状态切换时自动停止失败率颜色动画与闪烁动画，并重置 colorize 效果
        强度为 0，让原图标本色显示。运行中（``"running"``）的失败率颜色
        渐变由 :meth:`update_progress` 触发。

        Args:
            state: 状态名（``"idle"``、``"running"``、``"success"``、
                ``"error"``）。未知状态视为 ``"idle"``。
        """
        if state not in _VALID_STATES:
            logger.warning("未知状态 %r，按 idle 处理", state)
            state = "idle"
        self._state = state
        self._apply_state_icon(state)
        self._update_status_tooltip(state)

        # 状态切换时停止所有动画并重置 colorize 效果
        self._stop_failure_rate_animation()
        self._stop_flash_animation()
        # 非 running 状态：重置 colorize 效果强度为 0（不影响原图标）
        if state != "running":
            self._color_effect.setStrength(_FLASH_STRENGTH_MIN)
            # 重置当前失败率颜色为绿色起点
            self._current_failure_color = DesignTokens.failure_rate_colors()[0][1]

        # T-C3：暂停按钮仅在 running 状态启用；离开 running 时重置暂停状态
        self.pause_button.setEnabled(state == "running")
        if state != "running" and self._is_paused:
            self._set_paused(False)

    def set_total(self, total: int) -> None:
        """设置总数，重置进度条为 0 并记录任务开始时间。

        Args:
            total: 任务总数。
        """
        self._total = max(0, total)
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._start_time = time.time()
        self.progress_bar.setValue(0)
        self.progress_bar.set_segments(0, 0, self._total)
        self.count_label.setText(f"0 / {self._total}")
        self.success_label.setText("成功 0")
        self.failed_label.setText("失败 0")
        self.eta_label.setText(_ETA_PREFIX + "-")
        # 重置失败率颜色为绿色起点
        self._current_failure_color = DesignTokens.failure_rate_colors()[0][1]
        self._color_effect.setStrength(_FLASH_STRENGTH_MIN)
        # T-C3：重置暂停状态与统计标签，启动统计刷新定时器
        if self._is_paused:
            self._set_paused(False)
        self.rate_label.setText(f"速率: {_STATS_PLACEHOLDER}")
        self.avg_time_label.setText(f"平均: {_STATS_PLACEHOLDER}")
        self._stats_timer.start()

    def update_progress(
        self,
        completed: int,
        total: int,
        succeeded: int = 0,
        failed: int = 0,
    ) -> None:
        """更新进度条、计数与 ETA。

        保留原 ``(completed, total)`` 二参签名兼容性，``succeeded`` 与
        ``failed`` 为可选参数（默认 0），传入后启用分段着色。

        Task 11b：``running`` 状态下根据 ``failed/total`` 失败率启动
        :class:`QVariantAnimation` 颜色渐变动画（绿 → 黄 → 橙 → 红）。

        Args:
            completed: 已完成数。
            total: 总数。
            succeeded: 成功数（默认 0，向后兼容）。
            failed: 失败数（默认 0，向后兼容）。
        """
        self._completed = max(0, completed)
        self._total = max(0, total)
        self._succeeded = max(0, succeeded)
        self._failed = max(0, failed)
        if self._total > 0:
            percent = int(self._completed * 100 / self._total)
            percent = min(100, max(0, percent))
        else:
            percent = 0
        self.progress_bar.setValue(percent)
        self.progress_bar.set_segments(self._succeeded, self._failed, self._total)
        self.count_label.setText(f"{self._completed} / {self._total}")
        self.success_label.setText(f"成功 {self._succeeded}")
        self.failed_label.setText(f"失败 {self._failed}")

        # Task 11b：running 状态下根据失败率启动颜色渐变动画
        if self._state == "running":
            self._animate_failure_rate_color(self._failed, self._total)

        # ETA 预测：公式 eta = (total - completed) * (elapsed / completed)
        if (
            self._start_time is not None
            and self._completed > 0
            and self._total > self._completed
        ):
            elapsed = time.time() - self._start_time
            eta = (self._total - self._completed) * (elapsed / self._completed)
            self.eta_label.setText(self._format_eta(eta))
        elif (
            self._start_time is not None
            and self._total > 0
            and self._completed >= self._total
        ):
            # 任务已完成
            self.eta_label.setText(_ETA_PREFIX + "约 0s")
        else:
            self.eta_label.setText(_ETA_PREFIX + "-")

    def set_concurrency(self, active: int, max_threads: int) -> None:
        """更新并发数标签。

        Args:
            active: 当前活跃并发数。
            max_threads: 最大并发数。
        """
        self.concurrency_label.setText(f"并发: {active} / {max_threads}")

    def reset(self) -> None:
        """重置为初始状态。"""
        self._total = 0
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._start_time = None
        self._state = "idle"
        self.progress_bar.setValue(0)
        self.progress_bar.set_segments(0, 0, 0)
        self.count_label.setText("0 / 0")
        self.success_label.setText("成功 0")
        self.failed_label.setText("失败 0")
        self.concurrency_label.setText("并发: 0 / 0")
        self.eta_label.setText(_ETA_PREFIX + "-")
        self._apply_state_icon("idle")
        self._update_status_tooltip("idle")
        # 停止所有动画并重置 colorize 效果
        self._stop_failure_rate_animation()
        self._stop_flash_animation()
        self._current_failure_color = DesignTokens.failure_rate_colors()[0][1]
        # T-C3：重置暂停状态、统计标签，停止统计定时器与暂停按钮
        self._stats_timer.stop()
        if self._is_paused:
            self._set_paused(False)
        self.pause_button.setEnabled(False)
        self.rate_label.setText(f"速率: {_STATS_PLACEHOLDER}")
        self.avg_time_label.setText(f"平均: {_STATS_PLACEHOLDER}")

    def set_summary(self, succeeded: int, failed: int, elapsed: float) -> None:
        """显示汇总信息。

        在计数标签中更新成功/失败数，并在并发数标签位置显示耗时汇总。
        ETA 标签置为 "剩余: 约 0s" 表示任务完成。

        Task 11b：调用 ``set_summary`` 后自动触发 3 次脉冲闪烁动画
        （:meth:`_start_completion_flash`），通过状态灯闪烁反馈任务完成。

        Args:
            succeeded: 成功数。
            failed: 失败数。
            elapsed: 总耗时（秒）。
        """
        self._succeeded = max(0, succeeded)
        self._failed = max(0, failed)
        total = self._succeeded + self._failed
        self._total = total
        self._completed = total
        self.progress_bar.setValue(100 if total > 0 else 0)
        self.progress_bar.set_segments(self._succeeded, self._failed, total)
        self.count_label.setText(f"{total} / {total}")
        self.success_label.setText(f"成功 {self._succeeded}")
        self.failed_label.setText(f"失败 {self._failed}")
        self.concurrency_label.setText(f"耗时: {elapsed:.2f} s")
        self.eta_label.setText(_ETA_PREFIX + "约 0s")
        # T-C3：任务完成，停止统计定时器并按汇总耗时刷新平均耗时
        self._stats_timer.stop()
        if total > 0 and elapsed > 0:
            self.rate_label.setText(f"速率: {total / elapsed:.2f} files/s")
            self.avg_time_label.setText(f"平均: {elapsed / total:.2f} s/项")
        # Task 11b：触发任务完成闪烁动画（3 次脉冲）
        self._start_completion_flash()

    def flash_completion(self) -> None:
        """手动触发任务完成闪烁动画（3 次脉冲）。

        可由主窗口在 ``all_finished`` 信号回调中显式调用，与
        :meth:`set_summary` 内部触发的闪烁互斥（自动停止对方）。
        """
        self._start_completion_flash()


__all__ = ["ProgressWidget"]
