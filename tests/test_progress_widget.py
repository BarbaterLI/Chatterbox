"""ProgressWidget 单元测试。

验证 Task 11b 的 Qt6 原生动画集成：
- ``QGraphicsColorizeEffect`` 应用到 ``status_label``
- ``_failure_rate_to_color`` 失败率 → 颜色线性插值
- ``QVariantAnimation`` 颜色渐变动画（运行中根据失败率渐变）
- ``QPropertyAnimation`` + ``QSequentialAnimationGroup`` 闪烁动画（3 次脉冲）
- ``AnimationManager`` 集成（禁用动画时 duration=0）
- 状态切换时动画停止与重置
- ``set_total`` / ``update_progress`` / ``set_summary`` / ``reset`` 基础行为
"""
from __future__ import annotations

import os
import time

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import (
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsColorizeEffect,
    QLabel,
    QPushButton,
)

from balcon_batch_tts.gui.theme.design_tokens import DesignTokens
from balcon_batch_tts.gui.widgets.animation_manager import AnimationManager
from balcon_batch_tts.gui.widgets.progress_widget import (
    ProgressWidget,
    _ClickableLabel,
    _FLASH_PULSES,
)
# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# AnimationManager 单例隔离：每个测试前后重置，避免互相污染
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_animation_manager():
    """每个测试前后重置 AnimationManager 单例状态。"""
    AnimationManager.reset_instance()
    yield
    AnimationManager.reset_instance()


# ---------------------------------------------------------------------------
# QGraphicsColorizeEffect 应用
# ---------------------------------------------------------------------------
class TestColorizeEffectSetup:
    """验证 status_label 已应用 QGraphicsColorizeEffect。"""

    def test_status_label_has_colorize_effect(
        self, qapp: QApplication
    ) -> None:
        """``status_label`` 应通过 setGraphicsEffect 应用 QGraphicsColorizeEffect。"""
        widget = ProgressWidget()
        effect = widget.status_label.graphicsEffect()
        assert isinstance(effect, QGraphicsColorizeEffect), (
            "status_label 应有 QGraphicsColorizeEffect"
        )

    def test_initial_strength_is_zero(self, qapp: QApplication) -> None:
        """初始 strength 应为 0（不影响原图标显示）。"""
        widget = ProgressWidget()
        assert widget._color_effect.strength() == 0.0

    def test_color_effect_is_member(self, qapp: QApplication) -> None:
        """``_color_effect`` 应为 ProgressWidget 成员变量。"""
        widget = ProgressWidget()
        assert isinstance(widget._color_effect, QGraphicsColorizeEffect)


# ---------------------------------------------------------------------------
# 失败率 → 颜色线性插值
# ---------------------------------------------------------------------------
class TestFailureRateToColor:
    """验证 ``_failure_rate_to_color`` 静态方法的线性插值逻辑。"""

    def test_zero_failure_returns_green(self) -> None:
        """0% 失败率应返回绿色。"""
        color = ProgressWidget._failure_rate_to_color(0.0)
        assert color == DesignTokens.failure_rate_colors()[0][1]

    def test_high_failure_returns_red(self) -> None:
        """50%+ 失败率应返回红色。"""
        color = ProgressWidget._failure_rate_to_color(0.6)
        assert color == DesignTokens.failure_rate_colors()[-1][1]

    def test_critical_failure_returns_red(self) -> None:
        """100% 失败率应返回红色。"""
        color = ProgressWidget._failure_rate_to_color(1.0)
        assert color == DesignTokens.failure_rate_colors()[-1][1]

    def test_first_breakpoint_returns_yellow(self) -> None:
        """15% 失败率（第一个关键点）应返回黄色。"""
        color = ProgressWidget._failure_rate_to_color(0.15)
        assert color == DesignTokens.failure_rate_colors()[1][1]

    def test_second_breakpoint_returns_orange(self) -> None:
        """30% 失败率（第二个关键点）应返回橙色。"""
        color = ProgressWidget._failure_rate_to_color(0.30)
        assert color == DesignTokens.failure_rate_colors()[2][1]

    def test_interpolated_color_between_green_and_yellow(self) -> None:
        """7.5% 失败率应在绿色与黄色之间插值。"""
        color = ProgressWidget._failure_rate_to_color(0.075)
        green = DesignTokens.failure_rate_colors()[0][1]
        yellow = DesignTokens.failure_rate_colors()[1][1]
        # 颜色应介于绿与黄之间（每个分量都介于两者之间）
        assert min(green.red(), yellow.red()) <= color.red() <= max(green.red(), yellow.red())
        assert min(green.green(), yellow.green()) <= color.green() <= max(green.green(), yellow.green())

    def test_negative_rate_clamped_to_zero(self) -> None:
        """负失败率应被夹紧为 0，返回绿色。"""
        color = ProgressWidget._failure_rate_to_color(-0.5)
        assert color == DesignTokens.failure_rate_colors()[0][1]

    def test_rate_above_one_clamped_to_one(self) -> None:
        """超过 1 的失败率应被夹紧为 1，返回红色。"""
        color = ProgressWidget._failure_rate_to_color(2.0)
        assert color == DesignTokens.failure_rate_colors()[-1][1]


# ---------------------------------------------------------------------------
# QVariantAnimation 颜色渐变动画
# ---------------------------------------------------------------------------
class TestFailureRateColorAnimation:
    """验证 running 状态下失败率颜色渐变动画。"""

    def test_running_state_triggers_color_animation(
        self, qapp: QApplication
    ) -> None:
        """``running`` 状态下 ``update_progress`` 应触发颜色动画。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)

        # 应有动画引用
        assert widget._failure_rate_anim is not None
        assert isinstance(widget._failure_rate_anim, QVariantAnimation)

    def test_idle_state_no_color_animation(
        self, qapp: QApplication
    ) -> None:
        """非 running 状态下 ``update_progress`` 不应触发颜色动画。"""
        widget = ProgressWidget()
        widget.set_state("idle")
        widget.update_progress(5, 10, succeeded=3, failed=2)
        assert widget._failure_rate_anim is None

    def test_color_animation_uses_animation_manager(
        self, qapp: QApplication
    ) -> None:
        """禁用动画时，颜色动画 duration 应为 0。"""
        anim_mgr = AnimationManager.instance()
        anim_mgr.set_enabled(False)

        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)

        assert widget._failure_rate_anim is not None
        assert widget._failure_rate_anim.duration() == 0

    def test_color_animation_increases_strength(
        self, qapp: QApplication
    ) -> None:
        """触发颜色动画后 strength 应为 1.0（让颜色叠加可见）。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)
        assert widget._color_effect.strength() == 1.0

    def test_same_failure_rate_skips_animation(
        self, qapp: QApplication
    ) -> None:
        """相同失败率（颜色未变）应跳过动画创建。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(0, 10, succeeded=0, failed=0)
        # 0 失败率，与初始 _current_failure_color（绿色）相同，应跳过
        assert widget._failure_rate_anim is None

    def test_state_change_stops_color_animation(
        self, qapp: QApplication
    ) -> None:
        """``set_state`` 切换状态应停止进行中的颜色动画。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)
        assert widget._failure_rate_anim is not None

        # 切换到 idle 应停止动画
        widget.set_state("idle")
        assert widget._failure_rate_anim is None

    def test_reset_stops_color_animation(
        self, qapp: QApplication
    ) -> None:
        """``reset`` 应停止进行中的颜色动画。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)
        widget.reset()
        assert widget._failure_rate_anim is None
        assert widget._color_effect.strength() == 0.0


# ---------------------------------------------------------------------------
# QPropertyAnimation + QSequentialAnimationGroup 闪烁动画
# ---------------------------------------------------------------------------
class TestCompletionFlashAnimation:
    """验证任务完成闪烁动画（3 次脉冲）。"""

    def test_set_summary_triggers_flash(
        self, qapp: QApplication
    ) -> None:
        """``set_summary`` 应触发闪烁动画组。"""
        widget = ProgressWidget()
        widget.set_summary(succeeded=8, failed=2, elapsed=5.0)
        assert widget._flash_anim_group is not None
        assert isinstance(widget._flash_anim_group, QSequentialAnimationGroup)

    def test_flash_completion_method_triggers_flash(
        self, qapp: QApplication
    ) -> None:
        """``flash_completion`` 方法应触发闪烁动画组。"""
        widget = ProgressWidget()
        widget.flash_completion()
        assert widget._flash_anim_group is not None

    def test_flash_animation_has_6_sub_animations(
        self, qapp: QApplication
    ) -> None:
        """3 次脉冲 × (上升 + 下降) = 6 个 QPropertyAnimation 子动画。"""
        widget = ProgressWidget()
        widget.flash_completion()
        group = widget._flash_anim_group
        assert group.animationCount() == _FLASH_PULSES * 2
        for i in range(group.animationCount()):
            anim = group.animationAt(i)
            assert isinstance(anim, QPropertyAnimation)

    def test_flash_stops_failure_rate_animation(
        self, qapp: QApplication
    ) -> None:
        """闪烁动画触发时应停止进行中的颜色动画。"""
        widget = ProgressWidget()
        widget.set_state("running")
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)
        assert widget._failure_rate_anim is not None

        widget.flash_completion()
        assert widget._failure_rate_anim is None

    def test_flash_uses_animation_manager(
        self, qapp: QApplication
    ) -> None:
        """禁用动画时，闪烁子动画 duration 应为 0。"""
        anim_mgr = AnimationManager.instance()
        anim_mgr.set_enabled(False)

        widget = ProgressWidget()
        widget.flash_completion()
        group = widget._flash_anim_group
        assert group is not None
        for i in range(group.animationCount()):
            anim = group.animationAt(i)
            assert anim.duration() == 0

    def test_state_change_stops_flash(
        self, qapp: QApplication
    ) -> None:
        """``set_state`` 切换状态应停止进行中的闪烁动画。"""
        widget = ProgressWidget()
        widget.set_summary(succeeded=8, failed=2, elapsed=5.0)
        assert widget._flash_anim_group is not None

        widget.set_state("idle")
        assert widget._flash_anim_group is None

    def test_reset_stops_flash(self, qapp: QApplication) -> None:
        """``reset`` 应停止进行中的闪烁动画。"""
        widget = ProgressWidget()
        widget.set_summary(succeeded=8, failed=2, elapsed=5.0)
        widget.reset()
        assert widget._flash_anim_group is None
        assert widget._color_effect.strength() == 0.0


# ---------------------------------------------------------------------------
# 基础行为（确保动画集成不破坏原有功能）
# ---------------------------------------------------------------------------
class TestBasicBehavior:
    """验证 ProgressWidget 基础行为在动画集成后仍正确。"""

    def test_initial_state_is_idle(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        assert widget._state == "idle"

    def test_set_total_resets_counts(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        widget.set_total(10)
        assert widget._total == 10
        assert widget._completed == 0
        assert widget._succeeded == 0
        assert widget._failed == 0
        assert "0 / 10" in widget.count_label.text()

    def test_update_progress_updates_counts(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        widget.set_state("idle")  # 避免 running 触发颜色动画
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=4, failed=1)
        assert widget._completed == 5
        assert widget._succeeded == 4
        assert widget._failed == 1
        assert "5 / 10" in widget.count_label.text()
        assert widget.success_label.text() == "成功 4"
        assert widget.failed_label.text() == "失败 1"

    def test_reset_clears_all(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        widget.set_total(10)
        widget.update_progress(5, 10, succeeded=3, failed=2)
        widget.reset()
        assert widget._total == 0
        assert widget._completed == 0
        assert widget._succeeded == 0
        assert widget._failed == 0
        assert widget._state == "idle"

    def test_set_summary_shows_summary(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        widget.set_summary(succeeded=8, failed=2, elapsed=5.5)
        assert "10 / 10" in widget.count_label.text()
        assert widget.success_label.text() == "成功 8"
        assert widget.failed_label.text() == "失败 2"
        assert "耗时: 5.50" in widget.concurrency_label.text()

    def test_set_concurrency_updates_label(
        self, qapp: QApplication
    ) -> None:
        widget = ProgressWidget()
        widget.set_concurrency(3, 5)
        assert widget.concurrency_label.text() == "并发: 3 / 5"

    def test_status_label_is_qlabel(self, qapp: QApplication) -> None:
        widget = ProgressWidget()
        assert isinstance(widget.status_label, QLabel)


# ---------------------------------------------------------------------------
# Task T-C3：暂停/恢复按钮与统计扩展
# ---------------------------------------------------------------------------
class TestPauseResumeAndStats:
    """验证 Task T-C3 的暂停/恢复按钮、统计标签与可点击计数。"""

    def test_pause_button_exists_disabled_when_idle(
        self, qapp: QApplication
    ) -> None:
        """暂停按钮应为 QPushButton，非运行状态禁用。"""
        widget = ProgressWidget()
        assert isinstance(widget.pause_button, QPushButton)
        assert not widget.pause_button.isEnabled()
        assert widget.pause_button.text() == "暂停"

    def test_click_pause_when_running_emits_pause_true(
        self, qapp: QApplication
    ) -> None:
        """运行状态点击暂停按钮：发射 pause_requested(True)，按钮文本变为「恢复」。"""
        widget = ProgressWidget()
        received: list[bool] = []
        widget.pause_requested.connect(lambda p: received.append(p))

        widget.set_state("running")
        assert widget.pause_button.isEnabled()

        widget.pause_button.click()

        assert received == [True]
        assert widget.pause_button.text() == "恢复"
        assert widget._is_paused is True

    def test_click_resume_emits_pause_false(
        self, qapp: QApplication
    ) -> None:
        """已暂停时再次点击：发射 pause_requested(False)，按钮文本变为「暂停」。"""
        widget = ProgressWidget()
        received: list[bool] = []
        widget.pause_requested.connect(lambda p: received.append(p))

        widget.set_state("running")
        widget.pause_button.click()  # 暂停
        widget.pause_button.click()  # 恢复

        assert received == [True, False]
        assert widget.pause_button.text() == "暂停"
        assert widget._is_paused is False

    def test_rate_and_avg_labels_exist(self, qapp: QApplication) -> None:
        """速率与平均耗时标签应存在且初始为占位符。"""
        widget = ProgressWidget()
        assert isinstance(widget.rate_label, QLabel)
        assert isinstance(widget.avg_time_label, QLabel)
        assert "--" in widget.rate_label.text()
        assert "--" in widget.avg_time_label.text()
        # 统计定时器为 QTimer，1s 间隔
        assert isinstance(widget._stats_timer, QTimer)
        assert widget._stats_timer.interval() == 1000

    def test_rate_positive_when_running(self, qapp: QApplication) -> None:
        """运行中速率 > 0（mock _start_time 与 _completed）。"""
        widget = ProgressWidget()
        # 模拟任务已运行 10 秒、完成 5 项
        widget._start_time = time.time() - 10.0
        widget._completed = 5

        widget._refresh_stats()

        rate_text = widget.rate_label.text()
        avg_text = widget.avg_time_label.text()
        assert "--" not in rate_text
        assert "files/s" in rate_text
        assert "--" not in avg_text
        assert "s/项" in avg_text
        # 速率数值应 > 0
        rate_value = float(rate_text.replace("速率: ", "").split()[0])
        assert rate_value > 0

    def test_rate_placeholder_when_no_completed(
        self, qapp: QApplication
    ) -> None:
        """已完成数为 0 时显示「--」。"""
        widget = ProgressWidget()
        widget._start_time = time.time() - 5.0
        widget._completed = 0

        widget._refresh_stats()

        assert widget.rate_label.text() == "速率: --"
        assert widget.avg_time_label.text() == "平均: --"

    def test_click_success_label_emits_filter_success(
        self, qapp: QApplication
    ) -> None:
        """点击成功计数发射 filter_requested("success")。"""
        widget = ProgressWidget()
        assert isinstance(widget.success_label, _ClickableLabel)
        received: list[str] = []
        widget.filter_requested.connect(lambda s: received.append(s))

        widget.success_label.clicked.emit()

        assert received == ["success"]

    def test_click_failed_label_emits_filter_error(
        self, qapp: QApplication
    ) -> None:
        """点击失败计数发射 filter_requested("error")。"""
        widget = ProgressWidget()
        assert isinstance(widget.failed_label, _ClickableLabel)
        received: list[str] = []
        widget.filter_requested.connect(lambda s: received.append(s))

        widget.failed_label.clicked.emit()

        assert received == ["error"]

    def test_paused_progress_text_has_prefix(self, qapp: QApplication) -> None:
        """暂停状态进度条文案含「（已暂停）」。"""
        widget = ProgressWidget()
        widget.progress_bar.setValue(50)

        widget._set_paused(True)

        assert "（已暂停）" in widget.progress_bar.text()

        # 恢复后前缀消失
        widget._set_paused(False)
        assert "（已暂停）" not in widget.progress_bar.text()
