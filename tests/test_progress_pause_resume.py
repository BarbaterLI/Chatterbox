"""ProgressWidget 暂停/恢复与日志过滤的端到端信号连接测试。

Task T-C3 验证 ``ProgressWidget`` 的 ``pause_requested`` 与
``filter_requested`` 信号可被外部控制器（主窗口角色）正确接线，无需依赖
真实 :class:`MainWindow`。使用一个轻量 ``_FakeScheduler``（实现
``set_paused`` / ``is_paused``，与 T-C1 的 :class:`TaskScheduler` 接口一致）
与一个过滤处理器，模拟主窗口的连接逻辑，覆盖：

- 暂停按钮点击 → ``pause_requested(True)`` → 调度器 ``set_paused(True)``
- 恢复按钮点击 → ``pause_requested(False)`` → 调度器 ``set_paused(False)``
- 成功计数点击 → ``filter_requested("success")`` → 过滤处理器
- 失败计数点击 → ``filter_requested("error")`` → 过滤处理器
- 信号签名与控件状态一致性
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from balcon_batch_tts.gui.widgets.progress_widget import (
    ProgressWidget,
    _ClickableLabel,
)


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeScheduler:
    """轻量调度器替身，实现 T-C1 的 ``set_paused`` / ``is_paused`` 接口。

    用于模拟主窗口将 ``pause_requested`` 信号连接到 ``TaskScheduler`` 的
    端到端逻辑，避免引入真实调度器的线程与依赖。
    """

    def __init__(self) -> None:
        self._paused: bool = False
        # 记录 set_paused 调用历史，便于断言
        self.pause_calls: list[bool] = []

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.pause_calls.append(paused)

    def is_paused(self) -> bool:
        return self._paused


class _FilterController:
    """模拟主窗口的日志过滤处理器。

    记录 ``filter_requested`` 信号传入的过滤类型，主窗口实际会据此切换
    LogPanel 的级别过滤。
    """

    def __init__(self) -> None:
        self.current_filter: str | None = None
        self.filter_calls: list[str] = []

    def set_filter(self, kind: str) -> None:
        self.current_filter = kind
        self.filter_calls.append(kind)


# ---------------------------------------------------------------------------
# 连接辅助：模拟 MainWindow 的信号接线
# ---------------------------------------------------------------------------
def _wire_widget(widget: ProgressWidget, scheduler: _FakeScheduler,
                 filter_ctrl: _FilterController) -> None:
    """模拟 MainWindow 构造时的信号连接逻辑。

    - ``pause_requested`` → ``scheduler.set_paused``
    - ``filter_requested`` → ``filter_ctrl.set_filter``
    """
    widget.pause_requested.connect(scheduler.set_paused)
    widget.filter_requested.connect(filter_ctrl.set_filter)


# ---------------------------------------------------------------------------
# 控件类型与信号存在性
# ---------------------------------------------------------------------------
class TestWidgetExposesSignalsAndControls:
    """验证 ProgressWidget 暴露所需的信号与控件。"""

    def test_pause_button_is_qpushbutton(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        assert isinstance(widget.pause_button, QPushButton)

    def test_success_failed_labels_are_clickable(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        assert isinstance(widget.success_label, _ClickableLabel)
        assert isinstance(widget.failed_label, _ClickableLabel)

    def test_signals_exist(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        # 信号属性存在且可连接（Signal 描述符返回 SignalInstance）
        assert hasattr(widget, "pause_requested")
        assert hasattr(widget, "filter_requested")
        # 可连接即证明签名合法
        widget.pause_requested.connect(lambda _: None)
        widget.filter_requested.connect(lambda _: None)


# ---------------------------------------------------------------------------
# 端到端：暂停/恢复按钮 → 调度器
# ---------------------------------------------------------------------------
class TestPauseResumeEndToEnd:
    """验证暂停/恢复按钮经信号驱动调度器的完整链路。"""

    def test_pause_click_pauses_scheduler(self, qapp: QApplication) -> None:
        """运行中点击暂停：调度器进入暂停状态，按钮文本变为「恢复」。"""
        widget = ProgressWidget()
        scheduler = _FakeScheduler()
        filter_ctrl = _FilterController()
        _wire_widget(widget, scheduler, filter_ctrl)

        widget.set_state("running")
        widget.pause_button.click()

        assert scheduler.is_paused() is True
        assert scheduler.pause_calls == [True]
        assert widget.pause_button.text() == "恢复"
        # 暂停状态进度条文案含前缀
        widget.progress_bar.setValue(40)
        assert "（已暂停）" in widget.progress_bar.text()

    def test_resume_click_resumes_scheduler(self, qapp: QApplication) -> None:
        """已暂停时点击恢复：调度器退出暂停状态，按钮文本变为「暂停」。"""
        widget = ProgressWidget()
        scheduler = _FakeScheduler()
        _wire_widget(widget, scheduler, _FilterController())

        widget.set_state("running")
        widget.pause_button.click()  # 暂停
        widget.pause_button.click()  # 恢复

        assert scheduler.is_paused() is False
        assert scheduler.pause_calls == [True, False]
        assert widget.pause_button.text() == "暂停"
        # 恢复后进度条文案不再含暂停前缀
        assert "（已暂停）" not in widget.progress_bar.text()

    def test_pause_button_disabled_outside_running(
        self, qapp: QApplication
    ) -> None:
        """非运行状态暂停按钮禁用，点击不触发调度器调用。"""
        widget = ProgressWidget()
        scheduler = _FakeScheduler()
        _wire_widget(widget, scheduler, _FilterController())

        # idle 状态：按钮禁用
        assert not widget.pause_button.isEnabled()
        # 禁用按钮的 click() 不发射 clicked（Qt 行为），调度器不应被调用
        widget.pause_button.click()
        assert scheduler.pause_calls == []

        # 进入 running 后再离开：暂停状态应被重置
        widget.set_state("running")
        widget.pause_button.click()
        assert scheduler.is_paused() is True
        widget.set_state("success")
        # 离开 running 后内部暂停状态重置（按钮文本回到「暂停」）
        assert widget.pause_button.text() == "暂停"
        assert widget._is_paused is False
        # 按钮禁用
        assert not widget.pause_button.isEnabled()

    def test_pause_does_not_hold_scheduler_reference(
        self, qapp: QApplication
    ) -> None:
        """ProgressWidget 不直接持有调度器引用（通过信号解耦）。"""
        widget = ProgressWidget()
        # 不应存在 scheduler 相关属性
        assert not hasattr(widget, "_scheduler")
        assert not hasattr(widget, "scheduler")


# ---------------------------------------------------------------------------
# 端到端：可点击计数 → 日志过滤
# ---------------------------------------------------------------------------
class TestFilterClickEndToEnd:
    """验证成功/失败计数点击经信号驱动过滤处理器的完整链路。"""

    def test_click_success_filters_success(self, qapp: QApplication) -> None:
        """点击成功计数：过滤处理器收到 "success"。"""
        widget = ProgressWidget()
        filter_ctrl = _FilterController()
        _wire_widget(widget, _FakeScheduler(), filter_ctrl)

        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=4, failed=1)

        widget.success_label.clicked.emit()

        assert filter_ctrl.current_filter == "success"
        assert filter_ctrl.filter_calls == ["success"]

    def test_click_failed_filters_error(self, qapp: QApplication) -> None:
        """点击失败计数：过滤处理器收到 "error"。"""
        widget = ProgressWidget()
        filter_ctrl = _FilterController()
        _wire_widget(widget, _FakeScheduler(), filter_ctrl)

        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=4, failed=1)

        widget.failed_label.clicked.emit()

        assert filter_ctrl.current_filter == "error"
        assert filter_ctrl.filter_calls == ["error"]

    def test_alternate_clicks_toggle_filter(
        self, qapp: QApplication
    ) -> None:
        """交替点击成功/失败计数：过滤处理器依次收到 success/error。"""
        widget = ProgressWidget()
        filter_ctrl = _FilterController()
        _wire_widget(widget, _FakeScheduler(), filter_ctrl)

        widget.success_label.clicked.emit()
        widget.failed_label.clicked.emit()
        widget.success_label.clicked.emit()

        assert filter_ctrl.filter_calls == ["success", "error", "success"]
        assert filter_ctrl.current_filter == "success"


# ---------------------------------------------------------------------------
# 端到端：统计刷新
# ---------------------------------------------------------------------------
class TestStatsRefreshEndToEnd:
    """验证统计标签在任务运行中的刷新逻辑。"""

    def test_set_total_starts_stats_timer(self, qapp: QApplication) -> None:
        """set_total 后统计定时器应启动。"""
        widget = ProgressWidget()
        widget.set_total(10)
        assert widget._stats_timer.isActive()

    def test_reset_stops_stats_timer(self, qapp: QApplication) -> None:
        """reset 后统计定时器应停止。"""
        widget = ProgressWidget()
        widget.set_total(10)
        assert widget._stats_timer.isActive()
        widget.reset()
        assert not widget._stats_timer.isActive()

    def test_set_summary_stops_stats_timer(self, qapp: QApplication) -> None:
        """set_summary（任务完成）后统计定时器应停止。"""
        widget = ProgressWidget()
        widget.set_total(10)
        widget.set_state("running")
        widget.set_summary(succeeded=8, failed=2, elapsed=5.0)
        assert not widget._stats_timer.isActive()
