"""关于对话框富文本测试（T-D5）。

验证：
- ``_on_about`` 调用 ``QMessageBox.about`` 展示富文本
- ``_build_about_html`` 返回包含版本号、balcon/blb2txt 路径、Python/PySide6
  版本、依赖列表、许可证的 HTML 字符串
- ``_read_pyproject_metadata`` 从 pyproject.toml 读取依赖与许可证

测试在 offscreen Qt 平台下运行，使用 monkeypatch 捕获 QMessageBox.about 调用。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import platform

import pytest
from PySide6.QtWidgets import QApplication

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
# 测试辅助
# ---------------------------------------------------------------------------
def _make_fake_exe(tmp_path, name: str) -> str:
    """在 tmp_path 下创建一个空文件作为伪可执行文件，返回绝对路径。"""
    fake = tmp_path / name
    fake.write_text("")
    return str(fake)


@pytest.fixture
def fake_settings(tmp_path) -> AppSettings:
    """返回三个路径均有效的 AppSettings 实例。"""
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
    """构造一个 MainWindow 实例，禁用弹窗与枚举。"""
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.warning", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.critical", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "balcon_batch_tts.gui.main_window.QMessageBox.information", lambda *a, **k: 0
    )
    monkeypatch.setattr(MainWindow, "_refresh_voices_devices", lambda self: None)
    monkeypatch.setattr(
        AppSettings, "load", classmethod(lambda cls, path=None: fake_settings)
    )
    return MainWindow()


# ---------------------------------------------------------------------------
# T-D5：_on_about 调用 QMessageBox.about
# ---------------------------------------------------------------------------
class TestOnAbout:
    """``_on_about`` 行为。"""

    def test_calls_qmessagebox_about(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """``_on_about`` 应调用 QMessageBox.about。"""
        about_calls: list = []
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.about",
            lambda *a, **k: about_calls.append(a) or None,
        )
        main_window._on_about()
        assert len(about_calls) == 1
        # 参数：(parent, title, text)
        assert about_calls[0][0] is main_window
        assert about_calls[0][1] == "关于"

    def test_about_text_is_html(
        self, main_window: MainWindow, monkeypatch
    ) -> None:
        """about 文本应以 <h3> 开头（富文本）。"""
        captured: dict = {}
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.about",
            lambda parent, title, text: captured.update(text=text),
        )
        main_window._on_about()
        assert "<h3>" in captured["text"]


# ---------------------------------------------------------------------------
# T-D5：_build_about_html 内容
# ---------------------------------------------------------------------------
class TestBuildAboutHtml:
    """``_build_about_html`` 返回的 HTML 内容。"""

    def test_html_contains_version(self, main_window: MainWindow) -> None:
        """HTML 应包含版本号。"""
        html = main_window._build_about_html()
        from balcon_batch_tts import __version__
        assert __version__ in html

    def test_html_contains_balcon_path(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含 balcon 路径。"""
        html = main_window._build_about_html()
        assert main_window._settings.balcon_path in html

    def test_html_contains_blb2txt_path(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含 blb2txt 路径。"""
        html = main_window._build_about_html()
        assert main_window._settings.blb2txt_path in html

    def test_html_contains_python_version(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含 Python 版本。"""
        html = main_window._build_about_html()
        assert platform.python_version() in html

    def test_html_contains_pyside6_version(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含 PySide6 版本。"""
        html = main_window._build_about_html()
        import PySide6
        assert PySide6.__version__ in html

    def test_html_contains_license(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含许可证信息。"""
        html = main_window._build_about_html()
        # pyproject.toml 中 license 为 MIT
        assert "MIT" in html

    def test_html_contains_dependencies(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应包含依赖列表。"""
        html = main_window._build_about_html()
        # pyproject.toml 中至少有 PySide6 依赖
        assert "PySide6" in html

    def test_html_contains_h3_header(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应以 <h3> 标题开头。"""
        html = main_window._build_about_html()
        assert html.startswith("<h3>")

    def test_html_contains_code_tags(
        self, main_window: MainWindow
    ) -> None:
        """HTML 应使用 <code> 标签显示路径与版本号。"""
        html = main_window._build_about_html()
        assert "<code>" in html
        assert "</code>" in html

    def test_html_unconfigured_paths_shown(
        self, main_window: MainWindow
    ) -> None:
        """路径未配置时 HTML 应显示「(未配置)」。"""
        main_window._settings.balcon_path = ""
        html = main_window._build_about_html()
        assert "(未配置)" in html


# ---------------------------------------------------------------------------
# T-D5：_read_pyproject_metadata
# ---------------------------------------------------------------------------
class TestReadPyprojectMetadata:
    """``_read_pyproject_metadata`` 从 pyproject.toml 读取元数据。"""

    def test_returns_dict_with_dependencies(
        self, main_window: MainWindow
    ) -> None:
        """返回值应包含 dependencies 键（列表）。"""
        meta = main_window._read_pyproject_metadata()
        assert "dependencies" in meta
        assert isinstance(meta["dependencies"], list)

    def test_returns_dict_with_license(
        self, main_window: MainWindow
    ) -> None:
        """返回值应包含 license 键（字符串）。"""
        meta = main_window._read_pyproject_metadata()
        assert "license" in meta
        assert isinstance(meta["license"], str)

    def test_dependencies_include_pyside6(
        self, main_window: MainWindow
    ) -> None:
        """依赖列表应包含 PySide6。"""
        meta = main_window._read_pyproject_metadata()
        deps = meta["dependencies"]
        # 至少有一个依赖包含 PySide6
        assert any("PySide6" in d for d in deps)

    def test_license_is_mit(
        self, main_window: MainWindow
    ) -> None:
        """许可证应为 MIT。"""
        meta = main_window._read_pyproject_metadata()
        assert meta["license"] == "MIT"

    def test_metadata_not_empty(
        self, main_window: MainWindow
    ) -> None:
        """依赖列表应非空。"""
        meta = main_window._read_pyproject_metadata()
        assert len(meta["dependencies"]) > 0
