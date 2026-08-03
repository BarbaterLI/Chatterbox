"""log_panel 模块单元测试。

验证 ``LogPanel`` 的核心行为，包括：
- 日志追加与显示
- 级别过滤与搜索过滤
- 自动滚动开关
- 清空日志与保存日志
- Task 11f：最近日志横幅 ``QPropertyAnimation`` 展开动画

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QCoreApplication,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QPlainTextEdit,
)

import pytest

from balcon_batch_tts.gui.widgets.animation_manager import AnimationManager
from balcon_batch_tts.gui.widgets.log_panel import (
    _BANNER_COLLAPSE_MS,
    _BANNER_EXPAND_MS,
    _BANNER_HEIGHT,
    _BANNER_HOLD_MS,
    _BANNER_MAX_CHARS,
    _FILTER_ALL,
    _FILTER_ERRORS,
    _FILTER_WARN_PLUS,
    _MAX_BLOCK_COUNT,
    LogPanel,
)
from balcon_batch_tts.utils.signals import LogSignals


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


@pytest.fixture(autouse=True)
def disconnect_log_signals():
    """每个测试前后清理 LogSignals 单例的信号连接。

    避免上一个测试的 LogPanel 实例残留连接干扰当前测试。
    使用 warnings 过滤器抑制 libpyside 在无连接时 disconnect 的 RuntimeWarning。
    """
    import warnings

    signals = LogSignals.get_instance()
    yield
    # 测试后清理：断开所有连接到 log_message 的槽
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        try:
            signals.log_message.disconnect()
        except (RuntimeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# 基础初始化
# ---------------------------------------------------------------------------
class TestLogPanelInit:
    """``LogPanel`` 初始化契约。"""

    def test_text_edit_is_readonly(self, qapp: QApplication) -> None:
        panel = LogPanel()
        assert panel.text_edit.isReadOnly()

    def test_text_edit_max_block_count(self, qapp: QApplication) -> None:
        panel = LogPanel()
        assert panel.text_edit.maximumBlockCount() == _MAX_BLOCK_COUNT

    def test_default_filter_is_all(self, qapp: QApplication) -> None:
        panel = LogPanel()
        assert panel.level_filter.currentText() == _FILTER_ALL

    def test_auto_scroll_default_checked(self, qapp: QApplication) -> None:
        panel = LogPanel()
        assert panel.auto_scroll_check.isChecked()

    def test_filter_options_count(self, qapp: QApplication) -> None:
        panel = LogPanel()
        assert panel.level_filter.count() == 3
        texts = [
            panel.level_filter.itemText(i) for i in range(panel.level_filter.count())
        ]
        assert _FILTER_ALL in texts
        assert _FILTER_ERRORS in texts
        assert _FILTER_WARN_PLUS in texts


# ---------------------------------------------------------------------------
# 日志追加与显示
# ---------------------------------------------------------------------------
class TestAppendLog:
    """``_append_log`` 与 ``append`` 行为。"""

    def test_append_adds_to_raw_logs(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[2026-01-01 12:00:00] [INFO] test: hello")
        assert len(panel._raw_logs) == 1
        assert "hello" in panel._raw_logs[0]

    def test_append_displays_in_text_edit(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[2026-01-01 12:00:00] [INFO] test: hello world")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        text = panel.text_edit.toPlainText()
        assert "hello world" in text

    def test_append_multiple_lines(self, qapp: QApplication) -> None:
        panel = LogPanel()
        for i in range(5):
            panel.append(f"[INFO] line {i}")
        assert len(panel._raw_logs) == 5

    def test_append_truncates_raw_logs_beyond_max(
        self, qapp: QApplication
    ) -> None:
        panel = LogPanel()
        # 添加超过 _MAX_BLOCK_COUNT 条日志
        for i in range(_MAX_BLOCK_COUNT + 100):
            panel.append(f"[INFO] line {i}")
        # 应被截断到约 80% 的 _MAX_BLOCK_COUNT
        assert len(panel._raw_logs) <= _MAX_BLOCK_COUNT


# ---------------------------------------------------------------------------
# 级别过滤
# ---------------------------------------------------------------------------
class TestLevelFilter:
    """级别过滤下拉行为。"""

    def test_detect_level_info(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("[INFO] message") == "INFO"

    def test_detect_level_warning(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("[WARNING] message") == "WARNING"

    def test_detect_level_error(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("[ERROR] message") == "ERROR"

    def test_detect_level_critical(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("[CRITICAL] message") == "CRITICAL"

    def test_detect_level_debug(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("[DEBUG] message") == "DEBUG"

    def test_detect_level_no_level(self, qapp: QApplication) -> None:
        assert LogPanel._detect_level("plain message") == ""

    def test_filter_all_shows_all_levels(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_ALL)
        panel.append("[INFO] info message")
        panel.append("[ERROR] error message")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        text = panel.text_edit.toPlainText()
        assert "info message" in text
        assert "error message" in text

    def test_filter_errors_only(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_ERRORS)
        panel.append("[INFO] info message")
        panel.append("[ERROR] error message")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        text = panel.text_edit.toPlainText()
        assert "error message" in text
        assert "info message" not in text

    def test_filter_warn_plus(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_WARN_PLUS)
        panel.append("[INFO] info message")
        panel.append("[WARNING] warn message")
        panel.append("[ERROR] error message")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        text = panel.text_edit.toPlainText()
        assert "warn message" in text
        assert "error message" in text
        assert "info message" not in text


# ---------------------------------------------------------------------------
# 搜索过滤
# ---------------------------------------------------------------------------
class TestSearchFilter:
    """搜索框过滤行为。"""

    def test_search_filters_by_keyword(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[INFO] apple message")
        panel.append("[INFO] banana message")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        panel.search_box.setText("banana")
        # 等待 rerender（同步调用）
        text = panel.text_edit.toPlainText()
        assert "banana" in text
        assert "apple" not in text

    def test_search_case_insensitive(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[INFO] SomeMessage")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        panel.search_box.setText("somemessage")
        text = panel.text_edit.toPlainText()
        assert "SomeMessage" in text

    def test_search_empty_shows_all(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[INFO] apple")
        panel.append("[INFO] banana")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        panel.search_box.setText("")
        text = panel.text_edit.toPlainText()
        assert "apple" in text
        assert "banana" in text


# ---------------------------------------------------------------------------
# 清空与保存
# ---------------------------------------------------------------------------
class TestClearAndSave:
    """``clear_log`` 与 ``save_log`` 行为。"""

    def test_clear_empties_text_edit(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[INFO] hello")
        panel.clear_log()
        assert panel.text_edit.toPlainText() == ""

    def test_clear_empties_raw_logs(self, qapp: QApplication) -> None:
        panel = LogPanel()
        panel.append("[INFO] hello")
        panel.clear_log()
        assert len(panel._raw_logs) == 0


# ---------------------------------------------------------------------------
# Task 11f：最近日志横幅 QPropertyAnimation 展开动画
# ---------------------------------------------------------------------------
class TestRecentBannerAnimation:
    """Task 11f：最近日志横幅展开动画契约。

    验证：
    - 横幅 widget 存在且初始 maximumHeight=0
    - 横幅使用 QFrame.Shape.StyledPanel 原生外观
    - ``_show_recent_banner`` 创建 QSequentialAnimationGroup
    - 动画组包含三段：展开 → 暂停 → 收回
    - 展开动画目标属性为 ``maximumHeight``，起止值 0 → _BANNER_HEIGHT
    - 收回动画起止值 _BANNER_HEIGHT → 0
    - 动画进行中再次调用仅更新文本，不重启动画
    - 禁用动画时跳过横幅显示
    - 日志通过过滤时触发横幅
    - 日志被过滤时不触发横幅
    - 清空日志时停止横幅动画并重置
    - 过长文本被截断到 _BANNER_MAX_CHARS + 省略号
    """

    def test_banner_widget_exists(self, qapp: QApplication) -> None:
        """横幅 QLabel 应在初始化时创建。"""
        panel = LogPanel()
        assert isinstance(panel._recent_banner, QLabel)

    def test_banner_initial_max_height_is_zero(
        self, qapp: QApplication
    ) -> None:
        """横幅初始 maximumHeight 应为 0（不可见）。"""
        panel = LogPanel()
        assert panel._recent_banner.maximumHeight() == 0

    def test_banner_uses_styled_panel_frame(
        self, qapp: QApplication
    ) -> None:
        """横幅应使用 QFrame.Shape.StyledPanel 原生外观。"""
        panel = LogPanel()
        assert panel._recent_banner.frameShape() == QFrame.Shape.StyledPanel

    def test_banner_anim_group_initially_none(
        self, qapp: QApplication
    ) -> None:
        """动画组引用初始应为 None。"""
        panel = LogPanel()
        assert panel._banner_anim_group is None

    def test_show_recent_banner_creates_anim_group(
        self, qapp: QApplication
    ) -> None:
        """``_show_recent_banner`` 应创建 QSequentialAnimationGroup。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        assert panel._banner_anim_group is not None
        assert isinstance(panel._banner_anim_group, QSequentialAnimationGroup)

    def test_anim_group_contains_three_animations(
        self, qapp: QApplication
    ) -> None:
        """动画组应包含三段：展开 → 暂停 → 收回。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        # QSequentialAnimationGroup.animationCount 返回子动画数
        assert panel._banner_anim_group.animationCount() == 3

    def test_expand_animation_targets_maximum_height(
        self, qapp: QApplication
    ) -> None:
        """展开动画目标属性应为 ``maximumHeight``。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        expand_anim = panel._banner_anim_group.animationAt(0)
        assert isinstance(expand_anim, QPropertyAnimation)
        assert expand_anim.propertyName() == b"maximumHeight"

    def test_expand_animation_start_and_end_values(
        self, qapp: QApplication
    ) -> None:
        """展开动画起始值 0，结束值 _BANNER_HEIGHT。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        expand_anim = panel._banner_anim_group.animationAt(0)
        assert expand_anim.startValue() == 0
        assert expand_anim.endValue() == _BANNER_HEIGHT

    def test_collapse_animation_start_and_end_values(
        self, qapp: QApplication
    ) -> None:
        """收回动画起始值 _BANNER_HEIGHT，结束值 0。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        collapse_anim = panel._banner_anim_group.animationAt(2)
        assert collapse_anim.startValue() == _BANNER_HEIGHT
        assert collapse_anim.endValue() == 0

    def test_expand_animation_duration_matches_spec(
        self, qapp: QApplication
    ) -> None:
        """展开动画时长应与 ``_BANNER_EXPAND_MS`` 一致。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        expand_anim = panel._banner_anim_group.animationAt(0)
        assert expand_anim.duration() == _BANNER_EXPAND_MS

    def test_collapse_animation_duration_matches_spec(
        self, qapp: QApplication
    ) -> None:
        """收回动画时长应与 ``_BANNER_COLLAPSE_MS`` 一致。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        collapse_anim = panel._banner_anim_group.animationAt(2)
        assert collapse_anim.duration() == _BANNER_COLLAPSE_MS

    def test_hold_pause_duration_matches_spec(
        self, qapp: QApplication
    ) -> None:
        """保持段时长应与 ``_BANNER_HOLD_MS`` 一致。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        pause_anim = panel._banner_anim_group.animationAt(1)
        assert pause_anim.duration() == _BANNER_HOLD_MS

    def test_banner_text_is_set(self, qapp: QApplication) -> None:
        """横幅文本应被设置为传入的日志文本。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] unique banner text")
        assert panel._recent_banner.text() == "[INFO] unique banner text"

    def test_long_text_is_truncated(self, qapp: QApplication) -> None:
        """过长文本应被截断到 _BANNER_MAX_CHARS + 省略号。"""
        panel = LogPanel()
        long_text = "x" * (_BANNER_MAX_CHARS + 50)
        panel._show_recent_banner(long_text)
        banner_text = panel._recent_banner.text()
        # 应被截断为 _BANNER_MAX_CHARS 个字符 + "…"
        assert len(banner_text) == _BANNER_MAX_CHARS + 1
        assert banner_text.endswith("…")

    def test_short_text_not_truncated(self, qapp: QApplication) -> None:
        """短文本不应被截断。"""
        panel = LogPanel()
        short_text = "short message"
        panel._show_recent_banner(short_text)
        assert panel._recent_banner.text() == short_text

    def test_disabled_animation_skips_banner(
        self, qapp: QApplication
    ) -> None:
        """禁用动画时应跳过横幅显示。"""
        AnimationManager.instance().set_enabled(False)
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        assert panel._banner_anim_group is None

    def test_running_animation_not_restarted(
        self, qapp: QApplication
    ) -> None:
        """动画进行中再次调用应仅更新文本，不重启动画。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] first message")
        first_group = panel._banner_anim_group
        assert first_group is not None

        # 再次调用：动画组应保持不变（不重启）
        panel._show_recent_banner("[INFO] second message")
        assert panel._banner_anim_group is first_group
        # 但文本应更新为最新
        assert panel._recent_banner.text() == "[INFO] second message"

    def test_append_log_triggers_banner_when_passing_filter(
        self, qapp: QApplication
    ) -> None:
        """日志通过过滤时应触发横幅动画。"""
        panel = LogPanel()
        panel.append("[INFO] trigger banner")
        # Task 6：批量模式下横幅在 flush 时触发
        panel._flush_pending_logs()
        assert panel._banner_anim_group is not None

    def test_append_log_skips_banner_when_filtered_out(
        self, qapp: QApplication
    ) -> None:
        """日志被过滤时不应触发横幅动画。"""
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_ERRORS)
        # INFO 级别会被 ERROR 过滤掉
        panel.append("[INFO] filtered out")
        assert panel._banner_anim_group is None

    def test_clear_log_stops_banner_animation(
        self, qapp: QApplication
    ) -> None:
        """``clear_log`` 应停止横幅动画并重置动画组引用。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        assert panel._banner_anim_group is not None

        panel.clear_log()
        assert panel._banner_anim_group is None

    def test_clear_log_resets_banner_max_height(
        self, qapp: QApplication
    ) -> None:
        """``clear_log`` 应将横幅 maximumHeight 重置为 0。"""
        panel = LogPanel()
        # 模拟横幅展开后状态
        panel._recent_banner.setMaximumHeight(_BANNER_HEIGHT)
        panel.clear_log()
        assert panel._recent_banner.maximumHeight() == 0

    def test_clear_log_clears_banner_text(
        self, qapp: QApplication
    ) -> None:
        """``clear_log`` 应清空横幅文本。"""
        panel = LogPanel()
        panel._recent_banner.setText("some text")
        panel.clear_log()
        assert panel._recent_banner.text() == ""

    def test_disabled_animation_append_log_does_not_trigger_banner(
        self, qapp: QApplication
    ) -> None:
        """禁用动画时，``append`` 不应触发横幅动画。"""
        AnimationManager.instance().set_enabled(False)
        panel = LogPanel()
        panel.append("[INFO] test message")
        # Task 6：批量模式下需 flush 后才显示
        panel._flush_pending_logs()
        assert panel._banner_anim_group is None
        # 但日志仍应正常追加到 text_edit
        assert "test message" in panel.text_edit.toPlainText()

    def test_banner_animation_group_started(
        self, qapp: QApplication
    ) -> None:
        """``_show_recent_banner`` 后动画组应处于运行状态。"""
        panel = LogPanel()
        panel._show_recent_banner("[INFO] test message")
        assert (
            panel._banner_anim_group.state()
            == QSequentialAnimationGroup.State.Running
        )


# ---------------------------------------------------------------------------
# Task 6：日志批量刷新
# ---------------------------------------------------------------------------
class TestBatchFlush:
    """Task 6：日志批量刷新契约。

    验证：
    - 多条日志合并为单次 ``appendHtml`` 调用
    - 定时器在首条日志时启动
    - flush 后定时器停止
    - 空缓冲区 flush 不调用 ``appendHtml``
    - 过滤在批量模式下仍正确工作
    - 手动调用 flush 立即显示日志
    """

    def test_batch_append_combines_logs(self, qapp: QApplication) -> None:
        """多条日志合并为单次 ``appendHtml``（通过 mock 计数验证）。

        5 条日志合并为 1 次 ``appendHtml`` 调用，而非 5 次单独调用。
        """
        from unittest.mock import patch

        panel = LogPanel()
        for i in range(5):
            panel.append(f"[INFO] batch line {i}")
        # flush 前：缓冲区有 5 条，text_edit 尚未更新
        assert panel.text_edit.toPlainText() == ""
        assert len(panel._pending_logs) == 5
        # mock appendHtml 验证仅调用 1 次
        with patch.object(panel.text_edit, "appendHtml") as mock_append:
            panel._flush_pending_logs()
            assert mock_append.call_count == 1
        # flush 后缓冲区清空
        assert len(panel._pending_logs) == 0

    def test_timer_starts_on_first_log(self, qapp: QApplication) -> None:
        """首条日志时定时器应启动。"""
        panel = LogPanel()
        assert not panel._batch_timer.isActive()
        panel.append("[INFO] first log")
        assert panel._batch_timer.isActive()

    def test_timer_stops_after_flush(self, qapp: QApplication) -> None:
        """flush 后定时器应停止。"""
        panel = LogPanel()
        panel.append("[INFO] hello")
        assert panel._batch_timer.isActive()
        panel._flush_pending_logs()
        assert not panel._batch_timer.isActive()

    def test_flush_empty_buffer_noop(self, qapp: QApplication) -> None:
        """空缓冲区 flush 不调用 ``appendHtml``（blockCount 不变）。"""
        panel = LogPanel()
        initial_blocks = panel.text_edit.blockCount()
        # 直接调用 flush，缓冲区为空
        panel._flush_pending_logs()
        assert panel.text_edit.blockCount() == initial_blocks
        assert panel.text_edit.toPlainText() == ""

    def test_filter_works_in_batch_mode(self, qapp: QApplication) -> None:
        """过滤在批量模式下仍正确：仅显示通过过滤的日志。"""
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_ERRORS)
        panel.append("[INFO] filtered out")
        panel.append("[ERROR] kept line 1")
        panel.append("[WARNING] filtered out")
        panel.append("[ERROR] kept line 2")
        panel._flush_pending_logs()
        text = panel.text_edit.toPlainText()
        assert "kept line 1" in text
        assert "kept line 2" in text
        assert "filtered out" not in text
        # _raw_logs 仍保存所有日志（4 条）
        assert len(panel._raw_logs) == 4

    def test_manual_flush(self, qapp: QApplication) -> None:
        """手动调用 flush 立即显示日志。"""
        panel = LogPanel()
        panel.append("[INFO] manual flush test")
        # flush 前：text_edit 为空
        assert "manual flush test" not in panel.text_edit.toPlainText()
        # 手动 flush
        panel._flush_pending_logs()
        # flush 后：立即显示
        assert "manual flush test" in panel.text_edit.toPlainText()
        # 缓冲区已清空
        assert len(panel._pending_logs) == 0
        assert not panel._batch_timer.isActive()


# ---------------------------------------------------------------------------
# T-C4：级别统计徽章
# ---------------------------------------------------------------------------
class TestLevelBadges:
    """T-C4：级别统计徽章契约。

    验证：
    - 徽章 widget 存在且初始文本为 ``{LEVEL} 0``
    - 追加日志后徽章计数正确（ERROR 徽章含 ERROR + CRITICAL）
    - ``clear_log`` 后徽章归零
    - 点击 ERROR 徽章切换级别过滤为「仅错误」
    - 点击 INFO/WARNING 徽章切换对应过滤
    """

    def test_badges_exist(self, qapp: QApplication) -> None:
        """三个徽章 QLabel 应在初始化时创建。"""
        panel = LogPanel()
        assert isinstance(panel.info_badge, QLabel)
        assert isinstance(panel.warn_badge, QLabel)
        assert isinstance(panel.error_badge, QLabel)

    def test_badges_initial_count_zero(self, qapp: QApplication) -> None:
        """徽章初始文本应为 ``{LEVEL} 0``。"""
        panel = LogPanel()
        assert panel.info_badge.text() == "INFO 0"
        assert panel.warn_badge.text() == "WARNING 0"
        assert panel.error_badge.text() == "ERROR 0"

    def test_badge_counts_after_append(self, qapp: QApplication) -> None:
        """追加日志后徽章计数正确。

        追加 1 条 INFO + 1 条 WARNING + 1 条 ERROR + 1 条 CRITICAL，
        ERROR 徽章应显示 2（含 ERROR + CRITICAL）。
        """
        panel = LogPanel()
        panel.append("[INFO] info message")
        panel.append("[WARNING] warn message")
        panel.append("[ERROR] error message")
        panel.append("[CRITICAL] critical message")
        assert panel.info_badge.text() == "INFO 1"
        assert panel.warn_badge.text() == "WARNING 1"
        assert panel.error_badge.text() == "ERROR 2"

    def test_level_counts_dict_updated(self, qapp: QApplication) -> None:
        """``_level_counts`` 字典应按级别累加。"""
        panel = LogPanel()
        panel.append("[INFO] info")
        panel.append("[DEBUG] debug")
        panel.append("[ERROR] error")
        panel.append("[CRITICAL] critical")
        assert panel._level_counts["INFO"] == 1
        assert panel._level_counts["DEBUG"] == 1
        assert panel._level_counts["ERROR"] == 1
        assert panel._level_counts["CRITICAL"] == 1
        assert panel._level_counts["WARNING"] == 0

    def test_clear_log_resets_badges(self, qapp: QApplication) -> None:
        """``clear_log`` 后徽章应归零。"""
        panel = LogPanel()
        panel.append("[INFO] info")
        panel.append("[WARNING] warn")
        panel.append("[ERROR] error")
        panel.clear_log()
        assert panel.info_badge.text() == "INFO 0"
        assert panel.warn_badge.text() == "WARNING 0"
        assert panel.error_badge.text() == "ERROR 0"
        # _level_counts 也应全为 0
        assert all(v == 0 for v in panel._level_counts.values())

    def test_click_error_badge_switches_filter(self, qapp: QApplication) -> None:
        """点击 ERROR 徽章后级别过滤切换为「仅错误」。

        文本框仅显示 ERROR + CRITICAL 日志。
        """
        panel = LogPanel()
        panel.append("[INFO] info message")
        panel.append("[ERROR] error message")
        panel.append("[CRITICAL] critical message")
        panel._flush_pending_logs()

        # 初始过滤为「全部」，三条日志均显示
        assert panel.level_filter.currentText() == _FILTER_ALL

        # 点击 ERROR 徽章
        panel.error_badge.clicked.emit()

        # 过滤应切换为「仅错误」
        assert panel.level_filter.currentText() == _FILTER_ERRORS
        # 文本框仅显示 ERROR + CRITICAL
        text = panel.text_edit.toPlainText()
        assert "error message" in text
        assert "critical message" in text
        assert "info message" not in text

    def test_click_info_badge_switches_filter(self, qapp: QApplication) -> None:
        """点击 INFO 徽章后级别过滤切换为「全部」。"""
        panel = LogPanel()
        panel.level_filter.setCurrentText(_FILTER_ERRORS)
        panel.info_badge.clicked.emit()
        assert panel.level_filter.currentText() == _FILTER_ALL

    def test_click_warning_badge_switches_filter(
        self, qapp: QApplication
    ) -> None:
        """点击 WARNING 徽章后级别过滤切换为「仅警告以上」。"""
        panel = LogPanel()
        panel.warn_badge.clicked.emit()
        assert panel.level_filter.currentText() == _FILTER_WARN_PLUS


# ---------------------------------------------------------------------------
# T-C4：保存日志菜单
# ---------------------------------------------------------------------------
class TestSaveMenu:
    """T-C4：保存日志菜单按钮契约。

    验证：
    - 保存按钮拥有菜单，菜单包含两个选项
    - ``_save_filtered`` 仅保存通过当前过滤的日志
    - ``_save_all`` 保存全部原始日志
    """

    def test_save_btn_has_menu(self, qapp: QApplication) -> None:
        """保存按钮应拥有 QMenu。"""
        panel = LogPanel()
        assert panel.save_btn.menu() is not None

    def test_save_menu_has_two_options(self, qapp: QApplication) -> None:
        """保存菜单应包含两个选项。"""
        panel = LogPanel()
        menu = panel.save_btn.menu()
        actions = menu.actions()
        assert len(actions) == 2
        texts = [a.text() for a in actions]
        assert "保存当前过滤结果" in texts
        assert "保存全部" in texts

    def test_save_filtered_only_saves_filtered_logs(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``_save_filtered`` 仅保存通过当前过滤的日志。"""
        from unittest.mock import patch

        panel = LogPanel()
        panel.append("[INFO] info message")
        panel.append("[ERROR] error message")
        panel._flush_pending_logs()

        # 设置过滤为「仅错误」
        panel.level_filter.setCurrentText(_FILTER_ERRORS)

        save_path = str(tmp_path / "filtered.log")
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=(save_path, "")
        ):
            panel._save_filtered()

        with open(save_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "error message" in content
        assert "info message" not in content

    def test_save_all_saves_all_logs(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``_save_all`` 保存全部原始日志（不受过滤影响）。"""
        from unittest.mock import patch

        panel = LogPanel()
        panel.append("[INFO] info message")
        panel.append("[ERROR] error message")
        panel._flush_pending_logs()

        # 设置过滤为「仅错误」，但 _save_all 应保存全部
        panel.level_filter.setCurrentText(_FILTER_ERRORS)

        save_path = str(tmp_path / "all.log")
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=(save_path, "")
        ):
            panel._save_all()

        with open(save_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "info message" in content
        assert "error message" in content

    def test_save_filtered_canceled_no_file(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """用户取消保存对话框时不写文件。"""
        from unittest.mock import patch

        panel = LogPanel()
        panel.append("[INFO] info message")

        # 模拟用户取消（返回空字符串）
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            panel._save_filtered()

        # 不应抛出异常，且 _raw_logs 仍保留
        assert len(panel._raw_logs) == 1

    def test_save_filtered_respects_search_filter(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``_save_filtered`` 同时遵守搜索关键词过滤。"""
        from unittest.mock import patch

        panel = LogPanel()
        panel.append("[INFO] apple message")
        panel.append("[INFO] banana message")
        panel._flush_pending_logs()

        # 设置搜索关键词
        panel.search_box.setText("banana")

        save_path = str(tmp_path / "search_filtered.log")
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=(save_path, "")
        ):
            panel._save_filtered()

        with open(save_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "banana" in content
        assert "apple" not in content
