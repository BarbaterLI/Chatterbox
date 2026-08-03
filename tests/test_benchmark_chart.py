"""BenchmarkChart 单元测试。

验证并发基准测试图表控件（QPainter 自绘双 Y 轴折线图）：
- ``set_data`` 更新内部 ``_points`` 与 ``_optimal_concurrency``
- ``paintEvent`` 在有/无数据时不抛异常
- ``clear`` 重置内部状态
- ``minimumSizeHint`` 返回预期尺寸
- paintEvent 后数据点屏幕坐标被正确计算（供 mouseMoveEvent 命中检测）

测试在 offscreen Qt 平台下运行，无需真实显示设备。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.concurrency_benchmark import BenchmarkResult
from balcon_batch_tts.gui.widgets.benchmark_chart import BenchmarkChart


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """返回全局 QApplication 单例（offscreen 模式）。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 辅助：构造测试数据
# ---------------------------------------------------------------------------
def _make_results() -> list[BenchmarkResult]:
    """返回 3 个并发级别的 BenchmarkResult 测试数据。"""
    return [
        BenchmarkResult(
            concurrency=1,
            throughput=5.0,
            p95_latency=200.0,
            success_rate=1.0,
            total_time=4.0,
        ),
        BenchmarkResult(
            concurrency=2,
            throughput=10.0,
            p95_latency=150.0,
            success_rate=1.0,
            total_time=2.0,
        ),
        BenchmarkResult(
            concurrency=3,
            throughput=12.0,
            p95_latency=180.0,
            success_rate=0.95,
            total_time=1.67,
        ),
    ]


def _force_paint(
    chart: BenchmarkChart, qapp: QApplication
) -> None:
    """强制触发 paintEvent 执行。

    offscreen 平台下，未 ``show()`` 的 widget 调用 ``repaint()`` 可能跳过
    ``paintEvent``。此处先 ``show()`` 再直接调用 ``paintEvent``，确保
    绘制逻辑（含屏幕坐标计算）实际执行。
    """
    chart.show()
    qapp.processEvents()
    chart.paintEvent(QPaintEvent(QRect(0, 0, chart.width(), chart.height())))


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------
class TestBenchmarkChart:
    """BenchmarkChart 行为契约。"""

    def test_set_data_updates_internal_state(
        self, qapp: QApplication
    ) -> None:
        """set_data 传入 3 个结果后 _points 长度为 3，_optimal_concurrency 与传入值一致。"""
        chart = BenchmarkChart()
        chart.set_data(_make_results(), optimal_concurrency=2)

        assert len(chart._points) == 3
        assert chart._optimal_concurrency == 2
        # 验证 _points 字段从 BenchmarkResult 正确映射
        assert chart._points[0].concurrency == 1
        assert chart._points[0].throughput == 5.0
        assert chart._points[1].p95_latency == 150.0
        assert chart._points[2].success_rate == 0.95

    def test_chart_paints_without_error(
        self, qapp: QApplication
    ) -> None:
        """set_data 后触发 paintEvent 不抛异常。"""
        chart = BenchmarkChart()
        chart.resize(600, 400)
        chart.set_data(_make_results(), optimal_concurrency=2)
        chart.update()
        qapp.processEvents()
        _force_paint(chart, qapp)

    def test_optimal_concurrency_marker(
        self, qapp: QApplication
    ) -> None:
        """set_data(optimal_concurrency=2) + paintEvent 后 _optimal_concurrency == 2。"""
        chart = BenchmarkChart()
        chart.resize(600, 400)
        chart.set_data(_make_results(), optimal_concurrency=2)
        _force_paint(chart, qapp)
        # paintEvent 内部使用 _optimal_concurrency 绘制绿色竖线
        assert chart._optimal_concurrency == 2

    def test_tooltip_on_hover(
        self, qapp: QApplication
    ) -> None:
        """set_data + paintEvent 后数据点屏幕坐标被正确计算（非默认 QPointF(0,0)）。

        paintEvent 内部更新 ``_points[i].throughput_pos`` / ``p95_pos``，
        供 ``mouseMoveEvent`` 命中检测使用。验证这些坐标为有效值即间接验证
        悬停 tooltip 路径可用。
        """
        chart = BenchmarkChart()
        chart.resize(600, 400)
        chart.set_data(_make_results(), optimal_concurrency=2)
        _force_paint(chart, qapp)

        tp = chart._points[0].throughput_pos
        lp = chart._points[0].p95_pos
        # 坐标应为有效值（x > 0, y > 0），间接验证 mouseMoveEvent 命中检测可用
        assert tp.x() > 0
        assert tp.y() > 0
        assert lp.x() > 0
        assert lp.y() > 0

        # 构造鼠标移动事件到吞吐量点附近，调用 mouseMoveEvent 不抛异常
        # （命中数据点将触发 QToolTip.showText）
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(tp.x(), tp.y()),
            QPointF(tp.x(), tp.y()),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        chart.mouseMoveEvent(event)

    def test_clear_resets_state(
        self, qapp: QApplication
    ) -> None:
        """set_data 后 clear：_points 为空，_optimal_concurrency == 0。"""
        chart = BenchmarkChart()
        chart.set_data(_make_results(), optimal_concurrency=2)
        assert len(chart._points) == 3

        chart.clear()

        assert chart._points == []
        assert chart._optimal_concurrency == 0

    def test_minimum_size_hint(
        self, qapp: QApplication
    ) -> None:
        """minimumSizeHint() == QSize(400, 300)。"""
        chart = BenchmarkChart()
        assert chart.minimumSizeHint() == QSize(400, 300)

    def test_empty_data_paints_without_error(
        self, qapp: QApplication
    ) -> None:
        """未 set_data（空状态）触发 paintEvent 不抛异常（应绘制"无数据"状态）。"""
        chart = BenchmarkChart()
        chart.resize(600, 400)
        # 不调用 set_data，直接触发 paintEvent（初始空状态）
        _force_paint(chart, qapp)

        # 另验证 set_data([], 0) 同样不抛异常
        chart.set_data([], 0)
        _force_paint(chart, qapp)
        assert chart._points == []
        assert chart._optimal_concurrency == 0
