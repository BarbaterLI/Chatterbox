"""concurrency_benchmark 模块单元测试。

验证 :class:`ConcurrencyBenchmark` 引擎的逐级并发扫描、p95 计算、
最优并发判定、提前终止、取消、临时目录清理等行为。

使用 :class:`_FakeScheduler` 替换 :class:`TaskScheduler`（不启动真实线程池），
通过 :class:`_FakeTask` 模拟任务完成信号。参考 ``tests/test_task_scheduler.py``
的 ``_FakeTask`` / ``_FakeSignals`` 与模块级 ``qapp`` fixture 风格。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

import pytest
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.concurrency_benchmark import (
    ConcurrencyBenchmark,
    BenchmarkConfig,
    BenchmarkResult,
)
from balcon_batch_tts.core.tool_type import ToolType
import balcon_batch_tts.core.concurrency_benchmark as bm_module


@pytest.fixture(scope="session")
def qapp():
    """session 级 QApplication 单例 fixture。

    使用 QApplication（而非 QCoreApplication）以与其他 GUI 测试文件兼容，
    避免在同一次 pytest 运行中先创建 QCoreApplication 再创建 QApplication
    导致的实例类型冲突崩溃。
    """
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeSignals(QObject):
    """模拟 BaseToolTask.signals 的最小信号集。"""

    started = Signal(str)
    finished = Signal(str, int, str, float)
    log = Signal(str)
    error = Signal(str, str)


class _FakeTask:
    """模拟 BaseToolTask 的最小可调度任务。

    不真正在线程池执行，仅持有 signals 对象供测试手动发射 finished 信号。
    """

    def __init__(
        self,
        filename: str,
        returncode: int = 0,
        elapsed: float = 0.1,
    ) -> None:
        self.filename = filename
        self.input_file = filename
        self.signals = _FakeSignals()
        self._returncode = returncode
        self._elapsed = elapsed

    def run(self) -> None:
        """QRunnable.run 的占位实现（实际不调用）。"""
        pass

    def cancel(self) -> None:
        pass

    def emit_finished(self) -> None:
        """测试辅助：手动发射 finished 信号。"""
        self.signals.finished.emit(
            self.filename, self._returncode, "", self._elapsed
        )


class _FakeScheduler(QObject):
    """替换 TaskScheduler 的最小实现，不真正启动线程。

    ``submit`` 后通过 :func:`QTimer.singleShot` 在事件循环中触发完成，
    使 :class:`QEventLoop.exec` 能正常退出。信号签名与
    :class:`TaskScheduler.all_finished` 一致：``(int, int, float)``。
    """

    all_finished = Signal(int, int, float)

    def __init__(self, max_concurrency: int = 1, parent=None) -> None:
        super().__init__(parent)
        self._tasks: list = []
        self._max_concurrency = max_concurrency

    def set_max_concurrency(self, n: int) -> None:
        self._max_concurrency = n

    def submit(self, tasks) -> None:
        self._tasks = list(tasks)
        # 在事件循环启动后立即触发完成
        QTimer.singleShot(0, self._complete_all)

    def _complete_all(self) -> None:
        for task in self._tasks:
            task.emit_finished()
        self.all_finished.emit(len(self._tasks), 0, 0.1)

    def deleteLater(self) -> None:  # noqa: N802 - 与 Qt API 一致
        pass


class _MockTime:
    """模拟 ``time.perf_counter``，按预设序列返回时间值。

    用于控制 :meth:`ConcurrencyBenchmark.run` 内的 ``total_time`` 计算，
    从而精确控制每级的吞吐量（``throughput = task_count / total_time``）。
    """

    def __init__(self, times: list[float]) -> None:
        self._times = list(times)
        self._idx = 0

    def perf_counter(self) -> float:
        val = self._times[self._idx]
        self._idx += 1
        return val


def _make_task_factory(count: int, elapsed: float = 0.1, returncode: int = 0):
    """创建返回 ``count`` 个 :class:`_FakeTask` 的 task_factory 回调。"""

    def factory(n: int, level_idx: int, temp_dir: str):
        return [
            _FakeTask(
                f"task_{level_idx}_{i}.wav",
                returncode=returncode,
                elapsed=elapsed,
            )
            for i in range(count)
        ]

    return factory


# ---------------------------------------------------------------------------
# p95 计算
# ---------------------------------------------------------------------------
class TestP95Calculation:
    """``_calculate_p95`` 静态方法。"""

    def test_p95_calculation(self) -> None:
        """10 个时延值，idx=ceil(10*0.95)-1=9，返回 sorted[9]=100.0。"""
        latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        result = ConcurrencyBenchmark._calculate_p95(latencies)
        assert result == 100.0


# ---------------------------------------------------------------------------
# 最优并发判定
# ---------------------------------------------------------------------------
class TestFindOptimal:
    """``_find_optimal`` 静态方法。"""

    def test_find_optimal_peak_throughput(self) -> None:
        """吞吐量峰值优先：throughput=10,20,15 → 返回 2。"""
        results = [
            BenchmarkResult(
                concurrency=1,
                throughput=10,
                p95_latency=100,
                success_rate=1.0,
                total_time=0.4,
            ),
            BenchmarkResult(
                concurrency=2,
                throughput=20,
                p95_latency=80,
                success_rate=1.0,
                total_time=0.3,
            ),
            BenchmarkResult(
                concurrency=3,
                throughput=15,
                p95_latency=90,
                success_rate=1.0,
                total_time=0.4,
            ),
        ]
        optimal = ConcurrencyBenchmark._find_optimal(results)
        # max_throughput=20，候选（>=20*0.95=19）仅 concurrency=2
        assert optimal == 2

    def test_find_optimal_tiebreak_by_p95(self) -> None:
        """吞吐量差异 <5% 时取 p95 最低：throughput=20,20,19，p95=100,80,90 → 返回 2。"""
        results = [
            BenchmarkResult(
                concurrency=1,
                throughput=20,
                p95_latency=100,
                success_rate=1.0,
                total_time=0.3,
            ),
            BenchmarkResult(
                concurrency=2,
                throughput=20,
                p95_latency=80,
                success_rate=1.0,
                total_time=0.3,
            ),
            BenchmarkResult(
                concurrency=3,
                throughput=19,
                p95_latency=90,
                success_rate=1.0,
                total_time=0.32,
            ),
        ]
        optimal = ConcurrencyBenchmark._find_optimal(results)
        # max_throughput=20，候选（>=19）全部三个，取 p95 最低=80 → concurrency=2
        assert optimal == 2


# ---------------------------------------------------------------------------
# run 方法：逐级扫描
# ---------------------------------------------------------------------------
class TestRunBenchmark:
    """``ConcurrencyBenchmark.run`` 逐级扫描与信号发射。"""

    def test_run_collects_results_per_level(self, qapp, monkeypatch) -> None:
        """min=1, max=3, tasks_per_level=4 → all_finished 收到 3 个 BenchmarkResult。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=3,
            tasks_per_level=4,
            warmup_count=0,
        )

        benchmark = ConcurrencyBenchmark()
        received: list = []
        benchmark.all_finished.connect(
            lambda results, optimal: received.append((results, optimal))
        )

        benchmark.run(config, _make_task_factory(4))

        assert len(received) == 1
        results, _optimal = received[0]
        assert len(results) == 3
        assert all(isinstance(r, BenchmarkResult) for r in results)
        assert [r.concurrency for r in results] == [1, 2, 3]

    def test_warmup_excluded_from_p95(self, qapp, monkeypatch) -> None:
        """首级(level_idx=0) 前 warmup_count=2 个任务不计入 task_latencies。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=1,
            tasks_per_level=4,
            warmup_count=2,
        )

        benchmark = ConcurrencyBenchmark()
        received: list = []
        benchmark.all_finished.connect(
            lambda results, optimal: received.append((results, optimal))
        )

        benchmark.run(config, _make_task_factory(4))

        results, _optimal = received[0]
        assert len(results) == 1
        # tasks_per_level - warmup_count = 4 - 2 = 2
        assert len(results[0].task_latencies) == 2

    def test_early_stop_on_throughput_decline(self, qapp, monkeypatch) -> None:
        """连续 2 级吞吐量下降 >10% 时提前终止，all_finished 仅含 ≤3 个结果。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        # 通过 mock time 控制 total_time，从而精确控制吞吐量：
        # tasks_per_level=6，每级 2 次 perf_counter 调用（start/end）
        # Level 1: total=0.6  → throughput=6/0.6=10
        # Level 2: total=0.75 → throughput=6/0.75=8
        # Level 3: total=1.0  → throughput=6/1.0=6
        # 早期终止条件：8 < 10*0.9=9 ✓ 且 6 < 8*0.9=7.2 ✓ → break
        mock_time = _MockTime([0.0, 0.6, 0.6, 1.35, 1.35, 2.35])
        monkeypatch.setattr(bm_module, "time", mock_time)

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=5,
            tasks_per_level=6,
            warmup_count=0,
            early_stop=True,
        )

        benchmark = ConcurrencyBenchmark()
        received: list = []
        benchmark.all_finished.connect(
            lambda results, optimal: received.append((results, optimal))
        )

        benchmark.run(config, _make_task_factory(6))

        results, _optimal = received[0]
        # 提前终止应在第 3 级后触发
        assert len(results) <= 3
        assert len(results) == 3
        throughputs = [r.throughput for r in results]
        assert throughputs[0] > throughputs[1] > throughputs[2]

    def test_cancel_stops_after_current_level(self, qapp, monkeypatch) -> None:
        """第一级完成后调用 cancel()，不启动下一级（all_finished 仅 1 个结果）。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=3,
            tasks_per_level=4,
            warmup_count=0,
        )

        benchmark = ConcurrencyBenchmark()
        received: list = []
        benchmark.all_finished.connect(
            lambda results, optimal: received.append((results, optimal))
        )

        # 第一级完成后请求取消
        def on_level_finished(n: int, result) -> None:
            if n == config.min_concurrency:
                benchmark.cancel()

        benchmark.level_finished.connect(on_level_finished)

        benchmark.run(config, _make_task_factory(4))

        results, _optimal = received[0]
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 临时目录清理
# ---------------------------------------------------------------------------
class TestTempDirCleanup:
    """临时目录在成功/异常路径下均被清理。"""

    def test_temp_dir_cleanup_on_success(self, qapp, monkeypatch) -> None:
        """每级完成后临时目录被删除（os.path.exists 返回 False）。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        created_dirs: list[str] = []
        real_mkdtemp = tempfile.mkdtemp

        def spy_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created_dirs.append(path)
            return path

        monkeypatch.setattr(tempfile, "mkdtemp", spy_mkdtemp)

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=2,
            tasks_per_level=4,
            warmup_count=0,
        )

        benchmark = ConcurrencyBenchmark()
        benchmark.run(config, _make_task_factory(4))

        assert len(created_dirs) == 2
        for d in created_dirs:
            assert not os.path.exists(d)

    def test_temp_dir_cleanup_on_exception(self, qapp, monkeypatch) -> None:
        """task_factory 抛异常时 finally 块仍清理临时目录。"""
        monkeypatch.setattr(
            "balcon_batch_tts.core.task_scheduler.TaskScheduler", _FakeScheduler
        )

        created_dirs: list[str] = []
        real_mkdtemp = tempfile.mkdtemp

        def spy_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created_dirs.append(path)
            return path

        monkeypatch.setattr(tempfile, "mkdtemp", spy_mkdtemp)

        config = BenchmarkConfig(
            tool_type=ToolType.BALCON,
            min_concurrency=1,
            max_concurrency=1,
            tasks_per_level=4,
            warmup_count=0,
        )

        def raising_factory(n: int, level_idx: int, temp_dir: str):
            raise RuntimeError("task_factory error")

        benchmark = ConcurrencyBenchmark()
        errors: list[str] = []
        benchmark.error.connect(lambda msg: errors.append(msg))
        all_finished_received: list = []
        benchmark.all_finished.connect(
            lambda results, optimal: all_finished_received.append(
                (results, optimal)
            )
        )

        benchmark.run(config, raising_factory)

        # error 信号发射，all_finished 不发射
        assert len(errors) == 1
        assert "task_factory error" in errors[0]
        assert len(all_finished_received) == 0
        # 临时目录在 finally 块中被清理
        assert len(created_dirs) == 1
        assert not os.path.exists(created_dirs[0])
