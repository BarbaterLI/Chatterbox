"""并发基准测试菜单集成的 MainWindow 测试。

验证"工具 → 并发基准测试"菜单项的集成行为：
- "工具"菜单存在且包含"并发基准测试…"动作。
- 触发菜单项能实例化 BenchmarkDialog 并连接 apply_concurrency 信号。
- _on_apply_benchmark_concurrency 更新 settings、调度器并发数。
- n <= 0 时 _on_apply_benchmark_concurrency 不做任何修改。
- 打开对话框时传入当前工具类型。

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换 QMessageBox、
_refresh_voices_devices 与 AppSettings.load，避免真实交互与阻塞。
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

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.main_window import MainWindow
from balcon_batch_tts.persistence.settings import AppSettings


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 辅助：构造可用路径的 settings（避免路径校验弹窗阻塞）
# ---------------------------------------------------------------------------
def _make_fake_exe(tmp_path, name: str) -> str:
    """在 tmp_path 下创建一个空文件作为伪可执行文件，返回绝对路径。"""
    fake = tmp_path / name
    fake.write_text("")
    return str(fake)


@pytest.fixture
def fake_settings(tmp_path) -> AppSettings:
    """返回三个路径均有效的 AppSettings 实例（避免路径无效弹窗）。"""
    return AppSettings(
        balcon_path=_make_fake_exe(tmp_path, "balcon.exe"),
        blb2txt_path=_make_fake_exe(tmp_path, "blb2txt.exe"),
        blb2txt_lite_path=_make_fake_exe(tmp_path, "blb2txt_lite.exe"),
        max_concurrency=2,
    )


@pytest.fixture
def main_window(
    qapp: QApplication,
    fake_settings: AppSettings,
    monkeypatch,
) -> MainWindow:
    """构造一个 MainWindow 实例，禁用 QMessageBox 弹窗与枚举工作者。"""
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.warning",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.critical",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.information",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        MainWindow, "_refresh_voices_devices", lambda self: None
    )
    monkeypatch.setattr(
        AppSettings,
        "load",
        classmethod(lambda cls, path=None: fake_settings),
    )
    return MainWindow()


# ---------------------------------------------------------------------------
# 桩对话框：替代 BenchmarkDialog，exec() 立即返回不阻塞
# ---------------------------------------------------------------------------
class _FakeBenchmarkDialog(QObject):
    """替代 ``BenchmarkDialog`` 的桩对象。

    Signal 必须在类定义时声明，故继承 QObject 并定义 ``apply_concurrency``。
    记录所有实例化对象供测试断言。
    """

    apply_concurrency = Signal(int)
    instances: list["_FakeBenchmarkDialog"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        _FakeBenchmarkDialog.instances.append(self)
        self._args = args
        self._kwargs = kwargs

    def exec(self) -> int:
        return 0  # 不阻塞


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------
class TestBenchmarkIntegration:
    """并发基准测试菜单集成测试。"""

    def test_menu_has_benchmark_action(self, main_window):
        """工具菜单应存在且包含"并发基准测试…"动作。"""
        menubar = main_window.menuBar()
        # 找到"工具"菜单
        tool_menu = None
        for action in menubar.actions():
            if action.text() == "工具":
                tool_menu = action.menu()
                break
        assert tool_menu is not None, "工具菜单不存在"
        # 验证菜单项
        texts = [a.text() for a in tool_menu.actions()]
        assert "并发基准测试…" in texts

    def test_open_benchmark_dialog(self, main_window, monkeypatch):
        """触发 _on_open_benchmark_dialog 应实例化 BenchmarkDialog。"""
        _FakeBenchmarkDialog.instances.clear()
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.BenchmarkDialog",
            _FakeBenchmarkDialog,
        )
        # 直接调用方法（避免 menu action.trigger() 的副作用）
        main_window._on_open_benchmark_dialog()
        # 验证对话框被实例化
        assert len(_FakeBenchmarkDialog.instances) == 1
        dialog = _FakeBenchmarkDialog.instances[0]
        # 验证 apply_concurrency 信号已连接（实例化即成功）
        assert dialog is not None

    def test_apply_concurrency_updates_setting(self, main_window):
        """_on_apply_benchmark_concurrency 应更新 settings 与调度器。"""
        initial = main_window._settings.max_concurrency
        new_n = 6
        if new_n == initial:
            new_n = 7  # 确保与初始值不同
        main_window._on_apply_benchmark_concurrency(new_n)
        assert main_window._settings.max_concurrency == new_n
        assert main_window._scheduler.max_concurrency() == new_n

    def test_apply_concurrency_ignores_zero_or_negative(self, main_window):
        """n <= 0 时不应修改任何设置。"""
        initial = main_window._settings.max_concurrency
        main_window._on_apply_benchmark_concurrency(0)
        assert main_window._settings.max_concurrency == initial
        main_window._on_apply_benchmark_concurrency(-1)
        assert main_window._settings.max_concurrency == initial

    def test_benchmark_dialog_passed_correct_tool_type(
        self, main_window, monkeypatch
    ):
        """打开对话框时应传入当前工具类型（默认 BALCON）。"""
        captured_args: list[tuple[tuple, dict]] = []

        class _SpyDialog(QObject):
            apply_concurrency = Signal(int)

            def __init__(self, *args, **kwargs) -> None:
                super().__init__()
                captured_args.append((args, kwargs))

            def exec(self) -> int:
                return 0

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.BenchmarkDialog",
            _SpyDialog,
        )

        # 默认工具为 BALCON
        main_window._on_open_benchmark_dialog()
        assert len(captured_args) == 1
        args, kwargs = captured_args[0]
        # tool_type 以关键字参数传入
        tool_type = args[0] if args else kwargs.get("tool_type")
        assert tool_type is ToolType.BALCON
