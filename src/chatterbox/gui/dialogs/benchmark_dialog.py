"""并发基准测试对话框。

提供 :class:`BenchmarkDialog`，通过图形界面配置并运行
:class:`chatterbox.core.concurrency_benchmark.ConcurrencyBenchmark`，
逐级递增并发数采集吞吐量与 p95 时延，实时绘制
:class:`chatterbox.gui.widgets.benchmark_chart.BenchmarkChart` 图表，
并在完成后向主窗口发射推荐并发数。

测试任务通过 ``task_factory`` 回调构造：根据 :class:`ToolType` 创建
:class:`BalconTask` 或 :class:`SapiTask`，固定输出 WAV 以避免 ffmpeg
转码干扰时延测量。SAPI5 相关导入使用 try/except，pywin32 缺失时禁用
SAPI5 选项。

使用 Qt6 原生风格，不引入自定义 QSS。
"""

from __future__ import annotations

import copy
import logging
import os

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.audio_encoder import AudioFormat
from chatterbox.core.config import BalconConfig
from chatterbox.core.concurrency_benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    ConcurrencyBenchmark,
)
from chatterbox.core.tool_type import ToolType
from chatterbox.core.worker import BalconTask
from chatterbox.gui.widgets.benchmark_chart import BenchmarkChart

# SAPI5 相关模块可能不可用（sapi_worker 依赖 pywin32），延迟导入
try:
    from chatterbox.core.sapi_config import SapiConfig
    from chatterbox.core.sapi_worker import SapiTask

    _SAPI_AVAILABLE = True
except ImportError:  # noqa: E402 - 可选依赖，缺失时置 None
    SapiConfig = None  # type: ignore[assignment,misc]
    SapiTask = None  # type: ignore[assignment,misc]
    _SAPI_AVAILABLE = False

logger = logging.getLogger(__name__)

# 对话框允许的并发范围上限
_MAX_CONCURRENCY = 16
# 推荐并发上限阈值（超过此值时显示警告）
_WARN_CONCURRENCY = 12

# 默认测试文本样本（与 BenchmarkConfig 默认值一致）
_DEFAULT_TEXT_SAMPLE = (
    "这是一段用于并发性能测试的文本样本。"
    "The quick brown fox jumps over the lazy dog."
)


class BenchmarkDialog(QDialog):
    """并发基准测试对话框。

    配置并运行 :class:`ConcurrencyBenchmark`，实时绘制吞吐量与 p95 时延
    曲线，完成后发射 :attr:`apply_concurrency` 信号供主窗口应用推荐值。

    benchmark 在主线程通过 :class:`QTimer.singleShot` 延迟调用 ``run()``，
    其内部使用嵌套 :class:`QEventLoop`，UI 仍可响应取消按钮。

    Args:
        tool_type: 默认选中的工具类型（balcon 或 SAPI5）。
        balcon_config: balcon 配置（会被复制，避免修改主窗口配置）。
        sapi_config: SAPI5 配置；为 ``None`` 时禁用 SAPI5 选项。
        balcon_path: balcon.exe 路径。
        parent: 父窗口。

    Signals:
        apply_concurrency(int): 用户点击"应用推荐值"时发射，参数为推荐并发数。
    """

    apply_concurrency = Signal(int)

    def __init__(
        self,
        tool_type: ToolType,
        balcon_config: BalconConfig,
        sapi_config: SapiConfig | None,
        balcon_path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("并发基准测试")
        self.setModal(True)
        self.resize(700, 720)

        # 保存配置副本（浅拷贝，避免修改主窗口配置；任务内部会再次复制）
        self._balcon_config: BalconConfig = copy.copy(balcon_config)
        self._sapi_config: SapiConfig | None = (
            copy.copy(sapi_config) if sapi_config is not None else None
        )
        self._balcon_path: str = balcon_path

        # 测试运行时状态
        self._benchmark: ConcurrencyBenchmark | None = None
        # BenchmarkConfig 在 _on_start 中构建，此处预初始化避免类型 Optional
        self._config: BenchmarkConfig = BenchmarkConfig(
            tool_type=tool_type,
        )
        self._results: list[BenchmarkResult] = []
        self._optimal_concurrency: int = 0

        # 构建 UI
        self._build_ui()

        # 预选传入的工具类型
        self._set_default_tool_type(tool_type)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """构建对话框界面：配置区 + 图表区 + 控制区。"""
        layout = QVBoxLayout(self)

        # 顶部配置区
        layout.addWidget(self._build_config_group())

        # 中部图表区
        self._chart = BenchmarkChart(self)
        self._chart.setMinimumHeight(300)
        self._chart.setMinimumWidth(400)
        layout.addWidget(self._chart, 1)  # 拉伸因子 1，让图表占据剩余空间

        # 底部控制区
        layout.addLayout(self._build_control_layout())

    def _build_config_group(self) -> QGroupBox:
        """构建顶部配置区 QGroupBox（含工具类型/并发范围/任务数/文本/提前终止）。"""
        group = QGroupBox("测试配置", self)
        form = QFormLayout(group)

        # 工具类型
        self._tool_combo = QComboBox(group)
        self._tool_combo.setMinimumWidth(120)
        # balcon 始终可用
        self._tool_combo.addItem("balcon", ToolType.BALCON)
        # SAPI5 仅在模块可用时可选
        if _SAPI_AVAILABLE and SapiConfig is not None:
            self._tool_combo.addItem("SAPI5", ToolType.SAPI)
        form.addRow("工具类型：", self._tool_combo)

        # 并发范围（min + max 同一行）
        range_widget = QWidget(group)
        range_layout = QHBoxLayout(range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)

        self._min_concurrency_spin = QSpinBox(range_widget)
        self._min_concurrency_spin.setRange(1, _MAX_CONCURRENCY)
        self._min_concurrency_spin.setValue(1)
        self._min_concurrency_spin.setMinimumWidth(70)

        self._max_concurrency_spin = QSpinBox(range_widget)
        self._max_concurrency_spin.setRange(1, _MAX_CONCURRENCY)
        self._max_concurrency_spin.setValue(8)
        self._max_concurrency_spin.setMinimumWidth(70)
        # 超过 12 时显示警告
        self._max_concurrency_spin.valueChanged.connect(
            self._on_max_concurrency_changed
        )

        self._range_warning_label = QLabel(range_widget)
        self._range_warning_label.setMinimumWidth(130)

        range_layout.addWidget(self._min_concurrency_spin)
        range_layout.addWidget(QLabel("~", range_widget))
        range_layout.addWidget(self._max_concurrency_spin)
        range_layout.addWidget(self._range_warning_label)
        range_layout.addStretch(1)
        form.addRow("并发范围：", range_widget)

        # 每级任务数
        self._tasks_per_level_spin = QSpinBox(group)
        self._tasks_per_level_spin.setRange(5, 100)
        self._tasks_per_level_spin.setValue(20)
        self._tasks_per_level_spin.setMinimumWidth(70)
        form.addRow("每级任务数：", self._tasks_per_level_spin)

        # 测试文本
        self._text_edit = QTextEdit(group)
        self._text_edit.setPlainText(_DEFAULT_TEXT_SAMPLE)
        self._text_edit.setMinimumHeight(60)
        self._text_edit.setMinimumWidth(300)
        form.addRow("测试文本：", self._text_edit)

        # 提前终止
        self._early_stop_check = QCheckBox("扫描到拐点即停止", group)
        self._early_stop_check.setChecked(True)
        form.addRow("", self._early_stop_check)

        return group

    def _build_control_layout(self) -> QHBoxLayout:
        """构建底部控制区：进度条 + 状态标签 + 按钮组。"""
        layout = QHBoxLayout()

        # 进度条
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setMinimumWidth(150)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # 状态标签
        self._status_label = QLabel("就绪", self)
        self._status_label.setMinimumWidth(200)
        layout.addWidget(self._status_label, 1)  # 拉伸因子 1

        # 开始测试按钮
        self._start_btn = QPushButton("开始测试", self)
        self._start_btn.setMinimumWidth(90)
        self._start_btn.clicked.connect(self._on_start)
        layout.addWidget(self._start_btn)

        # 取消按钮（初始禁用）
        self._cancel_btn = QPushButton("取消", self)
        self._cancel_btn.setMinimumWidth(70)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

        # 应用推荐值按钮（初始禁用，测试完成后启用）
        self._apply_btn = QPushButton("应用推荐值", self)
        self._apply_btn.setMinimumWidth(100)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply_recommended)
        layout.addWidget(self._apply_btn)

        return layout

    def _set_default_tool_type(self, tool_type: ToolType) -> None:
        """预选传入的工具类型；不可选时回退到第一项（balcon）。"""
        for i in range(self._tool_combo.count()):
            if self._tool_combo.itemData(i) is tool_type:
                self._tool_combo.setCurrentIndex(i)
                return
        if self._tool_combo.count() > 0:
            self._tool_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # 槽函数
    # ------------------------------------------------------------------
    def _on_max_concurrency_changed(self, value: int) -> None:
        """并发上限变化时，超过 12 显示警告文本。"""
        if value > _WARN_CONCURRENCY:
            self._range_warning_label.setText(
                f">{_WARN_CONCURRENCY} 可能不稳定"
            )
        else:
            self._range_warning_label.setText("")

    def _on_start(self) -> None:
        """开始测试：校验参数、构建配置、连接信号、延迟启动 benchmark。"""
        # 校验并发范围
        min_c = self._min_concurrency_spin.value()
        max_c = self._max_concurrency_spin.value()
        if min_c > max_c:
            QMessageBox.warning(
                self, "参数错误", "并发范围下限不能大于上限。"
            )
            return

        # 校验工具类型可用性
        tool_type: ToolType = self._tool_combo.currentData()
        if tool_type is ToolType.SAPI and (
            not _SAPI_AVAILABLE or self._sapi_config is None
        ):
            QMessageBox.warning(
                self,
                "SAPI5 不可用",
                "SAPI5 模块未加载（pywin32 未安装），无法测试 SAPI5。",
            )
            return

        # 构建 BenchmarkConfig
        self._config = BenchmarkConfig(
            tool_type=tool_type,
            min_concurrency=min_c,
            max_concurrency=max_c,
            tasks_per_level=self._tasks_per_level_spin.value(),
            text_sample=self._text_edit.toPlainText() or _DEFAULT_TEXT_SAMPLE,
            early_stop=self._early_stop_check.isChecked(),
        )

        # 重置状态
        self._results.clear()
        self._chart.clear()
        self._optimal_concurrency = 0
        total_levels = max_c - min_c + 1
        self._progress_bar.setRange(0, total_levels)
        self._progress_bar.setValue(0)

        # 实例化 benchmark 并连接信号
        self._benchmark = ConcurrencyBenchmark(self)
        self._benchmark.level_started.connect(self._on_level_started)
        self._benchmark.level_finished.connect(self._on_level_finished)
        self._benchmark.progress_updated.connect(self._on_progress_updated)
        self._benchmark.all_finished.connect(self._on_all_finished)
        self._benchmark.error.connect(self._on_error)

        # 切换按钮状态
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._apply_btn.setEnabled(False)

        # 延迟调用，让 UI 先刷新（run 内部使用嵌套 QEventLoop，
        # UI 仍可响应 cancel 按钮点击等事件）
        config = self._config
        QTimer.singleShot(
            0, lambda: self._benchmark.run(config, self._task_factory)
        )

    def _on_level_started(self, level: int) -> None:
        """某并发级开始：更新状态标签。"""
        self._status_label.setText(f"正在测试并发数 {level}…")

    def _on_level_finished(self, level: int, result: BenchmarkResult) -> None:
        """某并发级完成：追加数据点并实时更新图表。"""
        self._results.append(result)
        # 实时更新图表（optimal 暂为 0，不绘制绿色竖线）
        self._chart.set_data(self._results, 0)

    def _on_progress_updated(self, current: int, total: int) -> None:
        """进度更新：设置进度条范围与当前值。"""
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current + 1)

    def _on_all_finished(self, results: list, optimal: int) -> None:
        """全部完成：更新图表与状态标签，切换按钮状态。"""
        self._results = list(results)
        self._optimal_concurrency = optimal

        # 更新图表（含最优并发数绿色竖线）
        self._chart.set_data(self._results, optimal)

        # 进度条置满
        total = self._progress_bar.maximum()
        self._progress_bar.setValue(total)

        # 状态标签显示推荐结果
        if results:
            optimal_result = next(
                (r for r in results if r.concurrency == optimal), None
            )
            if optimal_result is not None:
                self._status_label.setText(
                    f"推荐并发数：{optimal}"
                    f"（吞吐量 {optimal_result.throughput:.2f} tasks/s，"
                    f"p95 {optimal_result.p95_latency:.1f} ms）"
                )
            else:
                self._status_label.setText(f"推荐并发数：{optimal}")
        else:
            self._status_label.setText("未采集到结果")

        # 切换按钮状态
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._apply_btn.setEnabled(True)

    def _on_error(self, message: str) -> None:
        """测试发生异常：恢复按钮状态并弹窗提示。"""
        self._status_label.setText(f"错误：{message}")
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        QMessageBox.critical(self, "测试错误", message)

    def _on_cancel(self) -> None:
        """取消测试：请求 benchmark 终止并禁用取消按钮。"""
        if self._benchmark is not None:
            self._benchmark.cancel()
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("正在取消…")

    def _on_apply_recommended(self) -> None:
        """应用推荐值：发射信号并关闭对话框。"""
        self.apply_concurrency.emit(self._optimal_concurrency)
        self.accept()

    # ------------------------------------------------------------------
    # task_factory
    # ------------------------------------------------------------------
    def _task_factory(
        self, concurrency: int, level_idx: int, temp_dir: str
    ) -> list:
        """创建单级测试任务列表。

        为每个任务写入临时 .txt 文件，创建 :class:`BalconTask` 或
        :class:`SapiTask`（固定输出 WAV，避免转码干扰时延测量）。

        Args:
            concurrency: 当前并发数。
            level_idx: 当前级索引（0-based，未直接使用但保留以匹配回调签名）。
            temp_dir: 临时目录路径。

        Returns:
            任务列表（长度为 :attr:`BenchmarkConfig.tasks_per_level`）。
        """
        tasks = []
        config = self._config
        text = config.text_sample

        for i in range(config.tasks_per_level):
            # 写入临时文本文件
            txt_path = os.path.join(temp_dir, f"bench_c{concurrency}_t{i}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)

            # 输出 WAV 路径
            wav_path = os.path.join(temp_dir, f"bench_c{concurrency}_t{i}.wav")

            # 根据工具类型创建任务（固定 WAV 输出）
            if config.tool_type is ToolType.SAPI:
                task = SapiTask(
                    input_file=txt_path,
                    config=self._sapi_config,  # type: ignore[arg-type]
                    output_path=wav_path,
                    index=i,
                    output_format=AudioFormat.WAV,
                )
            else:
                task = BalconTask(
                    input_file=txt_path,
                    config=self._balcon_config,
                    output_path=wav_path,
                    balcon_path=self._balcon_path,
                    index=i,
                    output_format=AudioFormat.WAV,
                )
            tasks.append(task)

        return tasks


__all__ = ["BenchmarkDialog"]
