"""benchmark_dialog 模块单元测试。

验证 ``BenchmarkDialog`` 的核心行为，包括：
- 初始 UI 控件状态（spinbox 默认值、按钮启用状态）
- 工具类型下拉框默认选中 balcon
- 点击"开始测试"后实例化 benchmark 并切换按钮状态
- 取消按钮调用 benchmark.cancel 并禁用自身
- 应用推荐值发射 apply_concurrency 信号
- 单级完成时更新图表数据点
- 全部完成时更新状态标签与按钮状态

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件，
并 mock pywin32 以确保 SAPI5 模块可导入。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import MagicMock

# 确保 pywin32 mock（若尚未加载真实模块），使 SAPI5 模块可正常导入
if "win32com" not in sys.modules:
    sys.modules["win32com"] = MagicMock()
    sys.modules["win32com.client"] = MagicMock()
if "pythoncom" not in sys.modules:
    sys.modules["pythoncom"] = MagicMock()

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.concurrency_benchmark import BenchmarkResult
from balcon_batch_tts.core.sapi_config import SapiConfig
from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.dialogs.benchmark_dialog import BenchmarkDialog


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """会话级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 辅助：FakeBenchmark，避免真实 run 阻塞测试
# ---------------------------------------------------------------------------
class _FakeBenchmark(QObject):
    """替代 ``ConcurrencyBenchmark`` 的桩对象，``run`` 为空操作。

    保留与真实 benchmark 相同的信号定义，以便 ``BenchmarkDialog._on_start``
    中的 ``connect`` 调用不会失败。
    """

    level_started = Signal(int)
    level_finished = Signal(int, object)
    progress_updated = Signal(int, int)
    all_finished = Signal(list, int)
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cancel_called = False

    def run(self, config, task_factory) -> None:
        # 不真正执行，避免嵌套 QEventLoop 阻塞测试
        pass

    def cancel(self) -> None:
        self.cancel_called = True


# ---------------------------------------------------------------------------
# 辅助：构造 BenchmarkResult
# ---------------------------------------------------------------------------
def _make_result(
    concurrency: int,
    throughput: float = 10.0,
    p95: float = 100.0,
    success_rate: float = 1.0,
) -> BenchmarkResult:
    """构造单级 ``BenchmarkResult`` 实例，字段使用合理默认值。"""
    return BenchmarkResult(
        concurrency=concurrency,
        throughput=throughput,
        p95_latency=p95,
        success_rate=success_rate,
        total_time=2.0,
        task_latencies=[100.0],
    )


# ---------------------------------------------------------------------------
# 对话框 fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def dialog(qapp: QApplication) -> BenchmarkDialog:
    """构造一个默认配置的 ``BenchmarkDialog`` 实例。"""
    return BenchmarkDialog(
        tool_type=ToolType.BALCON,
        balcon_config=BalconConfig.create_default(),
        sapi_config=SapiConfig.create_default(),
        balcon_path="C:/fake/balcon.exe",
    )


# ---------------------------------------------------------------------------
# 初始状态
# ---------------------------------------------------------------------------
def test_dialog_initial_state(dialog: BenchmarkDialog) -> None:
    """构造后各控件应处于默认状态。"""
    assert dialog._min_concurrency_spin.value() == 1
    assert dialog._max_concurrency_spin.value() == 8
    assert dialog._tasks_per_level_spin.value() == 20
    assert dialog._early_stop_check.isChecked() is True
    assert dialog._cancel_btn.isEnabled() is False
    assert dialog._apply_btn.isEnabled() is False
    assert dialog._start_btn.isEnabled() is True


def test_tool_combo_defaults_to_balcon(dialog: BenchmarkDialog) -> None:
    """工具下拉框默认应选中 balcon。"""
    # PySide6 QVariant 将 ToolType(str, Enum) 降级为 str，需还原为枚举
    data = dialog._tool_combo.currentData()
    assert ToolType(data) is ToolType.BALCON


# ---------------------------------------------------------------------------
# 启动与取消
# ---------------------------------------------------------------------------
def test_start_emits_progress_signals(
    dialog: BenchmarkDialog, monkeypatch
) -> None:
    """点击开始按钮应实例化 benchmark 并切换按钮启用状态。"""
    # 替换 ConcurrencyBenchmark，阻止真实 run 执行
    monkeypatch.setattr(
        "balcon_batch_tts.gui.dialogs.benchmark_dialog.ConcurrencyBenchmark",
        _FakeBenchmark,
    )

    dialog._start_btn.click()

    # _benchmark 应已实例化
    assert dialog._benchmark is not None
    assert isinstance(dialog._benchmark, _FakeBenchmark)
    # 按钮状态切换
    assert dialog._start_btn.isEnabled() is False
    assert dialog._cancel_btn.isEnabled() is True

    # 处理 QTimer.singleShot(0, ...) 延迟调用
    # _FakeBenchmark.run 为空操作，不会阻塞
    qapp = QApplication.instance()
    qapp.processEvents()

    # _benchmark 仍存在
    assert dialog._benchmark is not None


def test_cancel_calls_benchmark_cancel(
    dialog: BenchmarkDialog, monkeypatch
) -> None:
    """启动后调用 _on_cancel 应触发 benchmark.cancel 并禁用取消按钮。"""
    monkeypatch.setattr(
        "balcon_batch_tts.gui.dialogs.benchmark_dialog.ConcurrencyBenchmark",
        _FakeBenchmark,
    )

    dialog._start_btn.click()
    assert dialog._benchmark is not None

    dialog._on_cancel()

    # benchmark.cancel 应被调用
    assert dialog._benchmark.cancel_called is True  # type: ignore[attr-defined]
    # 取消按钮应禁用
    assert dialog._cancel_btn.isEnabled() is False


# ---------------------------------------------------------------------------
# 应用推荐值
# ---------------------------------------------------------------------------
def test_apply_recommended_emits_signal(dialog: BenchmarkDialog) -> None:
    """点击应用推荐值应发射 apply_concurrency 信号，参数为最优并发数。"""
    dialog._optimal_concurrency = 4

    received: list[int] = []
    dialog.apply_concurrency.connect(lambda n: received.append(n))

    dialog._on_apply_recommended()

    assert received == [4]


# ---------------------------------------------------------------------------
# 图表更新
# ---------------------------------------------------------------------------
def test_chart_updates_on_level_finished(
    dialog: BenchmarkDialog,
) -> None:
    """_on_level_finished 应追加 _results 与图表数据点。"""
    dialog._on_level_finished(2, _make_result(2))

    assert len(dialog._chart._points) == 1
    assert len(dialog._results) == 1


# ---------------------------------------------------------------------------
# 全部完成
# ---------------------------------------------------------------------------
def test_all_finished_updates_status_and_buttons(
    dialog: BenchmarkDialog,
) -> None:
    """_on_all_finished 应更新状态标签文本与按钮启用状态。"""
    results = [_make_result(2, throughput=10.0, p95=150.0)]
    dialog._on_all_finished(results, 2)

    text = dialog._status_label.text()
    assert "推荐并发数：2" in text
    assert "10.00" in text
    assert "150.0" in text

    assert dialog._apply_btn.isEnabled() is True
    assert dialog._start_btn.isEnabled() is True
    assert dialog._cancel_btn.isEnabled() is False
