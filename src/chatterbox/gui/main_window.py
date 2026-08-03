"""主窗口模块。

定义 :class:`MainWindow`，整合文件列表、参数 Tab、进度与日志面板，
通过 :class:`chatterbox.core.task_scheduler.TaskScheduler` 调度
:class:`chatterbox.core.worker.BalconTask` 批量执行 TTS 转换。

约束：
- 使用 PySide6（QMainWindow、QToolBar、QSplitter、QTabWidget 等）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
- 仅通过 ``core/`` 层接口与 balcon 子进程交互，不直接调用 subprocess。
"""
from __future__ import annotations

import copy
import logging
import os
import os.path
import threading

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.audio_encoder import AudioFormat, clear_ffmpeg_cache
from chatterbox.core.balcon_runner import (
    build_command_preview,
    list_devices,
    list_voices,
)
from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.blb2txt_runner import build_blb2txt_command_preview
from chatterbox.core.blb2txt_worker import Blb2txtTask
from chatterbox.core.checkpoint import CheckpointManager, CheckpointState
from chatterbox.core.config import BalconConfig
from chatterbox.core.filename_template import render_output_path
from chatterbox.core.task_scheduler import TaskScheduler
from chatterbox.core.tool_type import ProcessPriority, ToolType
# SAPI5 相关模块可能不可用（sapi_worker/sapi_runner 依赖 pywin32），
# 使用 try/except 延迟导入避免硬依赖。SapiConfig 本身不依赖 pywin32，
# 但为统一管理仍放入同一 try/except 块。
try:
    from chatterbox.core.sapi_config import SapiConfig
    from chatterbox.core.sapi_worker import SapiTask
    from chatterbox.core.sapi_runner import (
        SapiError as sapi_SapiError,
        init_com as sapi_init_com,
        list_voices as sapi_list_voices,
        uninit_thread_com as sapi_uninit_thread_com,
    )
    _SAPI_AVAILABLE = True
except ImportError:  # noqa: E402 - 可选依赖，缺失时置 None
    SapiConfig = None  # type: ignore[assignment,misc]
    SapiTask = None  # type: ignore[assignment,misc]
    sapi_SapiError = None  # type: ignore[assignment,misc]
    sapi_init_com = None  # type: ignore[assignment,misc]
    sapi_list_voices = None  # type: ignore[assignment,misc]
    sapi_uninit_thread_com = None  # type: ignore[assignment,misc]
    _SAPI_AVAILABLE = False
from chatterbox.core.worker import BalconTask
from chatterbox.gui.dialogs.benchmark_dialog import BenchmarkDialog
from chatterbox.gui.dialogs.shortcuts_dialog import ShortcutItem, ShortcutsDialog
from chatterbox.gui.tabs import TabRegistry
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.theme.theme_manager import ThemeManager
from chatterbox.gui.widgets.command_palette import Command, CommandPalette
from chatterbox.gui.widgets.file_list_widget import FileListWidget
from chatterbox.gui.widgets.icon_provider import IconProvider
from chatterbox.gui.widgets.inline_indicator import InlineIndicator
from chatterbox.gui.widgets.log_panel import LogPanel
from chatterbox.gui.widgets.progress_widget import ProgressWidget
from chatterbox.gui.widgets.sidebar_tab_widget import SidebarTabWidget
from chatterbox.persistence.preset import load_preset, save_preset
from chatterbox.persistence.settings import AppSettings
from chatterbox.utils.signals import bridge_logging_to_signal

logger = logging.getLogger(__name__)

# 模块级标记：日志桥接是否已建立，避免重复注册回调导致日志重复输出。
_logging_bridged = False


def _ensure_logging_bridge() -> None:
    """确保标准库日志已桥接到 Qt 信号。

    多次调用安全：仅首次调用时注册回调。
    """
    global _logging_bridged
    if not _logging_bridged:
        bridge_logging_to_signal()
        _logging_bridged = True


class _EnumWorker(QObject):
    """语音/设备枚举异步工作者。

    在 Python 守护线程中调用 :func:`list_voices` / :func:`list_devices`，
    通过 Qt 信号将结果派发回主线程。Qt 信号机制在跨线程发射时会自动
    排队到接收线程，确保槽函数在主线程执行。

    Signals:
        voices_ready(list): 语音列表枚举完成，参数为 ``list[str]``。
        devices_ready(list): 设备列表枚举完成，参数为 ``list[tuple[int, str]]``。
        error(str): 枚举失败，参数为错误信息。
    """

    voices_ready = Signal(list)
    devices_ready = Signal(list)
    error = Signal(str)

    def enumerate(self, balcon_path: str) -> None:
        """启动后台线程执行枚举。

        Args:
            balcon_path: balcon.exe 路径。
        """
        threading.Thread(
            target=self._run, args=(balcon_path,), daemon=True
        ).start()

    def _run(self, balcon_path: str) -> None:
        """工作线程主体：依次枚举语音与设备，发射结果信号。"""
        try:
            voices = list_voices(balcon_path)
            self.voices_ready.emit(voices)
        except Exception as exc:  # noqa: BLE001 - 捕获所有异常避免线程崩溃
            self.error.emit(f"枚举语音失败: {exc}")

        try:
            devices = list_devices(balcon_path)
            self.devices_ready.emit(devices)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"枚举设备失败: {exc}")


class SettingsDialog(QDialog):
    """设置对话框：配置 balcon.exe / blb2txt.exe 路径与最大并发数。"""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        """构建对话框 UI。

        包含路径行（带内联校验指示器）、并发数（带内联警告）、
        外观分组（主题/密度/字号缩放/动画开关）与按钮行（重置/确定/取消）。
        """
        layout = QFormLayout(self)

        # balcon 路径行
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(self._settings.balcon_path, self)
        browse_btn = QPushButton("浏览…", self)
        browse_btn.clicked.connect(self._on_browse)
        self.path_indicator = InlineIndicator(self)
        self.path_edit.textChanged.connect(self._validate_balcon_path_inline)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(self.path_indicator)
        layout.addRow("balcon.exe 路径：", path_row)

        # blb2txt 主版本路径行
        blb2txt_row = QHBoxLayout()
        self.blb2txt_path_edit = QLineEdit(self._settings.blb2txt_path, self)
        blb2txt_browse_btn = QPushButton("浏览…", self)
        blb2txt_browse_btn.clicked.connect(self._on_browse_blb2txt)
        self.blb2txt_path_indicator = InlineIndicator(self)
        self.blb2txt_path_edit.textChanged.connect(
            self._validate_blb2txt_path_inline
        )
        blb2txt_row.addWidget(self.blb2txt_path_edit, 1)
        blb2txt_row.addWidget(blb2txt_browse_btn)
        blb2txt_row.addWidget(self.blb2txt_path_indicator)
        layout.addRow("blb2txt.exe 路径：", blb2txt_row)

        # blb2txt 精简版本路径行
        blb2txt_lite_row = QHBoxLayout()
        self.blb2txt_lite_path_edit = QLineEdit(
            self._settings.blb2txt_lite_path, self
        )
        blb2txt_lite_browse_btn = QPushButton("浏览…", self)
        blb2txt_lite_browse_btn.clicked.connect(self._on_browse_blb2txt_lite)
        self.blb2txt_lite_path_indicator = InlineIndicator(self)
        self.blb2txt_lite_path_edit.textChanged.connect(
            self._validate_blb2txt_lite_path_inline
        )
        blb2txt_lite_row.addWidget(self.blb2txt_lite_path_edit, 1)
        blb2txt_lite_row.addWidget(blb2txt_lite_browse_btn)
        blb2txt_lite_row.addWidget(self.blb2txt_lite_path_indicator)
        layout.addRow("blb2txt 精简版路径：", blb2txt_lite_row)

        # 并发数（含内联警告指示器）
        self.concurrency_spin = QSpinBox(self)
        self.concurrency_spin.setRange(1, 16)
        self.concurrency_spin.setValue(self._settings.max_concurrency)
        self.concurrency_spin.setToolTip(
            "并发数超过 12 会显示内联警告。建议 ≤8 以保证系统响应"
        )
        # 并发数 >12 警告：可能导致系统崩溃，本程序不负责
        self.concurrency_spin.valueChanged.connect(self._on_concurrency_changed)
        self.concurrency_indicator = InlineIndicator(self)
        concurrency_container = QVBoxLayout()
        concurrency_container.setContentsMargins(0, 0, 0, 0)
        concurrency_container.addWidget(self.concurrency_spin)
        concurrency_container.addWidget(self.concurrency_indicator)
        concurrency_widget = QWidget(self)
        concurrency_widget.setLayout(concurrency_container)
        layout.addRow("最大并发数：", concurrency_widget)

        # 子进程优先级（balcon + ffmpeg）
        self.priority_combo = QComboBox(self)
        self.priority_combo.setToolTip(
            "设置 balcon.exe 与 ffmpeg 子进程的 Windows 优先级。\n"
            "低于正常/空闲适合后台批量转换，减少对系统响应的影响；\n"
            "高于正常/高优先级适合需要快速完成的场景，但可能影响其他程序。"
        )
        for pri in ProcessPriority:
            self.priority_combo.addItem(pri.display_name, pri.value)
        self._set_combo_by_data(self.priority_combo, self._settings.process_priority)
        layout.addRow("子进程优先级：", self.priority_combo)

        # 外观分组：主题 / 密度 / 字号缩放 / 动画开关
        self.appearance_group = QGroupBox("外观", self)
        appearance_layout = QFormLayout(self.appearance_group)

        self.theme_combo = QComboBox(self.appearance_group)
        self.theme_combo.addItem("亮色", "light")
        self.theme_combo.addItem("暗色", "dark")
        self.theme_combo.addItem("跟随系统", "auto")
        self._set_combo_by_data(self.theme_combo, self._settings.theme)
        appearance_layout.addRow("主题：", self.theme_combo)

        self.density_combo = QComboBox(self.appearance_group)
        self.density_combo.addItem("舒适", "comfortable")
        self.density_combo.addItem("紧凑", "compact")
        self._set_combo_by_data(self.density_combo, self._settings.density)
        appearance_layout.addRow("密度：", self.density_combo)

        # 字号缩放滑块（0.85 ~ 1.30，步长 0.01）
        font_row = QHBoxLayout()
        self.font_scale_slider = QSlider(
            Qt.Orientation.Horizontal, self.appearance_group
        )
        self.font_scale_slider.setRange(85, 130)
        self.font_scale_slider.setSingleStep(1)
        self.font_scale_slider.setValue(
            int(round(self._settings.font_scale * 100))
        )
        self.font_scale_label = QLabel(
            f"{self._settings.font_scale:.2f}", self.appearance_group
        )
        self.font_scale_label.setMinimumWidth(40)
        self.font_scale_slider.valueChanged.connect(
            lambda v: self.font_scale_label.setText(f"{v / 100:.2f}")
        )
        font_row.addWidget(self.font_scale_slider, 1)
        font_row.addWidget(self.font_scale_label)
        appearance_layout.addRow("字号缩放：", font_row)

        # 动画开关（迁移自原隐式开关 disable_animations）
        self.animations_checkbox = QCheckBox(
            "禁用动画（降低动效，适合性能敏感场景）",
            self.appearance_group,
        )
        self.animations_checkbox.setChecked(self._settings.disable_animations)
        appearance_layout.addRow("", self.animations_checkbox)

        layout.addRow(self.appearance_group)

        # 按钮行：重置为默认 / 确定 / 取消
        button_row = QHBoxLayout()
        self.reset_button = QPushButton("重置为默认", self)
        self.reset_button.clicked.connect(self._on_reset_to_defaults)
        ok_btn = QPushButton("确定", self)
        cancel_btn = QPushButton("取消", self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.reset_button)
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addRow(button_row)

        self.setLayout(layout)

        # 初始触发内联路径校验
        self._validate_balcon_path_inline()
        self._validate_blb2txt_path_inline()
        self._validate_blb2txt_lite_path_inline()

    # ------------------------------------------------------------------
    # 内联校验与外观辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        """按 itemData 匹配值设置 comboBox 当前项；未匹配时不修改。"""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _validate_path_inline(
        self, edit: QLineEdit, indicator: InlineIndicator
    ) -> None:
        """通用路径内联校验：空值隐藏，存在显示 ✓，不存在显示 ✗。"""
        path = edit.text().strip()
        if not path:
            indicator.set_state("hidden")
            return
        if os.path.isfile(path):
            indicator.set_state("ok", "", "路径有效")
        else:
            indicator.set_state("error", "", "路径不存在")

    def _validate_balcon_path_inline(self) -> None:
        """balcon 路径输入框 textChanged 槽：实时校验路径存在性。"""
        self._validate_path_inline(self.path_edit, self.path_indicator)

    def _validate_blb2txt_path_inline(self) -> None:
        """blb2txt 主版本路径输入框 textChanged 槽：实时校验路径存在性。"""
        self._validate_path_inline(
            self.blb2txt_path_edit, self.blb2txt_path_indicator
        )

    def _validate_blb2txt_lite_path_inline(self) -> None:
        """blb2txt 精简版路径输入框 textChanged 槽：实时校验路径存在性。"""
        self._validate_path_inline(
            self.blb2txt_lite_path_edit, self.blb2txt_lite_path_indicator
        )

    def _on_reset_to_defaults(self) -> None:
        """重置为默认按钮：弹确认对话框，确认后还原字段（不立即持久化）。"""
        reply = QMessageBox.question(
            self,
            "重置为默认",
            "确定要将所有设置还原为默认值吗？\n\n"
            "此操作仅还原对话框字段，不会立即持久化；\n"
            "需点击「确定」保存，或「取消」放弃修改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        defaults = AppSettings()
        self.path_edit.setText(defaults.balcon_path)
        self.blb2txt_path_edit.setText(defaults.blb2txt_path)
        self.blb2txt_lite_path_edit.setText(defaults.blb2txt_lite_path)
        self.concurrency_spin.setValue(defaults.max_concurrency)
        self._set_combo_by_data(self.priority_combo, defaults.process_priority)
        self._set_combo_by_data(self.theme_combo, defaults.theme)
        self._set_combo_by_data(self.density_combo, defaults.density)
        self.font_scale_slider.setValue(int(round(defaults.font_scale * 100)))
        self.animations_checkbox.setChecked(defaults.disable_animations)

    def _on_browse(self) -> None:
        """浏览按钮：打开文件选择对话框。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 balcon.exe",
            self.path_edit.text() or "",
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.path_edit.setText(path)

    def _on_browse_blb2txt(self) -> None:
        """blb2txt 主版本浏览按钮：打开文件选择对话框。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 blb2txt.exe",
            self.blb2txt_path_edit.text() or "",
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.blb2txt_path_edit.setText(path)

    def _on_browse_blb2txt_lite(self) -> None:
        """blb2txt 精简版浏览按钮：打开文件选择对话框。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 blb2txt 精简版 blb2txt.exe",
            self.blb2txt_lite_path_edit.text() or "",
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.blb2txt_lite_path_edit.setText(path)

    def get_balcon_path(self) -> str:
        """返回用户输入的 balcon.exe 路径。"""
        return self.path_edit.text().strip()

    def get_blb2txt_path(self) -> str:
        """返回用户输入的 blb2txt.exe 主版本路径。"""
        return self.blb2txt_path_edit.text().strip()

    def get_blb2txt_lite_path(self) -> str:
        """返回用户输入的 blb2txt 精简版路径。"""
        return self.blb2txt_lite_path_edit.text().strip()

    def get_concurrency(self) -> int:
        """返回用户设置的并发数。"""
        return self.concurrency_spin.value()

    def get_process_priority(self) -> str:
        """返回用户选择的子进程优先级（``idle``/``below_normal``/``normal``/...）。"""
        data = self.priority_combo.currentData()
        return data if isinstance(data, str) else "normal"

    def get_theme(self) -> str:
        """返回用户选择的主题（``light`` / ``dark`` / ``auto``）。"""
        data = self.theme_combo.currentData()
        return data if isinstance(data, str) else "auto"

    def get_density(self) -> str:
        """返回用户选择的密度（``comfortable`` / ``compact``）。"""
        data = self.density_combo.currentData()
        return data if isinstance(data, str) else "comfortable"

    def get_font_scale(self) -> float:
        """返回字号缩放系数（0.85 ~ 1.30）。"""
        return self.font_scale_slider.value() / 100.0

    def get_disable_animations(self) -> bool:
        """返回是否禁用动画。"""
        return self.animations_checkbox.isChecked()

    def _on_concurrency_changed(self, value: int) -> None:
        """并发数变化时检查是否超过 12，显示内联黄色警告。

        警告用户高并发可能导致系统崩溃，本程序不负责。
        不再弹 ``QMessageBox``，改为在输入框下方显示 ``InlineIndicator``
        warning 状态。

        Args:
            value: 新的并发数值。
        """
        if value <= 12:
            self.concurrency_indicator.set_state("hidden")
            return
        self.concurrency_indicator.set_state(
            "warning",
            f"并发数 {value} 超过推荐上限 12，可能导致系统资源耗尽或崩溃",
            "高并发警告：可能导致系统崩溃，本程序不负责",
        )


class _PreviewDialog(QDialog):
    """命令行预览对话框：展示完整 balcon 命令并支持复制到剪贴板。"""

    def __init__(self, command: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chatterbox 命令行预览")
        self._command = command
        self._build_ui()

    def _build_ui(self) -> None:
        """构建对话框 UI。"""
        layout = QVBoxLayout(self)

        label = QLabel("首个输入文件的 balcon 命令：", self)
        layout.addWidget(label)

        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(self._command)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text_edit)

        button_row = QHBoxLayout()
        copy_btn = QPushButton("复制到剪贴板", self)
        copy_btn.clicked.connect(self._on_copy)
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        button_row.addStretch()
        button_row.addWidget(copy_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        self.resize(600, 200)

    def _on_copy(self) -> None:
        """将命令复制到系统剪贴板。"""
        QGuiApplication.clipboard().setText(self._command)


class _ClickableLabel(QLabel):
    """可点击的 QLabel：mousePressEvent 时发射 :attr:`clicked` 信号。

    用于状态栏中段 balcon 路径标签，点击复制路径到剪贴板。
    ``Ctrl+Click`` 时额外发射 :attr:`ctrl_clicked` 信号（用于在资源管理器
    中打开所在目录），保留原 :attr:`clicked` 信号行为。
    """

    clicked = Signal()
    ctrl_clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """鼠标按下时发射 :attr:`clicked` 信号（任意按键均触发）。

        若按住 ``Ctrl`` 修饰键，额外发射 :attr:`ctrl_clicked` 信号。
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.ctrl_clicked.emit()
        super().mousePressEvent(event)


def _make_vline(parent: QWidget | None = None) -> QFrame:
    """创建竖直分隔线（QFrame VLine），用于状态栏分段视觉区分。

    保留 Qt 原版样式，不引入自定义 QSS。
    """
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setFixedWidth(2)
    return line


class MainWindow(QMainWindow):
    """balcon 批量 TTS 主窗口。

    整合文件列表、参数 Tab、进度与日志面板，通过 :class:`TaskScheduler`
    调度 :class:`BalconTask` 批量执行 TTS 转换。

    布局：
        - 顶部：:class:`QToolBar` 工具栏 + :class:`QMenuBar` 菜单栏
        - 左侧：:class:`FileListWidget` 文件列表
        - 右侧：:class:`SidebarTabWidget` 分组侧边栏 + 堆叠面板（自动加载 ``TabRegistry``）
        - 底部：:class:`ProgressWidget` 进度条 + :class:`LogPanel` 日志面板
        - 左右与上下均使用 :class:`QSplitter`，可拖拽调整大小
        - 状态栏三段式：左侧状态文本 / 中段 balcon 路径（可点击复制）/ 右侧并发与语音数
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chatterbox")
        self.resize(1280, 800)
        # 设置窗口图标（chatterbox.ico 位于项目根目录）
        _ico_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "chatterbox.ico",
        )
        if os.path.isfile(_ico_path):
            self.setWindowIcon(QIcon(_ico_path))

        # 确保日志桥接（多次调用安全）
        _ensure_logging_bridge()

        # 应用状态
        self._settings = AppSettings.load()
        self._scheduler = TaskScheduler(
            max_concurrency=self._settings.max_concurrency, parent=self
        )
        self._tabs: list[AbstractTab] = []
        self._tabs_by_id: dict[str, AbstractTab] = {}
        self._enum_worker = _EnumWorker(self)
        # succeeded/failed 计数由 ProgressWidget 作为单一计数源维护
        # （progress_updated 信号携带真实计数驱动）
        # 当前已枚举到的语音数量（_on_voices_ready 更新）
        self._voices_count: int = 0
        # 当前工具类型（balcon / blb2txt），默认 balcon
        self._current_tool: ToolType = ToolType.BALCON
        # 两套配置实例，工具切换时各自保留状态
        self._balcon_config: BalconConfig = BalconConfig.create_default()
        self._blb2txt_config: Blb2txtConfig = Blb2txtConfig.create_default()
        # SAPI5 配置实例（pywin32 不可用时为 None）
        self._sapi_config: SapiConfig | None = (
            SapiConfig.create_default() if SapiConfig is not None else None
        )
        # balcon OutputTab 的输出目录、模板、格式与 ffmpeg 路径
        # （非 BalconConfig 字段，需单独保存）
        self._balcon_output_dir: str = ""
        self._balcon_filename_template: str = "{name}.wav"
        self._balcon_output_format: AudioFormat = AudioFormat.WAV
        self._balcon_ffmpeg_path: str = ""
        # balcon OutputTab 的 VBR 质量（-1=CBR 默认，0~10=VBR 等级）
        self._balcon_vbr_quality: int = -1
        # SAPI OutputTab 的输出目录、模板、格式与 ffmpeg 路径
        # （非 SapiConfig 字段，需单独保存）
        self._sapi_output_dir: str = ""
        self._sapi_filename_template: str = "{name}.wav"
        self._sapi_output_format: AudioFormat = AudioFormat.WAV
        self._sapi_ffmpeg_path: str = ""
        # SAPI OutputTab 的 VBR 质量（-1=CBR 默认，0~10=VBR 等级）
        self._sapi_vbr_quality: int = -1
        # 断点续传管理器（运行时创建，全部完成时清除）
        self._checkpoint_mgr = None
        # T-B5：命令面板与快捷键对话框懒加载（首次触发时实例化）
        self._command_palette: CommandPalette | None = None
        self._shortcuts_dialog: ShortcutsDialog | None = None

        # T-E2：启动时应用主题/密度/字号缩放（在构建 UI 前应用，
        # 确保所有 widget 使用正确调色板与字体）
        self._apply_appearance()

        # 构建 UI
        self._build_central()
        self._build_toolbar()
        self._build_menu()
        self._create_tabs()
        self._connect_signals()
        self._apply_settings()

        # T-E2：监听 ThemeManager.theme_changed 信号，触发特殊 widget 刷新
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        # 启动校验与枚举
        self._validate_balcon_path()
        self._refresh_voices_devices()

        # 检测未完成的断点续传记录，询问用户是否恢复
        self._check_for_pending_checkpoint()

        # 设置合理的最小窗口尺寸，允许窗口自由拉伸到较小尺寸
        # （各子控件已设置 minimumWidth 确保内容可收缩）
        self.setMinimumSize(QSize(720, 500))

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_central(self) -> None:
        """构建中央部件：垂直分割（上部左右分割 + 进度 + 日志）。"""
        v_splitter = QSplitter(Qt.Orientation.Vertical, self)

        # 上部：左右分割
        h_splitter = QSplitter(Qt.Orientation.Horizontal, v_splitter)
        self.file_list_widget = FileListWidget(h_splitter)
        self.file_list_widget.setMinimumWidth(200)
        self.tab_widget = SidebarTabWidget(h_splitter)
        h_splitter.addWidget(self.file_list_widget)
        h_splitter.addWidget(self.tab_widget)
        h_splitter.setStretchFactor(0, 3)
        h_splitter.setStretchFactor(1, 7)

        # 中部：进度
        self.progress_widget = ProgressWidget(v_splitter)

        # 下部：日志
        self.log_panel = LogPanel(v_splitter)

        v_splitter.addWidget(h_splitter)
        v_splitter.addWidget(self.progress_widget)
        v_splitter.addWidget(self.log_panel)
        v_splitter.setStretchFactor(0, 6)
        v_splitter.setStretchFactor(1, 1)
        v_splitter.setStretchFactor(2, 3)

        self.setCentralWidget(v_splitter)

        # 状态栏三段式：左 status_label / 中 balcon_path_label + 路径指示器
        # / 右 concurrency_label（可点击打开设置）
        self._status_label = QLabel("就绪", self)
        self._balcon_path_label = _ClickableLabel(self)
        self._balcon_path_label.setToolTip(
            "点击复制 balcon 路径；Ctrl+点击在资源管理器中打开所在目录"
        )
        self._balcon_path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._balcon_path_label.clicked.connect(self._on_copy_balcon_path)
        # T-C6：Ctrl+Click 在资源管理器中打开所在目录
        self._balcon_path_label.ctrl_clicked.connect(self._open_path_in_explorer)
        # T-D2：路径校验内联指示器（默认隐藏，路径无效时显示红色✗）
        self._path_indicator = InlineIndicator(self)
        self._path_indicator.clicked.connect(self._on_settings)
        # T-C6：并发标签改为可点击，点击打开设置
        self._concurrency_label = _ClickableLabel("", self)
        self._concurrency_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._concurrency_label.setToolTip("点击打开设置对话框")
        self._concurrency_label.clicked.connect(self._on_settings)
        sb = self.statusBar()
        sb.addWidget(self._status_label, 1)
        sb.addWidget(_make_vline(self), 0)
        sb.addWidget(self._balcon_path_label, 2)
        sb.addWidget(self._path_indicator, 0)
        sb.addWidget(_make_vline(self), 0)
        sb.addPermanentWidget(self._concurrency_label, 0)

    def _build_toolbar(self) -> None:
        """构建顶部工具栏。

        按钮顺序：工具选择器、添加文件、移除文件、清空、刷新语音/设备、
        开始、停止、预览命令行、保存预设、加载预设、设置。
        "开始"与"停止"互斥启用，"停止"初始禁用。
        每个 QAction 同时设置图标、tooltip、状态栏提示与快捷键，
        同一 QAction 实例后续被菜单栏复用。
        """
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())
        self.addToolBar(toolbar)

        # 工具选择器（首位）：balcon TTS / blb2txt 文本提取
        self.tool_combo = QComboBox(self)
        self.tool_combo.addItem(
            IconProvider.tool_icon(ToolType.BALCON),
            ToolType.BALCON.display_name,
            ToolType.BALCON,
        )
        self.tool_combo.addItem(
            IconProvider.tool_icon(ToolType.BLB2TXT),
            ToolType.BLB2TXT.display_name,
            ToolType.BLB2TXT,
        )
        self.tool_combo.addItem(
            IconProvider.tool_icon(ToolType.SAPI),
            ToolType.SAPI.display_name,
            ToolType.SAPI,
        )
        self.tool_combo.setToolTip(
            "选择当前工具（balcon TTS 文本转语音 / blb2txt 文本提取 / "
            "SAPI5 直达 TTS）"
        )
        self.tool_combo.setStatusTip("切换当前工具")
        self.tool_combo.currentIndexChanged.connect(self._on_tool_changed)
        toolbar.addWidget(self.tool_combo)

        toolbar.addSeparator()

        # 文件操作组
        self.add_files_action = self._make_action(
            "添加文件", "add", "添加待处理文件 (Ctrl+O)", "添加文件", "Ctrl+O",
            self._on_add_files,
        )
        toolbar.addAction(self.add_files_action)

        self.remove_files_action = self._make_action(
            "移除文件", "remove", "移除选中文件 (Delete)", "移除文件", "Delete",
            self._on_remove_files,
        )
        toolbar.addAction(self.remove_files_action)

        self.clear_action = self._make_action(
            "清空", "clear", "清空文件列表 (Ctrl+Shift+Delete)", "清空文件列表",
            "Ctrl+Shift+Delete", self._on_clear_files,
        )
        toolbar.addAction(self.clear_action)

        toolbar.addSeparator()

        # 刷新组
        self.refresh_action = self._make_action(
            "刷新语音/设备", "refresh", "重新枚举语音与输出设备 (F5)",
            "刷新语音/设备", "F5", self._refresh_voices_devices,
        )
        toolbar.addAction(self.refresh_action)

        toolbar.addSeparator()

        # 执行组
        self.start_action = self._make_action(
            "开始", "start", "开始批量 TTS 转换 (Ctrl+Return)", "开始转换",
            "Ctrl+Return", self._on_start,
        )
        toolbar.addAction(self.start_action)

        self.stop_action = self._make_action(
            "停止", "stop", "停止运行中的任务 (Esc)", "停止任务", "Esc",
            self._on_stop,
        )
        self.stop_action.setEnabled(False)
        toolbar.addAction(self.stop_action)

        toolbar.addSeparator()

        # 预览
        self.preview_action = self._make_action(
            "预览命令行", "preview", "预览首个文件的 balcon 命令行 (Ctrl+P)",
            "预览命令行", "Ctrl+P", self._on_preview,
        )
        toolbar.addAction(self.preview_action)

        toolbar.addSeparator()

        # 预设组
        self.save_preset_action = self._make_action(
            "保存预设", "save", "保存当前参数为预设文件 (Ctrl+S)", "保存预设",
            "Ctrl+S", self._on_save_preset,
        )
        toolbar.addAction(self.save_preset_action)

        self.load_preset_action = self._make_action(
            "加载预设", "load", "从预设文件加载参数 (Ctrl+L)", "加载预设",
            "Ctrl+L", self._on_load_preset,
        )
        toolbar.addAction(self.load_preset_action)

        toolbar.addSeparator()

        # 设置（无快捷键）
        self.settings_action = self._make_action(
            "设置", "settings", "打开设置对话框", "设置", None, self._on_settings,
        )
        toolbar.addAction(self.settings_action)

    def _make_action(
        self,
        text: str,
        icon_name: str,
        tooltip: str,
        status_tip: str,
        shortcut: str | None,
        slot,
    ) -> QAction:
        """创建并配置一个 QAction：图标、tooltip、状态栏提示、快捷键、信号。

        Args:
            text: 菜单/工具栏显示文本。
            icon_name: :class:`IconProvider.tool_icon` 中的图标名。
            tooltip: 悬浮提示文本。
            status_tip: 鼠标悬停时状态栏显示的文本。
            shortcut: 快捷键字符串（如 ``"Ctrl+O"``），``None`` 表示不设置。
            slot: triggered 信号连接的槽函数。

        Returns:
            配置好的 :class:`QAction` 实例。
        """
        action = QAction(text, self)
        action.setIcon(IconProvider.tool_icon(icon_name))
        action.setToolTip(tooltip)
        action.setStatusTip(status_tip)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_menu(self) -> None:
        """构建菜单栏：文件 / 操作 / 视图 / 帮助 四个菜单。

        菜单项与工具栏 QAction 共用同一实例（一个 QAction 可加入多个
        菜单/工具栏）。新增的菜单专属 action（如退出、关于）独立创建。
        """
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")
        file_menu.addAction(self.add_files_action)
        add_file_list_action = QAction("添加文件列表(-fl)…", self)
        add_file_list_action.setStatusTip("从文本列表文件导入文件路径")
        add_file_list_action.triggered.connect(
            self.file_list_widget.add_file_list_dialog
        )
        file_menu.addAction(add_file_list_action)
        # T-B6：最近文件子菜单
        self._recent_files_menu: QMenu = file_menu.addMenu("最近文件")
        self._recent_files_menu.setStatusTip("最近添加的文件")
        file_menu.addSeparator()
        file_menu.addAction(self.save_preset_action)
        file_menu.addAction(self.load_preset_action)
        # T-B6：最近预设子菜单
        self._recent_presets_menu: QMenu = file_menu.addMenu("最近预设")
        self._recent_presets_menu.setStatusTip("最近加载/保存的预设")
        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.setStatusTip("退出程序")
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # T-B6：初始填充最近文件/预设子菜单
        self._refresh_recent_menus()

        # 操作菜单
        op_menu = menubar.addMenu("操作")
        op_menu.addAction(self.start_action)
        op_menu.addAction(self.stop_action)
        op_menu.addSeparator()
        op_menu.addAction(self.preview_action)
        op_menu.addAction(self.refresh_action)

        # 工具菜单
        tool_menu = menubar.addMenu("工具")
        benchmark_action = QAction("并发基准测试…", self)
        benchmark_action.setStatusTip("扫描并发范围，找到性能最大化的并发点")
        benchmark_action.triggered.connect(self._on_open_benchmark_dialog)
        tool_menu.addAction(benchmark_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图")
        clear_log_action = QAction("清空日志", self)
        clear_log_action.setStatusTip("清空日志面板内容")
        clear_log_action.triggered.connect(self.log_panel.clear_log)
        view_menu.addAction(clear_log_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.setStatusTip("关于本程序")
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _create_tabs(self) -> None:
        """从 :class:`TabRegistry` 加载当前工具的 Tab 并按分组添加到侧边栏。

        使用 :meth:`TabRegistry.get_all_tabs_grouped(self._current_tool)`
        获取按分组排序的 dict，对每个 Tab 类实例化后调用
        :meth:`SidebarTabWidget.add_tab` 添加到侧边栏与堆叠面板。

        调用前会清空 ``self._tabs`` 与 ``self._tabs_by_id``，确保工具
        切换时不残留旧 Tab 引用。
        """
        self._tabs.clear()
        self._tabs_by_id.clear()
        grouped = TabRegistry.get_all_tabs_grouped(self._current_tool)
        for group, tab_classes in grouped.items():
            for cls in tab_classes:
                tab = cls(parent=self.tab_widget)
                icon = cls.tab_icon()
                self.tab_widget.add_tab(
                    tab, group, cls.tab_title(), icon, cls.tab_description()
                )
                self._tabs.append(tab)
                self._tabs_by_id[cls.tab_id()] = tab
        logger.debug(
            "工具 %s 已加载 %d 个 Tab（分组数：%d）",
            self._current_tool.value, len(self._tabs), len(grouped),
        )

    def _connect_signals(self) -> None:
        """连接调度器与枚举工作者的信号到 UI 槽。"""
        # 调度器信号 → 进度条与日志面板
        self._scheduler.all_finished.connect(self._on_all_finished)
        # progress_updated 现携带真实 succeeded/failed（4 参数），
        # 直接驱动 ProgressWidget.update_progress 完成分段着色实时刷新
        self._scheduler.progress_updated.connect(self.progress_widget.update_progress)
        self._scheduler.task_log.connect(self.log_panel.append)
        self._scheduler.task_started.connect(self._on_task_started)
        self._scheduler.task_error.connect(self._on_task_error)
        # task_finished 仅用于日志记录（计数由 progress_updated 统一驱动）
        self._scheduler.task_finished.connect(self._on_task_finished)
        # Task 17：并发超限警告（状态栏显示）与队列深度更新（日志记录）
        self._scheduler.warning_signal.connect(self._on_scheduler_warning)
        self._scheduler.queue_depth_changed.connect(self._on_queue_depth_changed)

        # 枚举工作者信号
        self._enum_worker.voices_ready.connect(self._on_voices_ready)
        self._enum_worker.devices_ready.connect(self._on_devices_ready)
        self._enum_worker.error.connect(self._on_enum_error)

        # T-B6：文件列表变化 → 追踪新增文件加入最近文件
        self._last_files: list[str] = list(self.file_list_widget.get_files())
        self.file_list_widget.files_changed.connect(self._on_files_changed)

        # T-B5：注册全局快捷键（命令面板 / 快捷键帮助 / Tab 循环）
        self._register_shortcuts()

    # ------------------------------------------------------------------
    # 启动初始化
    # ------------------------------------------------------------------
    def _apply_settings(self) -> None:
        """加载 :class:`AppSettings` 到 UI 状态。"""
        # 调度器并发数
        self._scheduler.set_max_concurrency(self._settings.max_concurrency)

        # OutputTab 模板、输出目录、输出格式与 ffmpeg 路径
        output_tab = self._tabs_by_id.get("output")
        if output_tab is not None:
            output_tab.set_filename_template(self._settings.filename_template)
            if self._settings.last_output_dir:
                output_tab.set_output_dir(self._settings.last_output_dir)
            # 多格式输出：还原输出格式与 ffmpeg 路径
            try:
                fmt = AudioFormat(self._settings.output_format)
            except ValueError:
                fmt = AudioFormat.WAV
            output_tab.set_output_format(fmt)
            if self._settings.ffmpeg_path:
                output_tab.set_ffmpeg_path(self._settings.ffmpeg_path)
            # 还原 VBR 质量设置（-1=CBR 默认，0~10=VBR 等级）
            output_tab.set_vbr_quality(self._settings.vbr_quality)
            self._balcon_vbr_quality = self._settings.vbr_quality
        # SAPI5：从设置还原 VBR 质量到内部状态字段
        # （SapiOutputTab 在工具切换时按 _sapi_vbr_quality 还原）
        self._sapi_vbr_quality = self._settings.vbr_quality

        # 窗口几何
        if self._settings.window_geometry:
            try:
                self.restoreGeometry(
                    QByteArray.fromBase64(
                        self._settings.window_geometry.encode("ascii")
                    )
                )
            except Exception:  # noqa: BLE001
                logger.debug("恢复窗口几何失败", exc_info=True)

        self._update_status_bar()

    # ------------------------------------------------------------------
    # T-E2：主题与外观应用
    # ------------------------------------------------------------------
    def _apply_appearance(self) -> None:
        """启动时应用主题、密度与字号缩放（通过 ThemeManager）。

        T-E2：在构建 UI 前调用，确保所有 widget 使用正确调色板与字体。
        动画开关通过 AnimationManager 同步禁用状态。
        """
        mgr = ThemeManager.instance()
        try:
            mgr.apply_theme(self._settings.theme)
        except Exception:  # noqa: BLE001
            logger.debug("应用主题失败", exc_info=True)
        try:
            mgr.apply_density(self._settings.density)
        except Exception:  # noqa: BLE001
            logger.debug("应用密度失败", exc_info=True)
        try:
            mgr.apply_font_scale(self._settings.font_scale)
        except Exception:  # noqa: BLE001
            logger.debug("应用字号缩放失败", exc_info=True)
        # 同步动画开关
        try:
            from chatterbox.gui.widgets.animation_manager import (
                AnimationManager,
            )

            AnimationManager.instance().set_enabled(
                not self._settings.disable_animations
            )
        except (ImportError, AttributeError):
            logger.debug("AnimationManager 不可用，跳过动画开关同步")

    def _on_theme_changed(self, theme: str) -> None:
        """ThemeManager.theme_changed 信号槽：触发特殊 widget 刷新。

        T-E2：主题切换后，对状态栏指示器、进度条等依赖调色板的 widget
        调用 update() 强制重绘，确保颜色令牌实时生效。
        """
        # 刷新路径指示器颜色（重新设置当前状态以应用新主题颜色）
        if self._current_tool is ToolType.BALCON:
            self._update_path_indicator(self._balcon_path_valid(), "balcon")
        elif self._current_tool is ToolType.SAPI:
            # SAPI5 无需路径校验，确保指示器隐藏
            self._path_indicator.set_state("hidden")
        else:
            self._update_path_indicator(self._blb2txt_path_valid(), "blb2txt")
        # 强制刷新关键 widget
        for widget in (
            self._balcon_path_label,
            self._concurrency_label,
            self._status_label,
            self.progress_widget,
        ):
            try:
                widget.update()
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # 断点续传：启动检测与恢复
    # ------------------------------------------------------------------
    def _check_for_pending_checkpoint(self) -> None:
        """启动时检测未完成的断点续传记录，询问用户是否恢复。

        检测 ``last_output_dir`` 目录下的 checkpoint 文件，若存在且
        包含未完成文件，弹出对话框询问用户：
        - "是"：恢复未完成文件列表到文件列表控件
        - 勾选框"同时恢复历史转换参数"：额外将 config_snapshot 应用到 Tab
        - "否"：不恢复，checkpoint 文件保留

        用户选择"是"后会切换到 checkpoint 记录的工具类型，确保 Tab 匹配。
        """
        # 从 last_output_dir 检测 checkpoint
        output_dir = self._settings.last_output_dir or ""
        if not output_dir or not os.path.isdir(output_dir):
            return

        mgr = CheckpointManager(output_dir)
        if not mgr.exists():
            return

        state = mgr.load()
        if state is None:
            return

        pending = state.pending_files()
        if not pending:
            # 无未完成文件，清除残留 checkpoint
            mgr.clear()
            logger.info("checkpoint 无未完成文件，已清除残留记录")
            return

        # 弹出恢复对话框
        restore_config, accepted = self._show_checkpoint_dialog(state, pending)
        if not accepted:
            logger.info("用户选择不恢复断点续传记录")
            return

        # 执行恢复
        self._load_checkpoint_state(state, restore_config, mgr)

    def _show_checkpoint_dialog(
        self, state: CheckpointState, pending: list[str]
    ) -> tuple[bool, bool]:
        """弹出断点续传恢复对话框。

        Args:
            state: checkpoint 状态。
            pending: 未完成文件列表。

        Returns:
            ``(restore_config, accepted)`` 元组：
            - ``restore_config``：用户是否勾选"同时恢复历史转换参数"。
            - ``accepted``：用户是否点击"是"（恢复）。
        """
        tool_name_map = {
            "balcon": "balcon TTS",
            "blb2txt": "blb2txt 文本提取",
            "sapi": "SAPI5 直达 TTS",
        }
        tool_name = tool_name_map.get(state.tool_type, state.tool_type)
        total = len(state.input_files)
        has_config = state.has_config_snapshot()

        dialog = QDialog(self)
        dialog.setWindowTitle("检测到未完成的任务")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        info_label = QLabel(
            f"在输出目录中检测到未完成的{tool_name}任务：\n\n"
            f"  总文件数：{total}\n"
            f"  已完成：{len(state.completed_files)}\n"
            f"  已失败：{len(state.failed_files)}\n"
            f"  待处理：{len(pending)}\n\n"
            f"创建时间：{state.created_at}\n"
            f"更新时间：{state.updated_at}\n\n"
            f"是否恢复未完成的任务？",
            dialog,
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # "同时恢复历史转换参数"勾选框
        config_checkbox = QCheckBox(
            "同时恢复历史转换参数（覆盖当前 Tab 配置）", dialog
        )
        config_checkbox.setChecked(has_config)
        config_checkbox.setEnabled(has_config)
        if not has_config:
            config_checkbox.setText(
                "同时恢复历史转换参数（无可用参数快照）"
            )
        layout.addWidget(config_checkbox)

        # 按钮行
        button_row = QHBoxLayout()
        yes_btn = QPushButton("是，恢复", dialog)
        no_btn = QPushButton("否，不恢复", dialog)
        yes_btn.clicked.connect(dialog.accept)
        no_btn.clicked.connect(dialog.reject)
        button_row.addStretch()
        button_row.addWidget(yes_btn)
        button_row.addWidget(no_btn)
        layout.addLayout(button_row)

        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        restore_config = config_checkbox.isChecked() and has_config
        return restore_config, accepted

    def _load_checkpoint_state(
        self,
        state: CheckpointState,
        restore_config: bool,
        mgr: CheckpointManager,
    ) -> None:
        """加载 checkpoint 状态，恢复文件列表与（可选）配置参数。

        Args:
            state: checkpoint 状态。
            restore_config: 是否恢复历史转换参数。
            mgr: :class:`CheckpointManager` 实例，用于后续进度跟踪。
        """
        # 1. 切换到 checkpoint 记录的工具类型（支持 balcon/blb2txt/sapi）
        try:
            target_tool = ToolType(state.tool_type)
        except ValueError:
            logger.warning(
                "checkpoint 工具类型 %r 未知，回退到 balcon",
                state.tool_type,
            )
            target_tool = ToolType.BALCON
        if target_tool is not self._current_tool:
            # 通过 comboBox 切换工具（触发 _on_tool_changed）
            for i in range(self.tool_combo.count()):
                item_data = self.tool_combo.itemData(i)
                tool = item_data if isinstance(item_data, ToolType) else ToolType(item_data)
                if tool is target_tool:
                    self.tool_combo.setCurrentIndex(i)
                    break

        # 2. 恢复文件列表（仅未完成文件）
        pending = state.pending_files()
        # 过滤出仍存在的文件
        existing_pending = [f for f in pending if os.path.isfile(f)]
        missing = [f for f in pending if not os.path.isfile(f)]
        if missing:
            logger.warning(
                "以下 %d 个文件已不存在，跳过：%s",
                len(missing),
                ", ".join(missing[:5]),
            )
        if existing_pending:
            self.file_list_widget.add_files(existing_pending)

        # 3. 恢复配置参数（若用户勾选）
        if restore_config and state.has_config_snapshot():
            self._apply_config_snapshot(state.config_snapshot, target_tool)

        # 4. 恢复输出设置（balcon / SAPI5）
        if target_tool is ToolType.BALCON:
            output_tab = self._tabs_by_id.get("output")
            if output_tab is not None:
                if state.output_dir:
                    output_tab.set_output_dir(state.output_dir)
                if state.filename_template:
                    output_tab.set_filename_template(state.filename_template)
                try:
                    fmt = AudioFormat(state.output_format)
                except ValueError:
                    fmt = AudioFormat.WAV
                output_tab.set_output_format(fmt)
                if state.ffmpeg_path:
                    output_tab.set_ffmpeg_path(state.ffmpeg_path)
        elif target_tool is ToolType.SAPI:
            # SapiOutputTab 使用 property 接口，需通过控件 setText 还原
            output_tab = self._tabs_by_id.get("sapi_output")
            if output_tab is not None:
                if state.output_dir:
                    output_tab.output_dir_edit.setText(state.output_dir)
                if state.filename_template:
                    output_tab.template_edit.setText(state.filename_template)
                try:
                    fmt = AudioFormat(state.output_format)
                except ValueError:
                    fmt = AudioFormat.WAV
                fmt_idx = output_tab.format_combo.findData(fmt)
                if fmt_idx >= 0:
                    output_tab.format_combo.setCurrentIndex(fmt_idx)
                if state.ffmpeg_path:
                    output_tab.ffmpeg_edit.setText(state.ffmpeg_path)

        # 5. 绑定 checkpoint 到调度器（后续任务完成时自动更新进度）
        self._checkpoint_mgr = mgr
        self._scheduler.attach_checkpoint(mgr)
        logger.info(
            "已恢复断点续传记录：待处理 %d 个文件，恢复参数：%s",
            len(existing_pending),
            "是" if restore_config else "否",
        )
        self._status_label.setText(
            f"{self._status_prefix()}已恢复 {len(existing_pending)} 个待处理文件"
        )

    def _apply_config_snapshot(
        self, snapshot: dict, tool_type: ToolType
    ) -> None:
        """将 config_snapshot 应用到当前 Tab 的配置。

        Args:
            snapshot: ``BalconConfig.to_dict()`` / ``Blb2txtConfig.to_dict()`` /
                ``SapiConfig.to_dict()`` 的结果。
            tool_type: 工具类型，决定使用哪个 Config 类反序列化。
        """
        if not snapshot:
            return
        try:
            if tool_type is ToolType.BALCON:
                cfg = BalconConfig.from_dict(snapshot)
                self._balcon_config = cfg
            elif tool_type is ToolType.SAPI:
                if SapiConfig is None:
                    logger.warning(
                        "SAPI5 配置类不可用，跳过 config_snapshot 恢复"
                    )
                    return
                cfg = SapiConfig.from_dict(snapshot)
                self._sapi_config = cfg
            else:
                cfg = Blb2txtConfig.from_dict(snapshot)
                self._blb2txt_config = cfg
            for tab in self._tabs:
                tab.apply_config(cfg)
            logger.info("已从 checkpoint 恢复 %s 配置参数", tool_type.value)
        except Exception:  # noqa: BLE001
            logger.warning("从 checkpoint 恢复配置参数失败", exc_info=True)

    def _validate_balcon_path(self) -> bool:
        """校验 balcon.exe 路径，无效时更新状态栏指示器并禁用"开始"按钮。

        T-D2：不再弹 ``QMessageBox``，改为更新状态栏中段的
        :class:`InlineIndicator`（红色✗ + 「balcon 路径无效，点击修复」），
        点击指示器调用 :meth:`_on_settings` 打开设置对话框。

        Returns:
            路径是否有效。
        """
        valid = self._balcon_path_valid()
        if self._current_tool is ToolType.BALCON:
            self._update_path_indicator(valid, "balcon")
        # 仅在非运行状态时更新"开始"按钮
        if not self._scheduler.is_running():
            if self._current_tool is ToolType.SAPI:
                # SAPI5 模式不依赖 balcon 路径
                self.start_action.setEnabled(True)
            else:
                self.start_action.setEnabled(valid)
        return valid

    def _balcon_path_valid(self) -> bool:
        """返回 balcon.exe 路径是否有效（非空且文件存在）。"""
        path = self._settings.balcon_path
        return bool(path) and os.path.isfile(path)

    def _refresh_voices_devices(self) -> None:
        """异步触发语音与设备枚举，避免阻塞主线程。

        SAPI5 模式下不走 balcon.exe 枚举，改为直接调用 pywin32 COM
        接口枚举系统 SAPI5 语音（同步调用，COM 调用通常 <100ms）。
        """
        if self._current_tool is ToolType.SAPI:
            if not _SAPI_AVAILABLE or sapi_list_voices is None:
                logger.warning(
                    "SAPI5 不可用（pywin32 未安装），跳过语音枚举"
                )
                self.statusBar().showMessage(
                    "SAPI5 不可用（pywin32 未安装）", 3000
                )
                return
            self.statusBar().showMessage("正在枚举 SAPI5 语音…", 3000)
            try:
                # 主线程短暂初始化 COM 枚举语音（幂等，主线程首次调用实际初始化）
                sapi_init_com()
                voices = sapi_list_voices()
                self._voices_count = len(voices)
                for tab in self._tabs:
                    tab.refresh_voices(voices)
                logger.info("已刷新 SAPI5 语音列表：共 %d 个", len(voices))
                self._update_status_bar()
            except Exception as e:  # noqa: BLE001
                logger.warning("SAPI5 语音枚举失败: %s", e)
                self.statusBar().showMessage(
                    f"SAPI5 语音枚举失败: {e}", 3000
                )
            finally:
                # 主线程不长期持有 SpVoice，清理 COM（删除 thread_local.voice + CoUninitialize）
                sapi_uninit_thread_com()
            return
        if not self._balcon_path_valid():
            logger.warning("balcon 路径无效，跳过语音/设备枚举")
            return
        self._enum_worker.enumerate(self._settings.balcon_path)
        self.statusBar().showMessage("正在枚举语音/设备…", 3000)

    def _update_status_bar(self) -> None:
        """更新状态栏三段式部件的文本。

        - 左：``_status_label`` 显示当前状态（如"就绪"、"运行中"）。
        - 中：``_balcon_path_label`` 显示当前工具的可执行文件路径。
        - 右：``_concurrency_label`` 显示并发数与语音数。

        临时状态消息（如"正在处理: xxx.wav"）由调用方通过
        :meth:`statusBar().showMessage` 设置，不影响永久部件。
        """
        if self._current_tool is ToolType.BALCON:
            tool_path = self._settings.balcon_path or "(未配置)"
            self._balcon_path_label.setText(f"balcon: {tool_path}")
            self._balcon_path_label.setToolTip(
                f"点击复制 balcon 路径\n当前路径: {tool_path}"
            )
        elif self._current_tool is ToolType.SAPI:
            # SAPI5 无外部 exe，状态栏中段显示工具说明
            self._balcon_path_label.setText("SAPI5 直达 TTS")
            self._balcon_path_label.setToolTip(
                "SAPI5 通过 COM 接口直调，无需外部可执行文件"
            )
        else:
            tool_path = self._settings.blb2txt_path or "(未配置)"
            self._balcon_path_label.setText(f"blb2txt: {tool_path}")
            self._balcon_path_label.setToolTip(
                f"点击复制 blb2txt 路径\n当前路径: {tool_path}"
            )
        self._concurrency_label.setText(
            f"并发: {self._settings.max_concurrency} | "
            f"语音: {self._voices_count}"
        )

    def _status_prefix(self) -> str:
        """返回状态栏文本的工具前缀（按当前工具类型差异化）。"""
        if self._current_tool is ToolType.BLB2TXT:
            return "[文本提取] "
        if self._current_tool is ToolType.SAPI:
            return "[SAPI5] "
        return ""

    @staticmethod
    def _ensure_template_extension(
        template: str, fmt: AudioFormat
    ) -> str:
        """确保文件名模板的扩展名与输出格式一致。

        若模板以已知音频扩展名结尾（如 ``.wav``、``.mp3``），替换为
        ``fmt`` 对应的扩展名；否则不修改（用户可能使用了 ``{ext}`` 占位符
        或自定义扩展名）。

        Args:
            template: 原始模板字符串。
            fmt: 目标输出格式。

        Returns:
            调整后的模板字符串。
        """
        if not template:
            return template
        lower = template.lower()
        for known in AudioFormat:
            ext = f".{known.extension}"
            if lower.endswith(ext):
                ext_start = len(template) - len(ext)
                return template[:ext_start] + f".{fmt.extension}"
        return template

    def emergency_save_checkpoint(self) -> None:
        """紧急保存断点续传记录（GUI 崩溃前调用）。

        委托给 :class:`TaskScheduler.emergency_save_checkpoint`，若调度器
        未绑定 checkpoint 则 no-op。
        """
        try:
            self._scheduler.emergency_save_checkpoint()
        except Exception:  # noqa: BLE001
            logger.warning("紧急保存断点续传失败", exc_info=True)

    def _blb2txt_path_valid(self) -> bool:
        """返回 blb2txt.exe 路径是否有效（非空且文件存在）。"""
        path = self._settings.blb2txt_path
        return bool(path) and os.path.isfile(path)

    def _validate_blb2txt_path(self) -> bool:
        """校验 blb2txt.exe 路径，无效时更新状态栏指示器并禁用"开始"按钮。

        T-D2：不再弹 ``QMessageBox``，改为更新状态栏中段的
        :class:`InlineIndicator`（红色✗ + 「blb2txt 路径无效，点击修复」），
        点击指示器调用 :meth:`_on_settings` 打开设置对话框。

        Returns:
            路径是否有效。
        """
        valid = self._blb2txt_path_valid()
        if self._current_tool is ToolType.BLB2TXT:
            self._update_path_indicator(valid, "blb2txt")
        if not self._scheduler.is_running():
            if self._current_tool is ToolType.SAPI:
                # SAPI5 模式不依赖 blb2txt 路径
                self.start_action.setEnabled(True)
            else:
                self.start_action.setEnabled(valid)
        return valid

    def _update_path_indicator(self, valid: bool, tool_name: str) -> None:
        """根据路径有效性更新状态栏中段的路径校验指示器。

        T-D2：路径有效时隐藏指示器；无效时显示红色✗ + 提示文本，
        点击调用 :meth:`_on_settings` 打开设置对话框修复。

        Args:
            valid: 路径是否有效。
            tool_name: 工具名（``"balcon"`` 或 ``"blb2txt"``），用于提示文本。
        """
        if valid:
            self._path_indicator.set_state("hidden")
        else:
            self._path_indicator.set_state(
                "error",
                f"{tool_name} 路径无效，点击修复",
                f"未找到 {tool_name} 可执行文件，点击打开设置对话框配置正确路径",
            )

    def _open_path_in_explorer(self) -> None:
        """Ctrl+Click 状态栏路径标签：在系统资源管理器中打开所在目录。

        T-C6：使用 ``os.startfile`` 打开当前工具可执行文件所在目录。
        路径为空或目录不存在时在状态栏显示提示，不弹对话框。
        SAPI5 模式无外部 exe，提示无路径可打开。
        """
        if self._current_tool is ToolType.BALCON:
            path = self._settings.balcon_path
        elif self._current_tool is ToolType.SAPI:
            self.statusBar().showMessage("SAPI5 无外部路径", 2000)
            return
        else:
            path = self._settings.blb2txt_path
        if not path:
            self.statusBar().showMessage("未配置路径", 2000)
            return
        directory = os.path.dirname(path) or "."
        if not os.path.isdir(directory):
            self.statusBar().showMessage("所在目录不存在", 2000)
            return
        try:
            os.startfile(directory)  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            logger.warning("无法打开资源管理器：%s", directory, exc_info=True)
            self.statusBar().showMessage("无法打开资源管理器", 2000)

    def _on_tool_changed(self, index: int) -> None:
        """工具选择器切换槽：保存当前配置、清空侧边栏、加载新工具 Tab。

        流程：
            1. 从 comboBox itemData 获取新 ToolType，与当前相同则返回。
            2. 收集当前工具的 Tab 配置到对应 config 实例
               （balcon → ``_balcon_config``，blb2txt → ``_blb2txt_config``）。
            3. 设置 ``_current_tool`` 为新工具。
            4. 清空侧边栏（``tab_widget.clear()``）。
            5. 调用 :meth:`_create_tabs` 按新工具重新填充 Tab。
            6. 调用 :meth:`file_list_widget.set_tool` 更新文件过滤器。
            7. 从对应 config 实例恢复 Tab 状态（``apply_config``）。
            8. 更新状态栏与"开始"按钮启用状态。

        Args:
            index: comboBox 当前项索引。

        注意:
            ``QComboBox.itemData`` 经 PySide6 QVariant 转换后，``ToolType``
            （继承自 ``str``）会被降级为普通字符串。此处通过
            :func:`ToolType` 构造函数将字符串值还原为枚举实例，确保
            ``self._current_tool`` 始终为 :class:`ToolType`。
        """
        if index < 0:
            return
        raw = self.tool_combo.itemData(index)
        if raw is None:
            return
        # PySide6 QVariant 将 ToolType(str, Enum) 降级为 str，需还原。
        new_tool = raw if isinstance(raw, ToolType) else ToolType(raw)
        if new_tool is self._current_tool:
            return

        # 1. 收集当前工具的 Tab 配置到对应 config 实例
        if self._current_tool is ToolType.BALCON:
            cfg = BalconConfig.create_default()
            for tab in self._tabs:
                tab.collect_config(cfg)
            self._balcon_config = cfg
            # 保存 OutputTab 的输出目录、模板、格式与 ffmpeg 路径
            output_tab = self._tabs_by_id.get("output")
            if output_tab is not None:
                self._balcon_output_dir = output_tab.get_output_dir()
                self._balcon_filename_template = output_tab.get_filename_template()
                self._balcon_output_format = output_tab.get_output_format()
                self._balcon_ffmpeg_path = output_tab.get_ffmpeg_path()
                # 保存 VBR 质量设置
                self._balcon_vbr_quality = output_tab.get_vbr_quality()
        elif self._current_tool is ToolType.SAPI:
            # SAPI5：收集 SapiConfig 与 SapiOutputTab 的输出设置
            if SapiConfig is not None:
                cfg = SapiConfig.create_default()
                for tab in self._tabs:
                    tab.collect_config(cfg)
                self._sapi_config = cfg
            # 保存 SapiOutputTab 的输出目录、模板、格式与 ffmpeg 路径
            output_tab = self._tabs_by_id.get("sapi_output")
            if output_tab is not None:
                self._sapi_output_dir = output_tab.output_dir
                self._sapi_filename_template = output_tab.filename_template
                self._sapi_output_format = output_tab.output_format
                self._sapi_ffmpeg_path = output_tab.ffmpeg_path
                # 保存 VBR 质量设置
                self._sapi_vbr_quality = output_tab.get_vbr_quality()
        else:  # BLB2TXT
            cfg = Blb2txtConfig.create_default()
            for tab in self._tabs:
                tab.collect_config(cfg)
            self._blb2txt_config = cfg

        # 2. 切换工具
        self._current_tool = new_tool

        # 3. 清空侧边栏并重新创建 Tab
        self.tab_widget.clear()
        self._create_tabs()

        # 4. 更新文件列表过滤器
        self.file_list_widget.set_tool(new_tool)

        # 5. 从对应 config 实例恢复 Tab 状态
        if new_tool is ToolType.BALCON:
            for tab in self._tabs:
                tab.apply_config(self._balcon_config)
            # 恢复 OutputTab 的输出目录、模板、格式与 ffmpeg 路径
            output_tab = self._tabs_by_id.get("output")
            if output_tab is not None:
                output_tab.set_output_dir(self._balcon_output_dir)
                output_tab.set_filename_template(self._balcon_filename_template)
                # 多格式输出：还原输出格式与 ffmpeg 路径
                fmt = getattr(self, "_balcon_output_format", AudioFormat.WAV)
                output_tab.set_output_format(fmt)
                ffmpeg_p = getattr(self, "_balcon_ffmpeg_path", "")
                if ffmpeg_p:
                    output_tab.set_ffmpeg_path(ffmpeg_p)
                # 还原 VBR 质量设置
                output_tab.set_vbr_quality(self._balcon_vbr_quality)
        elif new_tool is ToolType.SAPI:
            # SAPI5：恢复 SapiConfig 与 SapiOutputTab 的输出设置
            if self._sapi_config is not None:
                for tab in self._tabs:
                    tab.apply_config(self._sapi_config)
            # 恢复 SapiOutputTab 的输出目录、模板、格式与 ffmpeg 路径
            output_tab = self._tabs_by_id.get("sapi_output")
            if output_tab is not None:
                output_tab.output_dir_edit.setText(self._sapi_output_dir)
                output_tab.template_edit.setText(self._sapi_filename_template)
                # 还原输出格式
                fmt_idx = output_tab.format_combo.findData(self._sapi_output_format)
                if fmt_idx >= 0:
                    output_tab.format_combo.setCurrentIndex(fmt_idx)
                if self._sapi_ffmpeg_path:
                    output_tab.ffmpeg_edit.setText(self._sapi_ffmpeg_path)
                # 还原 VBR 质量设置
                output_tab.set_vbr_quality(self._sapi_vbr_quality)
        else:  # BLB2TXT
            for tab in self._tabs:
                tab.apply_config(self._blb2txt_config)

        # 6. 更新状态栏与"开始"按钮
        self._status_label.setText(f"{self._status_prefix()}就绪")
        self._update_status_bar()
        if new_tool is ToolType.BALCON:
            self.start_action.setEnabled(self._balcon_path_valid())
        elif new_tool is ToolType.SAPI:
            # SAPI5 无需外部 exe，开始按钮始终启用（文件列表非空检查在 _on_start_sapi）
            self.start_action.setEnabled(True)
            # 切换到 SAPI5 时枚举系统语音列表（启动时 _current_tool 为 BALCON，
            # 不会走 SAPI5 枚举路径，故在此补充触发，确保语音下拉框有内容）。
            # 使用 QTimer.singleShot 延迟调用，让 UI 先完成切换刷新。
            QTimer.singleShot(0, self._refresh_voices_devices)
        else:
            self.start_action.setEnabled(self._blb2txt_path_valid())

        logger.info("工具已切换为 %s", new_tool.display_name)

    # ------------------------------------------------------------------
    # 工具栏槽：文件操作
    # ------------------------------------------------------------------
    def _on_add_files(self) -> None:
        """添加文件：委托给 :class:`FileListWidget`。"""
        self.file_list_widget.add_files_dialog()

    def _on_remove_files(self) -> None:
        """移除选中文件：委托给 :class:`FileListWidget`。"""
        self.file_list_widget.remove_selected()

    def _on_clear_files(self) -> None:
        """清空文件列表：委托给 :class:`FileListWidget`。"""
        self.file_list_widget.clear_all()

    # ------------------------------------------------------------------
    # 工具栏槽：执行
    # ------------------------------------------------------------------
    def _build_extra_encode_args(self, output_tab: AbstractTab) -> list[str] | None:
        """从输出 Tab 读取 VBR 质量设置，构建 ffmpeg 额外编码参数。

        当 VBR 质量值 >= 0 时返回 ``["-q:a", str(quality)]``，
        为 -1（CBR 默认）时返回 ``None``（由 :func:`build_encode_args`
        自动应用格式默认参数 320kbps CBR）。

        Args:
            output_tab: 输出 Tab 实例（OutputTab 或 SapiOutputTab）。

        Returns:
            额外编码参数列表或 ``None``。
        """
        try:
            vbr_quality = output_tab.get_vbr_quality()
        except AttributeError:
            return None
        if vbr_quality < 0:
            return None
        return ["-q:a", str(vbr_quality)]

    def _on_start(self) -> None:
        """开始按钮：收集配置、校验、创建任务并提交到调度器。

        根据当前工具创建 :class:`BalconTask` 或 :class:`Blb2txtTask` 列表：
        - balcon 模式：按模板渲染输出路径，创建 BalconTask。
        - blb2txt 模式：按文件扩展名自动选用 blb2txt_path（PDF）或
          blb2txt_lite_path（非 PDF），输出路径基于 -v 输出目录或 -out
          输出文件，创建 Blb2txtTask。
        """
        if self._scheduler.is_running():
            QMessageBox.warning(self, "正在运行", "已有任务正在运行，请先停止。")
            return

        if self._current_tool is ToolType.SAPI:
            self._on_start_sapi()
        elif self._current_tool is ToolType.BLB2TXT:
            self._on_start_blb2txt()
        else:
            self._on_start_balcon()

    def _on_start_balcon(self) -> None:
        """balcon 模式开始：收集配置、创建 BalconTask 列表并提交。"""
        # 1. 调用所有 Tab 的 collect_config 收集配置
        cfg = BalconConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)

        # 2. 校验配置
        errors = cfg.validate()
        if errors:
            QMessageBox.warning(
                self,
                "配置校验失败",
                "以下参数存在问题：\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return

        # 3. 获取输入文件列表
        files = self.file_list_widget.get_files()
        if not files:
            QMessageBox.warning(self, "无输入文件", "请先添加待处理的文件。")
            return

        # 4. 校验 balcon 路径
        if not self._balcon_path_valid():
            self._validate_balcon_path()
            return

        # 5. 从 OutputTab 获取输出目录、模板、输出格式与 ffmpeg 路径
        output_tab = self._tabs_by_id.get("output")
        if output_tab is None:
            QMessageBox.critical(self, "内部错误", "未找到输出 Tab。")
            return
        output_dir = output_tab.get_output_dir()
        template = output_tab.get_filename_template() or "{name}.wav"
        output_format = output_tab.get_output_format()
        ffmpeg_path = output_tab.get_ffmpeg_path() or None
        voice = cfg.n_voice or ""
        balcon_path = self._settings.balcon_path

        # 5.1 非 WAV 格式时校验 ffmpeg 可用
        if output_format.needs_ffmpeg:
            from chatterbox.core.audio_encoder import validate_ffmpeg

            try:
                validate_ffmpeg(ffmpeg_path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    "ffmpeg 不可用",
                    f"输出格式 {output_format.value.upper()} 需要 ffmpeg，"
                    f"但校验失败：\n\n{exc}\n\n"
                    "请在「输出」Tab 中指定 ffmpeg 路径，或将 ffmpeg "
                    "添加到 PATH。",
                )
                return

        # 5.2 根据输出格式调整模板扩展名（避免 .wav 模板生成 .mp3 文件名不匹配）
        if output_format.needs_ffmpeg:
            template = self._ensure_template_extension(template, output_format)

        # 5.3 delete_file 二次确认：勾选后开始批次前弹确认对话框
        if cfg.delete_file:
            reply = QMessageBox.question(
                self,
                "确认",
                "⚠ 即将删除输入文件，此操作不可恢复。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 6. 遍历输入文件，按模板渲染输出路径，创建 BalconTask
        tasks: list[BalconTask] = []
        for idx, input_file in enumerate(files, start=1):
            output_path = render_output_path(
                template, input_file, voice, idx, output_dir
            )
            task = BalconTask(
                input_file=input_file,
                config=cfg,
                output_path=output_path,
                balcon_path=balcon_path,
                index=idx,
                output_format=output_format,
                ffmpeg_path=ffmpeg_path,
                process_priority=self._settings.process_priority,
                extra_encode_args=self._build_extra_encode_args(output_tab),
            )
            tasks.append(task)

        # 6.5 创建断点续传 checkpoint（保存到输出目录）
        checkpoint_mgr = CheckpointManager(output_dir)
        checkpoint_state = CheckpointState(
            tool_type="balcon",
            input_files=list(files),
            output_dir=output_dir,
            filename_template=template,
            output_format=output_format.value,
            ffmpeg_path=ffmpeg_path or "",
            config_snapshot=cfg.to_dict(),
        )
        checkpoint_mgr.create(checkpoint_state)
        self._checkpoint_mgr = checkpoint_mgr
        self._scheduler.attach_checkpoint(checkpoint_mgr)
        logger.info("已创建断点续传记录点: %s", checkpoint_mgr.checkpoint_path)

        # 7. 设置进度条总数并提交到调度器
        self.progress_widget.set_total(len(tasks))
        # succeeded/failed 计数由 ProgressWidget 维护（progress_updated
        # 信号携带真实计数驱动，set_total 已重置为 0）
        try:
            self._scheduler.submit(tasks)
        except RuntimeError as exc:
            QMessageBox.critical(self, "调度错误", str(exc))
            return

        # 8. 切换按钮状态："开始"禁用、"停止"启用
        self._set_running_state(True)
        # 进度面板状态灯切换为运行中
        self.progress_widget.set_state("running")
        self._status_label.setText(f"{self._status_prefix()}运行中")
        logger.info("已提交 %d 个 balcon 任务到调度器", len(tasks))

    def _on_start_blb2txt(self) -> None:
        """blb2txt 模式开始：收集配置、创建 Blb2txtTask 列表并提交。

        路径自动选用逻辑：
            - PDF 文件（``.pdf`` 扩展名，不区分大小写）→ ``blb2txt_path``
            - 非 PDF 文件且 ``blb2txt_lite_path`` 非空 → ``blb2txt_lite_path``
            - 否则 → ``blb2txt_path``（兜底）

        输出路径基于 ``-v`` 输出目录或 ``-out`` 输出文件；两者均未设置时
        为 ``None``（由 blb2txt 默认行为决定输出位置）。
        """
        # 1. 收集 blb2txt 配置
        cfg = Blb2txtConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)
        self._blb2txt_config = cfg

        # 2. 校验配置
        errors = cfg.validate()
        if errors:
            QMessageBox.warning(
                self,
                "配置校验失败",
                "以下参数存在问题：\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return

        # 3. 获取输入文件列表
        files = self.file_list_widget.get_files()
        if not files:
            QMessageBox.warning(self, "无输入文件", "请先添加待处理的文件。")
            return

        # 4. 校验 blb2txt 路径
        if not self._blb2txt_path_valid():
            self._validate_blb2txt_path()
            return

        # 5. 遍历输入文件，按扩展名选用 blb2txt_path 或 blb2txt_lite_path
        tasks: list[Blb2txtTask] = []
        for idx, input_file in enumerate(files, start=1):
            ext = os.path.splitext(input_file)[1].lower()
            if ext == ".pdf":
                selected_path = self._settings.blb2txt_path
            elif self._settings.blb2txt_lite_path:
                selected_path = self._settings.blb2txt_lite_path
            else:
                selected_path = self._settings.blb2txt_path

            # 输出路径：基于 -v 输出目录或 -out 输出文件
            if cfg.v_output:
                base = os.path.splitext(os.path.basename(input_file))[0]
                ext_out = cfg.ext_extension or "txt"
                output_path = os.path.join(cfg.v_output, f"{base}.{ext_out}")
            elif cfg.out_file:
                output_path = cfg.out_file
            else:
                output_path = None

            task = Blb2txtTask(
                input_file=input_file,
                config=cfg,
                output_path=output_path,
                blb2txt_path=selected_path,
                index=idx,
            )
            tasks.append(task)

        # 6. 创建断点续传 checkpoint（保存到 -v 输出目录或 -out 输出文件所在目录）
        # 确定输出目录用于存放 checkpoint 文件
        checkpoint_dir = cfg.v_output or ""
        if not checkpoint_dir and cfg.out_file:
            checkpoint_dir = os.path.dirname(cfg.out_file) or "."
        if not checkpoint_dir:
            checkpoint_dir = "."
        checkpoint_mgr = CheckpointManager(checkpoint_dir)
        checkpoint_state = CheckpointState(
            tool_type="blb2txt",
            input_files=list(files),
            output_dir=checkpoint_dir,
            filename_template="",
            output_format="txt",
            ffmpeg_path="",
            config_snapshot=cfg.to_dict(),
        )
        checkpoint_mgr.create(checkpoint_state)
        self._checkpoint_mgr = checkpoint_mgr
        self._scheduler.attach_checkpoint(checkpoint_mgr)
        logger.info("已创建断点续传记录点: %s", checkpoint_mgr.checkpoint_path)

        # 7. 设置进度条总数并提交到调度器
        self.progress_widget.set_total(len(tasks))
        try:
            self._scheduler.submit(tasks)
        except RuntimeError as exc:
            QMessageBox.critical(self, "调度错误", str(exc))
            return

        # 8. 切换按钮状态
        self._set_running_state(True)
        self.progress_widget.set_state("running")
        self._status_label.setText(f"{self._status_prefix()}运行中")
        logger.info("已提交 %d 个 blb2txt 任务到调度器", len(tasks))

    def _on_start_sapi(self) -> None:
        """SAPI5 直达 TTS 模式开始：收集配置、创建 SapiTask 列表并提交。

        SAPI5 通过 pywin32 直调 COM 接口，无需外部 exe。WAV 格式直接
        输出到文件；非 WAV 格式通过 SpMemoryStream → ffmpeg 管道转码。
        """
        # 0. 校验 SAPI5 可用性
        if not _SAPI_AVAILABLE or SapiTask is None or SapiConfig is None:
            QMessageBox.critical(
                self,
                "SAPI5 不可用",
                "SAPI5 模块加载失败（通常是 pywin32 未安装）。\n"
                "请安装 pywin32 后重试：pip install pywin32",
            )
            return

        # 1. 获取输入文件列表
        files = self.file_list_widget.get_files()
        if not files:
            QMessageBox.warning(self, "无输入文件", "请先添加待处理的文件。")
            return

        # 2. 收集 SapiConfig（SapiVoiceTab + SapiOutputTab 的 input_encoding）
        cfg = SapiConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)
        self._sapi_config = cfg

        # 3. 从 SapiOutputTab 读取输出设置（property 接口）
        output_tab = self._tabs_by_id.get("sapi_output")
        if output_tab is None:
            QMessageBox.critical(self, "内部错误", "未找到 SAPI 输出 Tab。")
            return
        output_dir = output_tab.output_dir
        template = output_tab.filename_template or "{name}.wav"
        output_format = output_tab.output_format
        ffmpeg_path = output_tab.ffmpeg_path or None

        # 4. 非 WAV 格式时校验 ffmpeg 可用
        if output_format.needs_ffmpeg:
            from chatterbox.core.audio_encoder import validate_ffmpeg

            try:
                validate_ffmpeg(ffmpeg_path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    "ffmpeg 不可用",
                    f"输出格式 {output_format.value.upper()} 需要 ffmpeg，"
                    f"但校验失败：\n\n{exc}\n\n"
                    "请在「输出设置」Tab 中指定 ffmpeg 路径，或将 ffmpeg "
                    "添加到 PATH。",
                )
                return

        # 5. 根据输出格式调整模板扩展名
        if output_format.needs_ffmpeg:
            template = self._ensure_template_extension(template, output_format)

        # 6. 遍历输入文件，按模板渲染输出路径，创建 SapiTask
        tasks: list[SapiTask] = []
        for idx, input_file in enumerate(files, start=1):
            output_path = render_output_path(
                template, input_file, cfg.voice_name or "", idx, output_dir
            )
            task = SapiTask(
                input_file=input_file,
                config=cfg,
                output_path=output_path,
                index=idx,
                output_format=output_format,
                ffmpeg_path=ffmpeg_path,
                process_priority=self._settings.process_priority,
                extra_encode_args=self._build_extra_encode_args(output_tab),
            )
            tasks.append(task)

        # 7. 创建断点续传 checkpoint（保存到输出目录）
        checkpoint_mgr = CheckpointManager(output_dir)
        checkpoint_state = CheckpointState(
            tool_type="sapi",
            input_files=list(files),
            output_dir=output_dir,
            filename_template=template,
            output_format=output_format.value,
            ffmpeg_path=ffmpeg_path or "",
            config_snapshot=cfg.to_dict(),
        )
        checkpoint_mgr.create(checkpoint_state)
        self._checkpoint_mgr = checkpoint_mgr
        self._scheduler.attach_checkpoint(checkpoint_mgr)
        logger.info("已创建断点续传记录点: %s", checkpoint_mgr.checkpoint_path)

        # 8. 设置进度条总数并提交到调度器
        self.progress_widget.set_total(len(tasks))
        try:
            self._scheduler.submit(tasks)
        except RuntimeError as exc:
            QMessageBox.critical(self, "调度错误", str(exc))
            return

        # 9. 切换按钮状态
        self._set_running_state(True)
        self.progress_widget.set_state("running")
        self._status_label.setText(f"{self._status_prefix()}运行中")
        logger.info("已提交 %d 个 SAPI5 任务到调度器", len(tasks))

    def _on_stop(self) -> None:
        """停止按钮：取消所有任务并切换按钮状态。"""
        self._scheduler.cancel_all()
        self._set_running_state(False)
        logger.info("已请求停止所有任务")

    def _on_preview(self) -> None:
        """预览命令行：展示首个输入文件的完整命令。

        根据当前工具使用对应 runner 构建命令预览：
        - balcon 模式：使用 :func:`build_command_preview`。
        - blb2txt 模式：使用 :func:`build_blb2txt_command_preview`。
        - SAPI5 模式：无命令行，显示参数摘要对话框。
        """
        files = self.file_list_widget.get_files()
        if not files:
            QMessageBox.warning(
                self, "无输入文件", "请先添加待处理的文件以预览命令行。"
            )
            return

        if self._current_tool is ToolType.SAPI:
            self._on_preview_sapi(files)
        elif self._current_tool is ToolType.BLB2TXT:
            self._on_preview_blb2txt(files)
        else:
            self._on_preview_balcon(files)

    def _on_preview_balcon(self, files: list[str]) -> None:
        """balcon 模式预览：构建首个文件的 balcon 命令行（含转码链路）。"""
        if not self._balcon_path_valid():
            self._validate_balcon_path()
            return

        # 收集配置
        cfg = BalconConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)

        # 渲染首个文件的输出路径
        input_file = files[0]
        output_tab = self._tabs_by_id.get("output")
        if output_tab is not None:
            output_dir = output_tab.get_output_dir()
            template = output_tab.get_filename_template() or "{name}.wav"
            output_format = output_tab.get_output_format()
            ffmpeg_path = output_tab.get_ffmpeg_path() or None
        else:
            output_dir = ""
            template = "{name}.wav"
            output_format = AudioFormat.WAV
            ffmpeg_path = None
        voice = cfg.n_voice or ""

        # 非 WAV 格式：调整模板扩展名 + 生成临时 WAV 路径
        if output_format.needs_ffmpeg:
            template = self._ensure_template_extension(template, output_format)

        output_path = render_output_path(
            template, input_file, voice, 1, output_dir
        )

        # 构建命令行（与 BalconTask 内部逻辑一致）
        task_config = copy.copy(cfg)
        task_config.f_files = [input_file]

        commands: list[str] = []
        if output_format.is_wav:
            # WAV：balcon 直接输出到最终路径
            task_config.w_output = output_path
            args = task_config.to_args()
            commands.append(
                build_command_preview(self._settings.balcon_path, args)
            )
        else:
            # 非 WAV：balcon 输出临时 WAV，再由 ffmpeg 转码
            directory = os.path.dirname(output_path) or "."
            filename = os.path.basename(output_path)
            temp_wav = os.path.join(directory, f".{filename}.tmp.wav")
            task_config.w_output = temp_wav
            args = task_config.to_args()
            commands.append(
                build_command_preview(self._settings.balcon_path, args)
            )

            # ffmpeg 转码命令行预览
            from chatterbox.core.audio_encoder import (
                build_encode_args,
                build_encode_preview,
            )

            encode_args = build_encode_args(
                src_wav=temp_wav,
                dst_path=output_path,
                fmt=output_format,
            )
            ffmpeg_preview_path = ffmpeg_path or "ffmpeg"
            commands.append(
                build_encode_preview(ffmpeg_preview_path, encode_args)
            )

        dialog = _PreviewDialog("\n".join(commands), self)
        dialog.exec()

    def _on_preview_blb2txt(self, files: list[str]) -> None:
        """blb2txt 模式预览：构建首个文件的 blb2txt 命令行。

        按首个文件扩展名选用 ``blb2txt_path``（PDF）或
        ``blb2txt_lite_path``（非 PDF，若非空）。
        """
        # 收集 blb2txt 配置
        cfg = Blb2txtConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)

        # 按首个文件扩展名选用 blb2txt 路径
        input_file = files[0]
        ext = os.path.splitext(input_file)[1].lower()
        if ext == ".pdf":
            preview_path = self._settings.blb2txt_path
        elif self._settings.blb2txt_lite_path:
            preview_path = self._settings.blb2txt_lite_path
        else:
            preview_path = self._settings.blb2txt_path

        # 构建命令行（与 Blb2txtTask._build_args 内部逻辑一致）
        task_config = copy.deepcopy(cfg)
        if not task_config.i_stdin:
            task_config.f_files = [input_file]
        args = task_config.to_args()
        command = build_blb2txt_command_preview(preview_path, args)

        dialog = _PreviewDialog(command, self)
        dialog.setWindowTitle("blb2txt 命令行预览")
        dialog.exec()

    def _on_preview_sapi(self, files: list[str]) -> None:
        """SAPI5 模式预览：无命令行，显示参数摘要对话框。

        SAPI5 通过 COM 直调，无命令行可预览。改为展示 SapiConfig 参数
        摘要 + SapiOutputTab 输出设置 + 首个文件的渲染输出路径。
        """
        # 收集 SapiConfig
        if SapiConfig is None:
            QMessageBox.critical(
                self, "预览失败", "SAPI5 配置类不可用（pywin32 未安装）"
            )
            return
        cfg = SapiConfig.create_default()
        for tab in self._tabs:
            tab.collect_config(cfg)

        # 从 SapiOutputTab 读取输出设置
        output_tab = self._tabs_by_id.get("sapi_output")
        if output_tab is not None:
            output_dir = output_tab.output_dir
            template = output_tab.filename_template or "{name}.wav"
            output_format = output_tab.output_format
            ffmpeg_path = output_tab.ffmpeg_path
            input_encoding = cfg.input_encoding
        else:
            output_dir = ""
            template = "{name}.wav"
            output_format = AudioFormat.WAV
            ffmpeg_path = ""
            input_encoding = cfg.input_encoding

        # 调整模板扩展名
        if output_format.needs_ffmpeg:
            template = self._ensure_template_extension(template, output_format)

        # 渲染首个文件的输出路径
        input_file = files[0]
        output_path = render_output_path(
            template, input_file, cfg.voice_name or "", 1, output_dir
        )

        # 构造参数摘要文本
        preview_lines = [
            "工具: SAPI5 直达 TTS（COM 接口，无命令行）",
            "",
            "—— SAPI5 参数 ——",
            f"语音: {cfg.voice_name or '(系统默认)'}",
            f"语速: {cfg.rate}（范围 -10~10, 0=正常）",
            f"音量: {cfg.volume}（范围 0~100, 100=最大）",
            f"音调: {cfg.pitch}（范围 -10~10, 0=正常, 通过 SAPI5 XML 标记实现）",
            f"输入编码: {input_encoding}",
            "",
            "—— 输出设置 ——",
            f"输出目录: {output_dir or '(与输入文件同目录)'}",
            f"文件名模板: {template}",
            f"输出格式: {output_format.value.upper()}"
            + ("（需 ffmpeg）" if output_format.needs_ffmpeg else ""),
            f"ffmpeg 路径: {ffmpeg_path or '(自动查找)'}",
            "",
            "—— 首个文件 ——",
            f"输入: {input_file}",
            f"输出: {output_path}",
        ]
        dialog = _PreviewDialog("\n".join(preview_lines), self)
        dialog.setWindowTitle("SAPI5 参数预览")
        dialog.exec()

    # ------------------------------------------------------------------
    # 工具栏槽：预设
    # ------------------------------------------------------------------
    def _on_save_preset(self) -> None:
        """保存预设：收集配置，排除会话字段，写入 JSON 文件。

        根据当前工具类型选择对应的 Config 类收集配置，并将
        ``self._current_tool.value`` 作为 ``tool_type`` 写入预设，
        以便加载时正确分派反序列化逻辑。
        """
        if self._current_tool is ToolType.BALCON:
            cfg = BalconConfig.create_default()
        elif self._current_tool is ToolType.BLB2TXT:
            cfg = Blb2txtConfig.create_default()
        elif self._current_tool is ToolType.SAPI:
            if SapiConfig is None:
                QMessageBox.critical(self, "保存失败", "SAPI 配置类不可用")
                return
            cfg = SapiConfig.create_default()
        else:
            QMessageBox.critical(
                self, "保存失败", f"未知工具类型：{self._current_tool}"
            )
            return
        for tab in self._tabs:
            tab.collect_config(cfg)
        # 排除会话特定信息：输入文件列表（仅清除存在的字段）
        if hasattr(cfg, "f_files"):
            cfg.f_files = []
        if hasattr(cfg, "fl_files"):
            cfg.fl_files = []

        default_dir = self._settings.last_preset_dir or ""
        default_path = (
            os.path.join(default_dir, "preset.json") if default_dir else "preset.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存预设",
            default_path,
            "预设文件 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            save_preset(path, cfg, self._current_tool.value)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"保存预设失败：{exc}")
            return
        self._settings.last_preset_dir = os.path.dirname(path)
        try:
            self._settings.save()
        except OSError as exc:
            logger.warning("保存设置失败：%s", exc)
        # T-B6：保存预设成功后加入最近预设
        self._add_recent_preset(path)
        logger.info("预设已保存到 %s", path)

    def _on_load_preset(self) -> None:
        """加载预设：从 JSON 读取并对所有 Tab 调用 apply_config。

        根据 ``tool_type`` 选择对应 Config 类反序列化；若与当前工具不同，
        先切换到该工具再应用配置。
        """
        default_dir = self._settings.last_preset_dir or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载预设",
            default_dir,
            "预设文件 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            tool_type_str, params = load_preset(path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "加载失败", f"加载预设失败：{exc}")
            return
        cfg = self._build_preset_config(tool_type_str, params)
        if cfg is None:
            QMessageBox.critical(
                self, "加载失败", f"无法应用预设工具类型：{tool_type_str}"
            )
            return
        # 预设工具类型与当前不同时切换工具（会重建 Tab）
        target_tool = ToolType(tool_type_str)
        if target_tool is not self._current_tool:
            self._switch_tool(target_tool)
        for tab in self._tabs:
            tab.apply_config(cfg)
        self._settings.last_preset_dir = os.path.dirname(path)
        try:
            self._settings.save()
        except OSError as exc:
            logger.warning("保存设置失败：%s", exc)
        # T-B6：加载预设成功后加入最近预设
        self._add_recent_preset(path)
        logger.info("已从 %s 加载预设", path)

    def _build_preset_config(self, tool_type_str: str, params: dict):
        """根据 tool_type 字符串选择对应 Config 类从 params 重建实例。

        Args:
            tool_type_str: 工具类型字符串（如 ``"balcon"``、``"blb2txt"``）。
            params: 预设参数字典。

        Returns:
            对应工具的 Config 实例；若工具类型未知或 SapiConfig 不可用，
            返回 ``None``。
        """
        try:
            tool_type = ToolType(tool_type_str)
        except ValueError:
            logger.warning("未知预设工具类型：%r", tool_type_str)
            return None
        if tool_type is ToolType.BALCON:
            return BalconConfig.from_dict(params)
        if tool_type is ToolType.BLB2TXT:
            return Blb2txtConfig.from_dict(params)
        if tool_type is ToolType.SAPI:
            if SapiConfig is None:
                logger.warning("SAPI 配置类不可用，无法加载预设")
                return None
            return SapiConfig.from_dict(params)
        logger.warning("不支持的预设工具类型：%r", tool_type_str)
        return None

    # ------------------------------------------------------------------
    # T-B6：最近文件/预设管理
    # ------------------------------------------------------------------
    def _on_files_changed(self, files: list[str]) -> None:
        """文件列表变化槽：将新增文件加入最近文件列表。

        通过与 ``_last_files`` 差集比较，仅对新出现的文件调用
        :meth:`_add_recent_file`，避免重复添加与删除时误触发。
        """
        old_set = set(getattr(self, "_last_files", []))
        for f in files:
            if f not in old_set:
                self._add_recent_file(f)
        self._last_files = list(files)

    def _add_recent_file(self, path: str) -> None:
        """将文件路径加入最近文件列表首位（去重，保留前 10 项）。

        Args:
            path: 文件绝对路径。
        """
        if not path:
            return
        recent = self._settings.recent_files
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        del recent[10:]
        self._refresh_recent_menus()

    def _add_recent_preset(self, path: str) -> None:
        """将预设路径加入最近预设列表首位（去重，保留前 10 项）。

        Args:
            path: 预设文件绝对路径。
        """
        if not path:
            return
        recent = self._settings.recent_presets
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        del recent[10:]
        self._refresh_recent_menus()

    def _refresh_recent_menus(self) -> None:
        """根据 ``AppSettings.recent_files`` / ``recent_presets`` 填充子菜单。

        列表为空时显示禁用的「（无）」占位项；非空时每项为一个 QAction，
        点击触发对应加载逻辑（文件添加到列表 / 预设加载到 Tab）。
        """
        # 最近文件子菜单
        self._recent_files_menu.clear()
        recent_files = self._settings.recent_files
        if not recent_files:
            empty_action = QAction("（无）", self)
            empty_action.setEnabled(False)
            self._recent_files_menu.addAction(empty_action)
        else:
            for path in recent_files:
                action = QAction(path, self)
                action.setStatusTip(f"添加到文件列表：{path}")
                action.triggered.connect(
                    lambda checked=False, p=path: self._load_recent_file(p)
                )
                self._recent_files_menu.addAction(action)

        # 最近预设子菜单
        self._recent_presets_menu.clear()
        recent_presets = self._settings.recent_presets
        if not recent_presets:
            empty_action = QAction("（无）", self)
            empty_action.setEnabled(False)
            self._recent_presets_menu.addAction(empty_action)
        else:
            for path in recent_presets:
                action = QAction(path, self)
                action.setStatusTip(f"加载预设：{path}")
                action.triggered.connect(
                    lambda checked=False, p=path: self._load_recent_preset(p)
                )
                self._recent_presets_menu.addAction(action)

    def _load_recent_file(self, path: str) -> None:
        """点击最近文件菜单项：将文件添加到文件列表。

        Args:
            path: 文件绝对路径。
        """
        if not os.path.isfile(path):
            self.statusBar().showMessage("文件不存在", 2000)
            return
        self.file_list_widget.add_files([path])

    def _load_recent_preset(self, path: str) -> None:
        """点击最近预设菜单项：加载预设到所有 Tab。

        Args:
            path: 预设文件绝对路径。
        """
        if not os.path.isfile(path):
            self.statusBar().showMessage("预设文件不存在", 2000)
            return
        try:
            tool_type_str, params = load_preset(path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "加载失败", f"加载预设失败：{exc}")
            return
        cfg = self._build_preset_config(tool_type_str, params)
        if cfg is None:
            QMessageBox.critical(
                self, "加载失败", f"无法应用预设工具类型：{tool_type_str}"
            )
            return
        # 预设工具类型与当前不同时切换工具（会重建 Tab）
        target_tool = ToolType(tool_type_str)
        if target_tool is not self._current_tool:
            self._switch_tool(target_tool)
        for tab in self._tabs:
            tab.apply_config(cfg)
        self._add_recent_preset(path)
        logger.info("已从最近预设 %s 加载", path)

    # ------------------------------------------------------------------
    # 工具栏槽：设置
    # ------------------------------------------------------------------
    def _on_settings(self) -> None:
        """打开设置对话框，保存配置并触发相关刷新。"""
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_path = dialog.get_balcon_path()
        new_concurrency = dialog.get_concurrency()
        new_priority = dialog.get_process_priority()
        new_blb2txt_path = dialog.get_blb2txt_path()
        new_blb2txt_lite_path = dialog.get_blb2txt_lite_path()
        new_theme = dialog.get_theme()
        new_density = dialog.get_density()
        new_font_scale = dialog.get_font_scale()
        new_disable_animations = dialog.get_disable_animations()

        path_changed = new_path != self._settings.balcon_path
        concurrency_changed = new_concurrency != self._settings.max_concurrency
        blb2txt_path_changed = new_blb2txt_path != self._settings.blb2txt_path
        blb2txt_lite_changed = (
            new_blb2txt_lite_path != self._settings.blb2txt_lite_path
        )
        theme_changed = new_theme != self._settings.theme
        density_changed = new_density != self._settings.density
        font_scale_changed = new_font_scale != self._settings.font_scale
        animations_changed = (
            new_disable_animations != self._settings.disable_animations
        )

        self._settings.balcon_path = new_path
        self._settings.max_concurrency = new_concurrency
        self._settings.process_priority = new_priority
        self._settings.blb2txt_path = new_blb2txt_path
        self._settings.blb2txt_lite_path = new_blb2txt_lite_path
        self._settings.theme = new_theme
        self._settings.density = new_density
        self._settings.font_scale = new_font_scale
        self._settings.disable_animations = new_disable_animations
        try:
            self._settings.save()
        except OSError as exc:
            QMessageBox.warning(self, "保存设置失败", str(exc))

        if concurrency_changed:
            self._scheduler.set_max_concurrency(new_concurrency)
        self._update_status_bar()

        # 外观变更：通过 ThemeManager 重新应用主题/密度/字号缩放
        if theme_changed:
            ThemeManager.instance().apply_theme(new_theme)
        if density_changed:
            ThemeManager.instance().apply_density(new_density)
        if font_scale_changed:
            ThemeManager.instance().apply_font_scale(new_font_scale)
        # 动画开关变化时刷新 AnimationManager 禁用状态
        if animations_changed:
            try:
                from chatterbox.gui.widgets.animation_manager import (
                    AnimationManager,
                )

                AnimationManager.instance().set_enabled(
                    not new_disable_animations
                )
            except (ImportError, AttributeError):
                logger.debug("AnimationManager 不可用，跳过动画开关同步")

        if path_changed:
            self._validate_balcon_path()
            self._refresh_voices_devices()

        # blb2txt 路径变更时刷新"开始"按钮启用状态
        if blb2txt_path_changed or blb2txt_lite_changed:
            if self._current_tool is ToolType.BLB2TXT:
                if not self._scheduler.is_running():
                    self.start_action.setEnabled(self._blb2txt_path_valid())

    def _on_open_benchmark_dialog(self) -> None:
        """打开并发基准测试对话框。

        使用当前工具类型与配置预填对话框，连接 apply_concurrency 信号到
        _on_apply_benchmark_concurrency 应用推荐值。
        """
        dialog = BenchmarkDialog(
            tool_type=self._current_tool,
            balcon_config=self._balcon_config,
            sapi_config=self._sapi_config,
            balcon_path=self._settings.balcon_path,
            parent=self,
        )
        dialog.apply_concurrency.connect(self._on_apply_benchmark_concurrency)
        dialog.exec()

    def _on_apply_benchmark_concurrency(self, n: int) -> None:
        """应用基准测试推荐的并发数。

        更新主窗口并发设置（settings 与 concurrency_spin），
        同步到调度器，并在状态栏提示。
        """
        if n <= 0:
            return
        # 更新 settings
        self._settings.max_concurrency = n
        try:
            self._settings.save()
        except OSError as exc:
            logger.warning("保存设置失败: %s", exc)
        # 更新设置对话框中的 SpinBox（如果存在）
        # 注意：SettingsDialog 是临时创建的，SpinBox 在 SettingsDialog 实例中，
        # 但 MainWindow 持有 self.concurrency_spin 引用吗？
        # 查看代码：SettingsDialog 拥有 concurrency_spin，MainWindow 不直接持有。
        # 但 MainWindow 设置对话框通过 _on_settings 创建 SettingsDialog，
        # 每次 exec() 前用 self._settings.max_concurrency 初始化 SpinBox 值，
        # 所以更新 self._settings.max_concurrency 即可，下次打开设置对话框时自动同步。

        # 同步到调度器
        self._scheduler.set_max_concurrency(n)

        # 状态栏提示
        self.statusBar().showMessage(f"已应用推荐并发数：{n}", 5000)

    # ------------------------------------------------------------------
    # 调度器信号槽
    # ------------------------------------------------------------------
    def _on_task_started(self, filename: str) -> None:
        """单个任务开始：更新状态栏显示当前处理文件（含工具前缀）。"""
        self.statusBar().showMessage(
            f"{self._status_prefix()}正在处理: {filename}"
        )

    def _on_task_error(self, filename: str, error: str) -> None:
        """任务出错：记录日志。"""
        logger.error("任务失败 %s: %s", filename, error)

    def _on_scheduler_warning(self, message: str) -> None:
        """调度器警告（Task 17）：状态栏显示 5 秒，并写入日志面板。

        用于并发数超过 12 时的崩溃风险提示等项目硬约束警告。

        Args:
            message: 警告消息文本。
        """
        self.statusBar().showMessage(message, 5000)
        logger.warning(message)

    def _on_queue_depth_changed(self, depth: int) -> None:
        """队列深度更新（Task 17）：记录调试日志。

        ProgressWidget 暂无队列深度显示控件，此处仅记录日志便于排查
        饱和状态；后续可扩展为驱动背压告警 UI。

        Args:
            depth: 当前待处理任务数（总任务数 - 已完成 - 正在运行）。
        """
        logger.debug("队列深度更新：%d", depth)

    def _on_task_finished(
        self, filename: str, returncode: int, stderr: str, elapsed: float
    ) -> None:
        """单个任务完成：日志记录（succeeded/failed 计数由
        ``progress_updated`` 信号携带真实计数驱动 ProgressWidget 更新，
        不再在此方法维护冗余计数）。

        Args:
            filename: 文件名（仅用于日志）。
            returncode: 子进程返回码，``0`` 为成功。
            stderr: stderr 摘要（仅用于日志）。
            elapsed: 单任务耗时（秒）。
        """
        status = "成功" if returncode == 0 else f"失败(rc={returncode})"
        logger.debug(
            "任务 %s：%s，耗时 %.2fs", filename, status, elapsed
        )

    def _on_all_finished(
        self, succeeded: int, failed: int, elapsed: float
    ) -> None:
        """全部任务完成：切换按钮状态、更新进度汇总、弹出汇总对话框。

        Args:
            succeeded: 成功任务数。
            failed: 失败任务数。
            elapsed: 总耗时（秒）。
        """
        self._set_running_state(False)
        # 清除 ffmpeg 路径与编码器检测缓存，避免长时间运行后缓存过期
        # （用户可能在下次批次前切换 ffmpeg 路径或更换 ffmpeg 版本）
        clear_ffmpeg_cache()
        # progress_updated 信号已携带真实 succeeded/failed 驱动
        # ProgressWidget 实时更新；此处仅补一次完整刷新确保最终状态正确
        total = succeeded + failed
        self.progress_widget.update_progress(
            total, total, succeeded=succeeded, failed=failed
        )
        # 状态灯：有失败 → error，全成功 → success
        self.progress_widget.set_state("error" if failed > 0 else "success")
        self.progress_widget.set_summary(succeeded, failed, elapsed)
        self._status_label.setText(f"{self._status_prefix()}就绪")
        self._update_status_bar()
        QMessageBox.information(
            self,
            "任务完成",
            f"批量任务已完成。\n\n"
            f"成功：{succeeded} 个\n"
            f"失败：{failed} 个\n"
            f"总耗时：{elapsed:.2f} 秒",
        )

    # ------------------------------------------------------------------
    # 枚举信号槽
    # ------------------------------------------------------------------
    def _on_voices_ready(self, voices: list[str]) -> None:
        """语音枚举完成：刷新所有 Tab 的语音列表。"""
        self._voices_count = len(voices)
        for tab in self._tabs:
            tab.refresh_voices(voices)
        logger.info("已刷新语音列表：共 %d 个", len(voices))
        self._update_status_bar()

    def _on_devices_ready(self, devices: list[tuple[int, str]]) -> None:
        """设备枚举完成：刷新所有 Tab 的设备列表。"""
        for tab in self._tabs:
            tab.refresh_devices(devices)
        logger.info("已刷新设备列表：共 %d 个", len(devices))
        self._update_status_bar()

    def _on_enum_error(self, message: str) -> None:
        """枚举失败：记录日志。"""
        logger.warning(message)

    # ------------------------------------------------------------------
    # 菜单栏槽
    # ------------------------------------------------------------------
    def _on_about(self) -> None:
        """关于对话框：以富文本展示版本、路径、运行时版本、依赖与许可证。"""
        QMessageBox.about(self, "关于", self._build_about_html())

    @staticmethod
    def _read_pyproject_metadata() -> dict[str, object]:
        """读取 pyproject.toml 中的项目元数据（依赖与许可证）。

        定位策略：从本模块文件向上查找 ``pyproject.toml``（最多 5 层），
        找不到则回退到当前工作目录。使用 ``tomllib``（Python 3.11+）解析，
        不可用时用简单文本扫描提取 ``dependencies`` 与 ``license``。

        Returns:
            ``{"dependencies": list[str], "license": str}`` 字典；
            解析失败时返回空列表/空字符串。
        """
        result: dict[str, object] = {"dependencies": [], "license": ""}
        # 定位 pyproject.toml
        candidates: list[str] = []
        try:
            module_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            module_dir = os.getcwd()
        cur = module_dir
        for _ in range(6):
            candidates.append(os.path.join(cur, "pyproject.toml"))
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        candidates.append(os.path.join(os.getcwd(), "pyproject.toml"))
        pyproject_path = next(
            (p for p in candidates if os.path.isfile(p)), None
        )
        if pyproject_path is None:
            return result
        try:
            try:
                import tomllib  # Python 3.11+

                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                project = data.get("project", {}) or {}
                deps = project.get("dependencies", []) or []
                result["dependencies"] = list(deps)
                license_field = project.get("license", "")
                if isinstance(license_field, dict):
                    license_field = license_field.get("text", "")
                result["license"] = str(license_field or "")
                return result
            except ImportError:
                pass
        except OSError:
            return result
        # 回退：简单文本扫描（Python 3.10 无 tomllib）
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return result
        import re

        dep_match = re.search(
            r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL
        )
        if dep_match:
            result["dependencies"] = re.findall(
                r'"([^"]+)"', dep_match.group(1)
            )
        lic_match = re.search(
            r'license\s*=\s*\{[^}]*text\s*=\s*"([^"]*)"', text
        )
        if lic_match:
            result["license"] = lic_match.group(1)
        return result

    def _build_about_html(self) -> str:
        """构造关于对话框的富文本（HTML）。

        展示：版本号、balcon/blb2txt 路径、Python/PySide6 版本、
        依赖列表（从 pyproject.toml 读取）、项目主页占位、许可证。
        路径与版本号使用 ``<code>`` 标签等宽字体显示。
        """
        try:
            from chatterbox import __version__

            version = f"v{__version__}"
        except ImportError:
            version = "v1.0"

        import platform

        python_ver = platform.python_version()
        try:
            import PySide6

            pyside_ver = PySide6.__version__
        except (ImportError, AttributeError):
            pyside_ver = "(未知)"

        balcon_path = self._settings.balcon_path or "(未配置)"
        blb2txt_path = self._settings.blb2txt_path or "(未配置)"

        meta = self._read_pyproject_metadata()
        deps = meta.get("dependencies", [])
        if isinstance(deps, list) and deps:
            deps_html = "<br>".join(
                f"&nbsp;&nbsp;<code>{d}</code>" for d in deps
            )
        else:
            deps_html = "&nbsp;&nbsp;(无法读取)"
        license_text = meta.get("license", "") or "MIT"

        return (
            f"<h3>balcon 批量 TTS {version}</h3>"
            "<p>基于 balcon.exe 的批量文本转语音与 blb2txt 文本提取工具。</p>"
            "<p><b>版本：</b><code>" + version + "</code></p>"
            "<p><b>balcon 路径：</b><code>" + balcon_path + "</code></p>"
            "<p><b>blb2txt 路径：</b><code>" + blb2txt_path + "</code></p>"
            "<p><b>运行时：</b><code>Python " + python_ver
            + "</code> / <code>PySide6 " + pyside_ver + "</code></p>"
            "<p><b>依赖：</b></p>" + deps_html
            + "<p><b>许可证：</b><code>" + license_text + "</code></p>"
            '<p><b>项目主页：</b><a href="https://github.com/BarbaterLI/Chatterbox">https://github.com/BarbaterLI/Chatterbox</a></p>'
        )

    def _on_copy_balcon_path(self) -> None:
        """状态栏中段路径点击：复制当前工具的可执行文件路径到剪贴板。

        SAPI5 模式无外部 exe，提示无路径可复制。
        """
        if self._current_tool is ToolType.BALCON:
            path = self._settings.balcon_path
        elif self._current_tool is ToolType.SAPI:
            self.statusBar().showMessage("SAPI5 无外部路径", 2000)
            return
        else:
            path = self._settings.blb2txt_path
        if not path:
            self.statusBar().showMessage("未配置路径", 2000)
            return
        QGuiApplication.clipboard().setText(path)
        self.statusBar().showMessage("已复制路径", 2000)

    # ------------------------------------------------------------------
    # T-B5：命令面板、快捷键对话框与 Tab 循环
    # ------------------------------------------------------------------
    def _register_shortcuts(self) -> None:
        """注册全局快捷键（QShortcut）。

        - ``Ctrl+Shift+P``：打开命令面板
        - ``F1``：打开快捷键帮助对话框
        - ``Ctrl+Tab``：下一个 Tab
        - ``Ctrl+Shift+Tab``：上一个 Tab
        """
        # Ctrl+Shift+P：打开命令面板
        palette_sc = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        palette_sc.activated.connect(self._open_command_palette)
        # F1：打开快捷键帮助对话框
        help_sc = QShortcut(QKeySequence("F1"), self)
        help_sc.activated.connect(self._open_shortcuts_dialog)
        # Ctrl+Tab：下一个 Tab
        next_tab_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_sc.activated.connect(lambda: self._cycle_tab(True))
        # Ctrl+Shift+Tab：上一个 Tab
        prev_tab_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_sc.activated.connect(lambda: self._cycle_tab(False))

    def _open_command_palette(self) -> None:
        """Ctrl+Shift+P：懒加载并打开命令面板。

        每次打开重建命令集合，确保 Tab 列表与工具状态为最新。
        首次创建后将引用存入 ``_command_palette``（懒加载标记）。
        """
        commands = self._build_commands()
        palette = CommandPalette(commands, self)
        palette.setModal(True)
        self._command_palette = palette
        palette.exec()

    def _open_shortcuts_dialog(self) -> None:
        """F1：懒加载并打开快捷键帮助对话框。

        首次创建后将引用存入 ``_shortcuts_dialog``（懒加载标记）。
        """
        shortcuts = self._build_shortcuts()
        dialog = ShortcutsDialog(shortcuts, self)
        dialog.setModal(True)
        self._shortcuts_dialog = dialog
        dialog.exec()

    def _cycle_tab(self, forward: bool) -> None:
        """Ctrl+Tab / Ctrl+Shift+Tab 在侧边栏可选 Tab 项间循环切换。

        Args:
            forward: ``True`` 为下一个（Ctrl+Tab），``False`` 为上一个
                （Ctrl+Shift+Tab）。
        """
        count = self.tab_widget.count()
        if count <= 1:
            return
        current = self.tab_widget.current_index()
        if current < 0:
            current = 0
        if forward:
            next_idx = (current + 1) % count
        else:
            next_idx = (current - 1) % count
        self.tab_widget.set_current_index(next_idx)

    def _build_commands(self) -> list[Command]:
        """构造命令面板的命令集合。

        包含：所有 Tab 跳转、工具切换、预设加载/保存、主题切换、打开设置。
        """
        commands: list[Command] = []
        # Tab 跳转命令（按堆叠面板索引循环切换）
        for i, tab in enumerate(self._tabs):
            cls = type(tab)
            title = cls.tab_title()
            tab_id = cls.tab_id()
            commands.append(
                Command(
                    id=f"tab.{tab_id}",
                    title=f"跳转到 {title}",
                    group="导航",
                    shortcut="Ctrl+Tab",
                    handler=lambda idx=i: self.tab_widget.set_current_index(idx),
                )
            )
        # 工具切换
        commands.append(
            Command(
                id="tool.balcon",
                title="切换到 balcon TTS",
                group="工具",
                handler=lambda: self._switch_tool(ToolType.BALCON),
            )
        )
        commands.append(
            Command(
                id="tool.blb2txt",
                title="切换到 blb2txt 文本提取",
                group="工具",
                handler=lambda: self._switch_tool(ToolType.BLB2TXT),
            )
        )
        # 预设
        commands.append(
            Command(
                id="preset.save",
                title="保存预设",
                group="预设",
                shortcut="Ctrl+S",
                handler=self._on_save_preset,
            )
        )
        commands.append(
            Command(
                id="preset.load",
                title="加载预设",
                group="预设",
                shortcut="Ctrl+L",
                handler=self._on_load_preset,
            )
        )
        # 主题切换
        commands.append(
            Command(
                id="theme.light",
                title="切换到亮色主题",
                group="主题",
                handler=lambda: self._switch_theme("light"),
            )
        )
        commands.append(
            Command(
                id="theme.dark",
                title="切换到暗色主题",
                group="主题",
                handler=lambda: self._switch_theme("dark"),
            )
        )
        commands.append(
            Command(
                id="theme.auto",
                title="切换到跟随系统主题",
                group="主题",
                handler=lambda: self._switch_theme("auto"),
            )
        )
        # 设置
        commands.append(
            Command(
                id="settings.open",
                title="打开设置",
                group="设置",
                handler=self._on_settings,
            )
        )
        return commands

    def _build_shortcuts(self) -> list[ShortcutItem]:
        """构造快捷键帮助对话框的 ShortcutItem 列表。"""
        return [
            ShortcutItem("Ctrl+O", "添加文件", "文件"),
            ShortcutItem("Delete", "移除选中文件", "文件"),
            ShortcutItem("Ctrl+Shift+Delete", "清空文件列表", "文件"),
            ShortcutItem("Ctrl+S", "保存预设", "预设"),
            ShortcutItem("Ctrl+L", "加载预设", "预设"),
            ShortcutItem("Ctrl+Q", "退出程序", "文件"),
            ShortcutItem("F5", "刷新语音/设备", "操作"),
            ShortcutItem("Ctrl+Return", "开始转换", "执行控制"),
            ShortcutItem("Esc", "停止任务", "执行控制"),
            ShortcutItem("Ctrl+P", "预览命令行", "操作"),
            ShortcutItem("Ctrl+Shift+P", "打开命令面板", "导航"),
            ShortcutItem("F1", "快捷键帮助", "导航"),
            ShortcutItem("Ctrl+Tab", "下一个 Tab", "导航"),
            ShortcutItem("Ctrl+Shift+Tab", "上一个 Tab", "导航"),
        ]

    def _switch_tool(self, tool: ToolType) -> None:
        """命令面板：切换工具类型（通过 tool_combo 触发 _on_tool_changed）。

        Args:
            tool: 目标工具类型。
        """
        for i in range(self.tool_combo.count()):
            if self.tool_combo.itemData(i) == tool:
                self.tool_combo.setCurrentIndex(i)
                return

    def _switch_theme(self, theme: str) -> None:
        """命令面板：切换主题并持久化。

        Args:
            theme: ``"light"`` / ``"dark"`` / ``"auto"``。
        """
        self._settings.theme = theme
        try:
            self._settings.save()
        except OSError as exc:
            logger.warning("保存设置失败：%s", exc)
        ThemeManager.instance().apply_theme(theme)

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------
    def _set_running_state(self, running: bool) -> None:
        """切换运行状态："开始"与"停止"按钮互斥启用。

        非运行状态下，"开始"按钮的启用取决于当前工具路径是否有效
        （balcon → :meth:`_balcon_path_valid`，blb2txt →
        :meth:`_blb2txt_path_valid`，SAPI5 → 始终启用，无外部 exe 依赖）。

        Args:
            running: 是否处于运行状态。
        """
        if running:
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
        else:
            if self._current_tool is ToolType.BALCON:
                self.start_action.setEnabled(self._balcon_path_valid())
            elif self._current_tool is ToolType.SAPI:
                # SAPI5 无外部 exe 依赖，开始按钮始终启用
                self.start_action.setEnabled(True)
            else:
                self.start_action.setEnabled(self._blb2txt_path_valid())
            self.stop_action.setEnabled(False)

    # ------------------------------------------------------------------
    # 窗口关闭
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """关闭窗口：保存设置与窗口几何，取消运行中的任务。"""
        # 保存 OutputTab 的输出目录与模板到设置
        if self._current_tool is ToolType.BALCON:
            output_tab = self._tabs_by_id.get("output")
            if output_tab is not None:
                self._settings.last_output_dir = output_tab.get_output_dir()
                self._settings.filename_template = output_tab.get_filename_template()
                # 多格式输出：保存输出格式与 ffmpeg 路径
                self._settings.output_format = output_tab.get_output_format().value
                self._settings.ffmpeg_path = output_tab.get_ffmpeg_path()
                # 保存 VBR 质量设置
                self._settings.vbr_quality = output_tab.get_vbr_quality()
        elif self._current_tool is ToolType.SAPI:
            # SAPI5：不覆盖共享的 AppSettings 输出字段，
            # SAPI 输出状态已在 _on_tool_changed 中保存到 _sapi_output_* 字段
            # 但 VBR 质量是共享设置，需从 SapiOutputTab 读取并保存
            output_tab = self._tabs_by_id.get("sapi_output")
            if output_tab is not None:
                self._settings.vbr_quality = output_tab.get_vbr_quality()
        else:
            # blb2txt 模式下使用保存的 balcon 状态
            self._settings.last_output_dir = self._balcon_output_dir
            self._settings.filename_template = self._balcon_filename_template
        # 保存窗口几何
        try:
            self._settings.window_geometry = (
                self.saveGeometry().toBase64().data().decode("ascii")
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            self._settings.save()
        except OSError as exc:
            logger.warning("保存设置失败：%s", exc)
        # 取消运行中的任务
        if self._scheduler.is_running():
            self._scheduler.cancel_all()
        event.accept()


__all__ = ["MainWindow"]
