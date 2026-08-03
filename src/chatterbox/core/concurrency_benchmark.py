"""并发基准测试引擎。

定义 :class:`ConcurrencyBenchmark`，通过逐级递增并发数（默认 1~8）对
:class:`chatterbox.core.task_scheduler.TaskScheduler` 进行压力测试，
采集每级的吞吐量、p95 时延与成功率，并自动计算最优并发点
（吞吐量峰值；差异 <5% 时取 p95 最低者）。

引擎使用独立的 :class:`TaskScheduler` 实例，不污染主调度器。任务创建逻辑
通过 ``task_factory`` 回调由调用方提供（解耦具体工具类型），便于
:class:`BenchmarkDialog` 根据 :class:`ToolType` 构造 BalconTask/SapiTask。

:meth:`ConcurrencyBenchmark.run` 通过 :class:`QEventLoop` 阻塞调用线程，
应在独立 QThread 中调用以避免阻塞 UI。
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, QEventLoop, QTimer, Signal

from chatterbox.core.tool_type import ToolType

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """单个并发级别的测试结果。"""
    concurrency: int
    throughput: float  # tasks/s
    p95_latency: float  # ms
    success_rate: float  # 0.0~1.0
    total_time: float  # s
    task_latencies: list[float] = field(default_factory=list)  # ms, 排除预热


@dataclass
class BenchmarkConfig:
    """基准测试配置。"""
    tool_type: ToolType
    min_concurrency: int = 1
    max_concurrency: int = 8
    tasks_per_level: int = 30  # 样本量需≥30以保证 p95 统计稳定性
    warmup_count: int = 2  # 每级前 N 个完成的任务不计入 p95（每级新调度器→冷线程）
    text_sample: str = "这是一段用于并发性能测试的文本样本。The quick brown fox jumps over the lazy dog."
    early_stop: bool = True  # 连续 2 级吞吐量下降 >10% 或 p95 上涨 >50% 时提前终止


class ConcurrencyBenchmark(QObject):
    """并发基准测试引擎。

    逐级递增并发数，每级运行 N 个任务，采集吞吐量/p95/成功率，
    自动计算最优并发点（吞吐量峰值，差异 <5% 取 p95 最低）。

    使用独立 TaskScheduler 实例，不污染主调度器。
    通过 task_factory 回调由调用方提供任务创建逻辑（解耦工具类型）。

    Signals:
        level_started(int): 当前并发级开始，参数为并发数。
        level_finished(int, object): 当前并发级完成，参数为并发数与
            :class:`BenchmarkResult`。
        progress_updated(int, int): 进度更新，参数为当前级索引与总级数。
        all_finished(list, int): 全部测试完成，参数为结果列表与最优并发数。
        error(str): 测试发生异常，参数为错误信息。
    """

    level_started = Signal(int)  # 当前并发数
    level_finished = Signal(int, object)  # (concurrency, BenchmarkResult)
    progress_updated = Signal(int, int)  # (current_level_index, total_levels)
    all_finished = Signal(list, int)  # (results, optimal_concurrency)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancel_event = threading.Event()

    def run(
        self,
        config: BenchmarkConfig,
        task_factory: Callable[[int, int, str], list],
    ) -> None:
        """运行基准测试。

        Args:
            config: 测试配置。
            task_factory: 回调函数 (concurrency, level_index, temp_dir) -> list[BaseToolTask]，
                          返回该级别的任务列表。由 Dialog 提供，封装 BalconTask/SapiTask 创建。
        """
        self._cancel_event.clear()
        results: list[BenchmarkResult] = []
        total_levels = config.max_concurrency - config.min_concurrency + 1

        try:
            for level_idx, n in enumerate(
                range(config.min_concurrency, config.max_concurrency + 1)
            ):
                if self._cancel_event.is_set():
                    break

                self.level_started.emit(n)
                self.progress_updated.emit(level_idx, total_levels)

                # 创建临时目录
                temp_dir = tempfile.mkdtemp(prefix=f"balcon_bench_c{n}_")

                try:
                    # 创建任务
                    tasks = task_factory(n, level_idx, temp_dir)
                    if len(tasks) != config.tasks_per_level:
                        logger.warning(
                            "task_factory 返回 %d 任务，期望 %d",
                            len(tasks),
                            config.tasks_per_level,
                        )

                    # 采集时延
                    latencies: list[float] = []
                    task_count = len(tasks)
                    completed = 0
                    succeeded = 0
                    task_index = 0  # 用于预热排除（每级独立计数）

                    # 连接 finished 信号采集时延
                    loop = QEventLoop()

                    def on_finished(filename, returncode, stderr, elapsed):
                        nonlocal completed, succeeded, task_index
                        completed += 1
                        if returncode == 0:
                            succeeded += 1
                        # 每级前 warmup_count 个任务不计入 p95：
                        # 每级创建新 TaskScheduler，线程池冷启动（线程创建、
                        # COM 初始化等开销），首几个任务时延偏高不具代表性。
                        if task_index < config.warmup_count:
                            task_index += 1
                        else:
                            task_index += 1
                            latencies.append(elapsed * 1000.0)  # s -> ms

                    def on_all_finished(s, f, t):
                        # 延迟退出事件循环：让已排队的 finished 信号先被处理，
                        # 避免 all_finished 在最后一个 finished 之前退出循环
                        # 导致 completed/succeeded 计数不足。
                        QTimer.singleShot(0, loop.quit)

                    # 创建独立调度器
                    from chatterbox.core.task_scheduler import TaskScheduler
                    scheduler = TaskScheduler(max_concurrency=n)
                    scheduler.all_finished.connect(on_all_finished)

                    for task in tasks:
                        task.signals.finished.connect(on_finished)

                    # 计时 + 提交
                    start_time = time.perf_counter()
                    scheduler.submit(tasks)
                    loop.exec()
                    total_time = time.perf_counter() - start_time

                    # 计算结果
                    throughput = task_count / total_time if total_time > 0 else 0.0
                    p95 = self._calculate_p95(latencies)
                    success_rate = succeeded / task_count if task_count > 0 else 0.0

                    result = BenchmarkResult(
                        concurrency=n,
                        throughput=throughput,
                        p95_latency=p95,
                        success_rate=success_rate,
                        total_time=total_time,
                        task_latencies=latencies[:],  # copy
                    )
                    results.append(result)
                    self.level_finished.emit(n, result)

                    # 提前终止：连续 2 级吞吐量下降 >10% 或 p95 上涨 >50%
                    if config.early_stop and len(results) >= 3:
                        last3 = results[-3:]
                        throughput_decline = (
                            last3[1].throughput < last3[0].throughput * 0.9
                            and last3[2].throughput < last3[1].throughput * 0.9
                        )
                        # p95 退化：连续 2 级 p95 涨幅 >50%（且首级 p95>0）
                        p95_base = last3[0].p95_latency
                        p95_degradation = (
                            p95_base > 0
                            and last3[1].p95_latency > p95_base * 1.5
                            and last3[2].p95_latency > last3[1].p95_latency * 1.5
                        )
                        if throughput_decline or p95_degradation:
                            logger.info(
                                "提前终止：吞吐量下降=%s, p95退化=%s",
                                throughput_decline, p95_degradation,
                            )
                            break

                finally:
                    # 清理调度器（无论正常完成、提前终止还是异常都执行）
                    try:
                        scheduler.deleteLater()
                    except Exception:  # noqa: BLE001
                        pass
                    # 清理临时目录
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception as e:
                        logger.warning("清理临时目录失败 %s: %s", temp_dir, e)

            # 计算最优并发数
            optimal = (
                self._find_optimal(results) if results else config.min_concurrency
            )
            self.all_finished.emit(results, optimal)

        except Exception as e:
            logger.exception("基准测试发生异常")
            self.error.emit(str(e))

    def cancel(self) -> None:
        """请求取消，当前级完成后停止。"""
        self._cancel_event.set()

    @staticmethod
    def _calculate_p95(latencies: list[float]) -> float:
        """计算 p95 时延（最近秩方法 nearest-rank）。

        使用 ``ceil(n * 0.95) - 1`` 作为 0 基索引，避免 ``int()`` 截断
        导致偶数样本量时退化为 p100（如 n=20 时 ``int(19.0)=19`` 取末尾）。
        """
        if not latencies:
            return 0.0
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        idx = math.ceil(n * 0.95) - 1
        return sorted_lat[min(idx, n - 1)]

    @staticmethod
    def _find_optimal(results: list[BenchmarkResult]) -> int:
        """找最优并发数：吞吐量峰值，差异 <5% 取 p95 最低。"""
        if not results:
            return 1
        if len(results) == 1:
            return results[0].concurrency

        # 找吞吐量峰值
        max_throughput = max(r.throughput for r in results)
        # 候选：吞吐量在峰值 95% 以内
        candidates = [r for r in results if r.throughput >= max_throughput * 0.95]
        # 从候选中取 p95 最低
        best = min(candidates, key=lambda r: r.p95_latency)
        return best.concurrency


__all__ = ["ConcurrencyBenchmark", "BenchmarkConfig", "BenchmarkResult"]
