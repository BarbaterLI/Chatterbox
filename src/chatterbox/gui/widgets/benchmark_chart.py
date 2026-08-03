"""并发基准测试图表控件。

基于 QPainter 自绘的双 Y 轴折线图，无第三方依赖。
左 Y 轴：吞吐量（tasks/s，蓝色），右 Y 轴：p95 时延（ms，红色）。
X 轴：并发数。最优并发点用绿色竖线标注。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

if TYPE_CHECKING:
    from chatterbox.core.concurrency_benchmark import BenchmarkResult

logger = logging.getLogger(__name__)

# 图表布局边距（像素）
MARGIN_LEFT = 60  # 左 Y 轴标签宽度
MARGIN_RIGHT = 60  # 右 Y 轴标签宽度
MARGIN_TOP = 30  # 顶部留白（含图例）
MARGIN_BOTTOM = 40  # 底部 X 轴标签高度

# Y 轴刻度数量
_Y_TICK_COUNT = 5

# 数据点圆点半径（像素）
_MARKER_RADIUS = 4

# 悬停命中检测阈值（曼哈顿距离，像素）
_HIT_RADIUS = 10

# 图例尺寸常量
_LEGEND_PADDING = 6  # 内边距
_LEGEND_LINE_LEN = 18  # 颜色样本线长度
_LEGEND_ROW_HEIGHT = 16  # 单行高度


@dataclass
class _ChartPoint:
    """图表数据点。

    存储原始测量值与 paintEvent 中计算的屏幕坐标（供 mouseMoveEvent
    命中检测使用，避免在鼠标事件中重算缩放）。
    """

    concurrency: int
    throughput: float  # tasks/s
    p95_latency: float  # ms
    success_rate: float  # 0.0~1.0
    # 屏幕坐标（paintEvent 中计算）
    throughput_pos: QPointF = field(default_factory=QPointF)
    p95_pos: QPointF = field(default_factory=QPointF)


class BenchmarkChart(QWidget):
    """并发性能基准测试图表控件。

    使用 QPainter 绘制双 Y 轴折线图：
    - 吞吐量曲线（蓝色，左 Y 轴，tasks/s）
    - p95 时延曲线（红色，右 Y 轴，ms）
    - X 轴：并发数
    - 最优并发点：绿色竖线

    支持鼠标悬停显示 QToolTip（并发数 / 吞吐量 / p95 / 成功率）。

    数据通过 :meth:`set_data` 注入，参数为 ``BenchmarkResult`` 列表与
    最优并发数。控件不持有基准测试引擎引用，仅负责绘制。
    """

    # 颜色常量
    _THROUGHPUT_COLOR = QColor("#2196F3")  # 蓝色
    _LATENCY_COLOR = QColor("#F44336")  # 红色
    _OPTIMAL_COLOR = QColor("#4CAF50")  # 绿色
    _AXIS_COLOR = QColor("#9E9E9E")  # 灰色
    _TEXT_COLOR = QColor("#212121")  # 深色
    _GRID_COLOR = QColor("#E0E0E0")  # 浅灰
    _BG_COLOR = QColor("#FAFAFA")  # 背景

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[_ChartPoint] = []
        self._optimal_concurrency: int = 0
        self.setMouseTracking(True)  # 启用鼠标追踪以支持悬停
        self.setMinimumSize(400, 300)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def set_data(
        self,
        results: list[BenchmarkResult],
        optimal_concurrency: int,
    ) -> None:
        """设置图表数据并触发重绘。

        Args:
            results: ``BenchmarkResult`` 列表（含 concurrency/throughput/
                p95_latency/success_rate 字段）。
            optimal_concurrency: 最优并发数（绿色竖线标注）。
        """
        self._points = [
            _ChartPoint(
                concurrency=r.concurrency,
                throughput=r.throughput,
                p95_latency=r.p95_latency,
                success_rate=r.success_rate,
            )
            for r in results
        ]
        self._optimal_concurrency = optimal_concurrency
        self.update()  # 触发重绘

    def clear(self) -> None:
        """清空图表数据。"""
        self._points.clear()
        self._optimal_concurrency = 0
        self.update()

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(400, 300)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(600, 400)

    # ------------------------------------------------------------------
    # 缩放与坐标计算
    # ------------------------------------------------------------------
    def _calculate_scales(
        self, width: int, height: int
    ) -> tuple[int, int, int, int, int, float, float] | None:
        """计算图表缩放参数。

        Returns:
            ``(chart_w, chart_h, min_c, max_c, c_range, max_t, max_l)``
            元组；无数据时返回 ``None``。
        """
        if not self._points:
            return None
        chart_w = width - MARGIN_LEFT - MARGIN_RIGHT
        chart_h = height - MARGIN_TOP - MARGIN_BOTTOM
        concs = [p.concurrency for p in self._points]
        min_c, max_c = min(concs), max(concs)
        throughputs = [p.throughput for p in self._points]
        max_t = max(throughputs) if throughputs else 1.0
        latencies = [p.p95_latency for p in self._points]
        max_l = max(latencies) if latencies else 1.0
        # 避免除零
        c_range = max(max_c - min_c, 1)
        max_t = max(max_t, 0.001)
        max_l = max(max_l, 0.001)
        return chart_w, chart_h, min_c, max_c, c_range, max_t, max_l

    def _throughput_pos(
        self,
        point: _ChartPoint,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> QPointF:
        """计算吞吐量数据点的屏幕坐标（左 Y 轴）。"""
        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        x = MARGIN_LEFT + (point.concurrency - min_c) / c_range * chart_w
        y = (MARGIN_TOP + chart_h) - (point.throughput / max_t) * chart_h
        return QPointF(x, y)

    def _latency_pos(
        self,
        point: _ChartPoint,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> QPointF:
        """计算 p95 时延数据点的屏幕坐标（右 Y 轴）。"""
        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        x = MARGIN_LEFT + (point.concurrency - min_c) / c_range * chart_w
        y = (MARGIN_TOP + chart_h) - (point.p95_latency / max_l) * chart_h
        return QPointF(x, y)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()

        # 1. 背景
        painter.fillRect(self.rect(), self._BG_COLOR)

        # 空数据：画边框 + "无数据" 文本
        scales = self._calculate_scales(width, height)
        if scales is None:
            self._draw_empty(painter, width, height)
            return

        # 更新各数据点屏幕坐标（供 mouseMoveEvent 命中检测）
        for p in self._points:
            p.throughput_pos = self._throughput_pos(p, scales, width, height)
            p.p95_pos = self._latency_pos(p, scales, width, height)

        # 2. 网格线
        self._draw_grid(painter, scales, width, height)

        # 3. 坐标轴
        self._draw_axes(painter, scales, width, height)

        # 4. 轴标签与刻度
        self._draw_axis_labels(painter, scales, width, height)

        # 5. 吞吐量曲线
        self._draw_curve(
            painter,
            [p.throughput_pos for p in self._points],
            self._THROUGHPUT_COLOR,
        )

        # 6. p95 时延曲线
        self._draw_curve(
            painter,
            [p.p95_pos for p in self._points],
            self._LATENCY_COLOR,
        )

        # 7. 最优并发竖线
        self._draw_optimal_line(painter, scales, width, height)

        # 8. 图例
        self._draw_legend(painter, width, height)

    def _draw_empty(
        self, painter: QPainter, width: int, height: int
    ) -> None:
        """绘制空数据状态：图表边框 + 居中 "无数据" 文本。"""
        chart_rect = QRectF(
            MARGIN_LEFT,
            MARGIN_TOP,
            width - MARGIN_LEFT - MARGIN_RIGHT,
            height - MARGIN_TOP - MARGIN_BOTTOM,
        )
        pen = QPen(self._AXIS_COLOR, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(chart_rect)

        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QPen(self._TEXT_COLOR))
        painter.drawText(
            chart_rect, Qt.AlignmentFlag.AlignCenter, "无数据"
        )

    def _draw_grid(
        self,
        painter: QPainter,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> None:
        """绘制水平网格线（左 Y 轴刻度位置，浅灰点线）。"""
        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        pen = QPen(self._GRID_COLOR, 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)

        left = MARGIN_LEFT
        right = MARGIN_LEFT + chart_w
        bottom = MARGIN_TOP + chart_h

        for i in range(_Y_TICK_COUNT):
            # 0..1 的比例
            ratio = i / (_Y_TICK_COUNT - 1) if _Y_TICK_COUNT > 1 else 0.0
            y = bottom - ratio * chart_h
            painter.drawLine(QPointF(left, y), QPointF(right, y))

    def _draw_axes(
        self,
        painter: QPainter,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> None:
        """绘制 X 轴（底）、左 Y 轴、右 Y 轴。"""
        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        pen = QPen(self._AXIS_COLOR, 1)
        painter.setPen(pen)

        left = MARGIN_LEFT
        right = MARGIN_LEFT + chart_w
        top = MARGIN_TOP
        bottom = MARGIN_TOP + chart_h

        # X 轴（底）
        painter.drawLine(QPointF(left, bottom), QPointF(right, bottom))
        # 左 Y 轴
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))
        # 右 Y 轴
        painter.drawLine(QPointF(right, top), QPointF(right, bottom))

    def _draw_axis_labels(
        self,
        painter: QPainter,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> None:
        """绘制轴标题、刻度线与刻度标签。"""
        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        left = MARGIN_LEFT
        right = MARGIN_LEFT + chart_w
        top = MARGIN_TOP
        bottom = MARGIN_TOP + chart_h

        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        axis_pen = QPen(self._AXIS_COLOR, 1)
        tick_len = 4

        # --- 左 Y 轴刻度（吞吐量） ---
        painter.setPen(QPen(self._THROUGHPUT_COLOR))
        for i in range(_Y_TICK_COUNT):
            ratio = i / (_Y_TICK_COUNT - 1) if _Y_TICK_COUNT > 1 else 0.0
            y = bottom - ratio * chart_h
            value = ratio * max_t
            # 刻度线
            painter.setPen(axis_pen)
            painter.drawLine(
                QPointF(left - tick_len, y), QPointF(left, y)
            )
            # 标签
            label = f"{value:.1f}"
            painter.setPen(QPen(self._THROUGHPUT_COLOR))
            text_w = fm.horizontalAdvance(label)
            painter.drawText(
                QRectF(
                    left - tick_len - text_w - 2,
                    y - fm.height() / 2,
                    text_w + 2,
                    fm.height(),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        # --- 右 Y 轴刻度（p95 时延） ---
        painter.setPen(QPen(self._LATENCY_COLOR))
        for i in range(_Y_TICK_COUNT):
            ratio = i / (_Y_TICK_COUNT - 1) if _Y_TICK_COUNT > 1 else 0.0
            y = bottom - ratio * chart_h
            value = ratio * max_l
            # 刻度线
            painter.setPen(axis_pen)
            painter.drawLine(
                QPointF(right, y), QPointF(right + tick_len, y)
            )
            # 标签
            label = f"{value:.0f}"
            painter.setPen(QPen(self._LATENCY_COLOR))
            text_w = fm.horizontalAdvance(label)
            painter.drawText(
                QRectF(
                    right + tick_len + 2,
                    y - fm.height() / 2,
                    text_w + 2,
                    fm.height(),
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        # --- X 轴刻度（并发数） ---
        # 显示每个数据点的并发数；若点过多则均匀采样
        concs = sorted({p.concurrency for p in self._points})
        if len(concs) <= 10:
            tick_concs = concs
        else:
            step = max(1, len(concs) // 8)
            tick_concs = concs[::step]
            if concs[-1] not in tick_concs:
                tick_concs.append(concs[-1])

        painter.setPen(QPen(self._TEXT_COLOR))
        for c in tick_concs:
            x = MARGIN_LEFT + (c - min_c) / c_range * chart_w
            # 刻度线
            painter.setPen(axis_pen)
            painter.drawLine(
                QPointF(x, bottom), QPointF(x, bottom + tick_len)
            )
            # 标签
            label = str(c)
            painter.setPen(QPen(self._TEXT_COLOR))
            text_w = fm.horizontalAdvance(label)
            painter.drawText(
                QRectF(
                    x - text_w / 2 - 2,
                    bottom + tick_len + 2,
                    text_w + 4,
                    fm.height(),
                ),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        # --- 轴标题 ---
        title_font = QFont()
        title_font.setPointSize(9)
        painter.setFont(title_font)

        # 左 Y 轴标题（顶部，蓝色）
        painter.setPen(QPen(self._THROUGHPUT_COLOR))
        painter.drawText(
            QRectF(left - 30, 2, 90, MARGIN_TOP - 4),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "吞吐量(tasks/s)",
        )

        # 右 Y 轴标题（顶部，红色）
        painter.setPen(QPen(self._LATENCY_COLOR))
        right_title = "p95时延(ms)"
        tw = QFontMetrics(title_font).horizontalAdvance(right_title)
        painter.drawText(
            QRectF(right - tw + 30, 2, tw + 10, MARGIN_TOP - 4),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            right_title,
        )

        # X 轴标题（底部居中）
        painter.setPen(QPen(self._TEXT_COLOR))
        x_title = "并发数"
        xtw = QFontMetrics(title_font).horizontalAdvance(x_title)
        painter.drawText(
            QRectF(
                left + chart_w / 2 - xtw / 2,
                bottom + tick_len + fm.height() + 4,
                xtw + 4,
                fm.height(),
            ),
            Qt.AlignmentFlag.AlignCenter,
            x_title,
        )

    def _draw_curve(
        self, painter: QPainter, positions: list[QPointF], color: QColor
    ) -> None:
        """绘制折线 + 圆点标记。

        Args:
            painter: 画布。
            positions: 数据点屏幕坐标列表。
            color: 曲线与标记颜色。
        """
        if not positions:
            return

        # 折线
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(positions) >= 2:
            path = QPainterPath(positions[0])
            for pos in positions[1:]:
                path.lineTo(pos)
            painter.drawPath(path)

        # 圆点标记
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 1))
        for pos in positions:
            painter.drawEllipse(pos, _MARKER_RADIUS, _MARKER_RADIUS)

    def _draw_optimal_line(
        self,
        painter: QPainter,
        scales: tuple[int, int, int, int, int, float, float],
        width: int,
        height: int,
    ) -> None:
        """绘制最优并发数绿色虚线竖线 + 顶部 "最优" 标签。"""
        if self._optimal_concurrency <= 0:
            return

        chart_w, chart_h, min_c, max_c, c_range, max_t, max_l = scales
        # 检查最优并发数是否在数据范围内
        if self._optimal_concurrency < min_c or self._optimal_concurrency > max_c:
            return

        x = MARGIN_LEFT + (
            self._optimal_concurrency - min_c
        ) / c_range * chart_w
        top = MARGIN_TOP
        bottom = MARGIN_TOP + chart_h

        # 虚线
        pen = QPen(self._OPTIMAL_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))

        # 顶部 "最优" 标签
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        fm = QFontMetrics(font)
        label = f"最优({self._optimal_concurrency})"
        text_w = fm.horizontalAdvance(label)
        # 标签背景（浅绿底，避免与曲线重叠不可读）
        bg_rect = QRectF(
            x - text_w / 2 - 2,
            top - fm.height() + 2,
            text_w + 4,
            fm.height(),
        )
        painter.setBrush(
            QBrush(QColor(204, 255, 204, 200))
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 3, 3)
        # 标签文字
        painter.setPen(QPen(self._OPTIMAL_COLOR))
        painter.drawText(
            bg_rect,
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def _draw_legend(
        self, painter: QPainter, width: int, height: int
    ) -> None:
        """绘制右上角图例（吞吐量 / p95时延）。"""
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        items = [
            ("吞吐量", self._THROUGHPUT_COLOR),
            ("p95时延", self._LATENCY_COLOR),
        ]

        # 计算图例尺寸
        max_text_w = max(fm.horizontalAdvance(text) for text, _ in items)
        box_w = (
            _LEGEND_PADDING * 2
            + _LEGEND_LINE_LEN
            + 4
            + max_text_w
        )
        box_h = (
            _LEGEND_PADDING * 2 + len(items) * _LEGEND_ROW_HEIGHT
        )

        # 右上角定位（图表区内）
        right = width - MARGIN_RIGHT
        box_x = right - box_w - 4
        box_y = MARGIN_TOP + 4
        box_rect = QRectF(box_x, box_y, box_w, box_h)

        # 半透明白色背景
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.setPen(QPen(self._AXIS_COLOR, 1))
        painter.drawRoundedRect(box_rect, 3, 3)

        # 各图例项
        for i, (text, color) in enumerate(items):
            row_y = box_y + _LEGEND_PADDING + i * _LEGEND_ROW_HEIGHT
            # 颜色样本线
            line_pen = QPen(color, 2)
            painter.setPen(line_pen)
            line_y = row_y + _LEGEND_ROW_HEIGHT / 2
            painter.drawLine(
                QPointF(box_x + _LEGEND_PADDING, line_y),
                QPointF(
                    box_x + _LEGEND_PADDING + _LEGEND_LINE_LEN, line_y
                ),
            )
            # 圆点
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, 1))
            mid_x = box_x + _LEGEND_PADDING + _LEGEND_LINE_LEN / 2
            painter.drawEllipse(
                QPointF(mid_x, line_y), 3, 3
            )
            # 文字
            painter.setPen(QPen(self._TEXT_COLOR))
            painter.drawText(
                QRectF(
                    box_x + _LEGEND_PADDING + _LEGEND_LINE_LEN + 4,
                    row_y,
                    max_text_w,
                    _LEGEND_ROW_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )

    # ------------------------------------------------------------------
    # 鼠标悬停
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """鼠标悬停检测：靠近数据点时显示 QToolTip。"""
        pos = event.position().toPoint()
        cursor = QPointF(pos)
        for p in self._points:
            # 检查吞吐量点
            if (p.throughput_pos - cursor).manhattanLength() < _HIT_RADIUS:
                text = (
                    f"并发数: {p.concurrency}\n"
                    f"吞吐量: {p.throughput:.2f} tasks/s\n"
                    f"p95: {p.p95_latency:.1f} ms\n"
                    f"成功率: {p.success_rate:.1%}"
                )
                QToolTip.showText(
                    event.globalPosition().toPoint(), text, self
                )
                return
            # 检查 p95 点
            if (p.p95_pos - cursor).manhattanLength() < _HIT_RADIUS:
                text = (
                    f"并发数: {p.concurrency}\n"
                    f"吞吐量: {p.throughput:.2f} tasks/s\n"
                    f"p95: {p.p95_latency:.1f} ms\n"
                    f"成功率: {p.success_rate:.1%}"
                )
                QToolTip.showText(
                    event.globalPosition().toPoint(), text, self
                )
                return
        QToolTip.hideText()


__all__ = ["BenchmarkChart"]
