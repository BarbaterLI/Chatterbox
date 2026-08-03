"""最近文件/预设子菜单测试（T-B6）。

验证：
- 菜单栏「文件」菜单包含「最近文件」与「最近预设」子菜单
- ``_refresh_recent_menus`` 根据设置填充子菜单（空列表显示「（无）」占位项）
- ``_add_recent_file`` / ``_add_recent_preset`` 加入首位、去重、保留前 10 项
- ``_on_files_changed`` 将新增文件加入最近文件列表
- ``_load_recent_file`` 将文件添加到文件列表
- 保存/加载预设成功后加入最近预设

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换 QMessageBox、
QFileDialog 与调度器，避免真实交互与子进程执行。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.config import BalconConfig
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
# 测试辅助：构造可用路径的 settings
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
# T-B6：子菜单存在性
# ---------------------------------------------------------------------------
class TestRecentMenusExist:
    """菜单栏包含最近文件与最近预设子菜单。"""

    def test_recent_files_menu_exists(self, main_window: MainWindow) -> None:
        """「文件」菜单应包含「最近文件」子菜单。"""
        assert hasattr(main_window, "_recent_files_menu")
        assert main_window._recent_files_menu.title() == "最近文件"

    def test_recent_presets_menu_exists(self, main_window: MainWindow) -> None:
        """「文件」菜单应包含「最近预设」子菜单。"""
        assert hasattr(main_window, "_recent_presets_menu")
        assert main_window._recent_presets_menu.title() == "最近预设"


# ---------------------------------------------------------------------------
# T-B6：空列表占位项
# ---------------------------------------------------------------------------
class TestEmptyRecentMenus:
    """空列表时子菜单显示禁用的「（无）」占位项。"""

    def test_empty_recent_files_shows_placeholder(
        self, main_window: MainWindow
    ) -> None:
        """recent_files 为空时子菜单只有 1 个禁用项「（无）」。"""
        main_window._settings.recent_files = []
        main_window._refresh_recent_menus()
        actions = main_window._recent_files_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "（无）"
        assert actions[0].isEnabled() is False

    def test_empty_recent_presets_shows_placeholder(
        self, main_window: MainWindow
    ) -> None:
        """recent_presets 为空时子菜单只有 1 个禁用项「（无）」。"""
        main_window._settings.recent_presets = []
        main_window._refresh_recent_menus()
        actions = main_window._recent_presets_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "（无）"
        assert actions[0].isEnabled() is False


# ---------------------------------------------------------------------------
# T-B6：_refresh_recent_menus 填充
# ---------------------------------------------------------------------------
class TestRefreshRecentMenus:
    """``_refresh_recent_menus`` 根据设置填充子菜单。"""

    def test_populates_recent_files_actions(
        self, main_window: MainWindow
    ) -> None:
        """非空 recent_files 时每项对应一个 QAction。"""
        files = ["C:/a.txt", "C:/b.txt", "C:/c.txt"]
        main_window._settings.recent_files = list(files)
        main_window._refresh_recent_menus()
        actions = main_window._recent_files_menu.actions()
        assert len(actions) == 3
        for i, f in enumerate(files):
            assert actions[i].text() == f

    def test_populates_recent_presets_actions(
        self, main_window: MainWindow
    ) -> None:
        """非空 recent_presets 时每项对应一个 QAction。"""
        presets = ["C:/p1.json", "C:/p2.json"]
        main_window._settings.recent_presets = list(presets)
        main_window._refresh_recent_menus()
        actions = main_window._recent_presets_menu.actions()
        assert len(actions) == 2
        for i, p in enumerate(presets):
            assert actions[i].text() == p

    def test_refresh_clears_old_actions(
        self, main_window: MainWindow
    ) -> None:
        """刷新后旧 action 应被清除（不残留）。"""
        main_window._settings.recent_files = ["C:/a.txt", "C:/b.txt"]
        main_window._refresh_recent_menus()
        assert len(main_window._recent_files_menu.actions()) == 2
        # 刷新为不同列表
        main_window._settings.recent_files = ["C:/c.txt"]
        main_window._refresh_recent_menus()
        actions = main_window._recent_files_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "C:/c.txt"


# ---------------------------------------------------------------------------
# T-B6：_add_recent_file
# ---------------------------------------------------------------------------
class TestAddRecentFile:
    """``_add_recent_file`` 加入首位、去重、保留前 10 项。"""

    def test_add_to_head(self, main_window: MainWindow) -> None:
        """新文件应加入列表首位。"""
        main_window._settings.recent_files = []
        main_window._add_recent_file("C:/a.txt")
        assert main_window._settings.recent_files == ["C:/a.txt"]

    def test_add_second_to_head(self, main_window: MainWindow) -> None:
        """第二个文件应加入首位，原文件下移。"""
        main_window._settings.recent_files = ["C:/a.txt"]
        main_window._add_recent_file("C:/b.txt")
        assert main_window._settings.recent_files == ["C:/b.txt", "C:/a.txt"]

    def test_dedup_moves_to_head(self, main_window: MainWindow) -> None:
        """已存在的文件应移动到首位（去重）。"""
        main_window._settings.recent_files = ["C:/a.txt", "C:/b.txt"]
        main_window._add_recent_file("C:/a.txt")
        assert main_window._settings.recent_files == ["C:/a.txt", "C:/b.txt"]

    def test_limit_to_ten(self, main_window: MainWindow) -> None:
        """列表应保留最多 10 项，超出时截断尾部。"""
        files = [f"C:/{i}.txt" for i in range(10)]
        main_window._settings.recent_files = list(files)
        main_window._add_recent_file("C:/new.txt")
        assert len(main_window._settings.recent_files) == 10
        assert main_window._settings.recent_files[0] == "C:/new.txt"
        # 最后一个（C:/9.txt）应被截断
        assert "C:/9.txt" not in main_window._settings.recent_files
        # C:/0.txt 应仍在列表
        assert "C:/0.txt" in main_window._settings.recent_files

    def test_empty_path_ignored(self, main_window: MainWindow) -> None:
        """空路径不应加入列表。"""
        main_window._settings.recent_files = ["C:/a.txt"]
        main_window._add_recent_file("")
        assert main_window._settings.recent_files == ["C:/a.txt"]

    def test_add_triggers_refresh(self, main_window: MainWindow) -> None:
        """添加后应触发菜单刷新（菜单内容与设置同步）。"""
        main_window._settings.recent_files = []
        main_window._add_recent_file("C:/a.txt")
        actions = main_window._recent_files_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "C:/a.txt"


# ---------------------------------------------------------------------------
# T-B6：_add_recent_preset
# ---------------------------------------------------------------------------
class TestAddRecentPreset:
    """``_add_recent_preset`` 加入首位、去重、保留前 10 项。"""

    def test_add_to_head(self, main_window: MainWindow) -> None:
        """新预设应加入列表首位。"""
        main_window._settings.recent_presets = []
        main_window._add_recent_preset("C:/p1.json")
        assert main_window._settings.recent_presets == ["C:/p1.json"]

    def test_dedup_moves_to_head(self, main_window: MainWindow) -> None:
        """已存在的预设应移动到首位（去重）。"""
        main_window._settings.recent_presets = ["C:/p1.json", "C:/p2.json"]
        main_window._add_recent_preset("C:/p1.json")
        assert main_window._settings.recent_presets == ["C:/p1.json", "C:/p2.json"]

    def test_limit_to_ten(self, main_window: MainWindow) -> None:
        """列表应保留最多 10 项。"""
        presets = [f"C:/p{i}.json" for i in range(10)]
        main_window._settings.recent_presets = list(presets)
        main_window._add_recent_preset("C:/new.json")
        assert len(main_window._settings.recent_presets) == 10
        assert main_window._settings.recent_presets[0] == "C:/new.json"
        assert "C:/p9.json" not in main_window._settings.recent_presets


# ---------------------------------------------------------------------------
# T-B6：_on_files_changed
# ---------------------------------------------------------------------------
class TestOnFilesChanged:
    """``_on_files_changed`` 将新增文件加入最近文件列表。"""

    def test_new_file_added_to_recent(
        self, main_window: MainWindow
    ) -> None:
        """文件列表新增的文件应加入最近文件。"""
        main_window._settings.recent_files = []
        main_window._on_files_changed(["C:/a.txt"])
        assert "C:/a.txt" in main_window._settings.recent_files

    def test_only_new_files_added(
        self, main_window: MainWindow
    ) -> None:
        """仅新增文件加入最近文件，已有文件不重复加入。"""
        main_window._settings.recent_files = []
        # 第一次添加
        main_window._on_files_changed(["C:/a.txt", "C:/b.txt"])
        assert main_window._settings.recent_files == ["C:/b.txt", "C:/a.txt"]
        # 第二次添加仅新增 c.txt
        main_window._on_files_changed(["C:/a.txt", "C:/b.txt", "C:/c.txt"])
        # c.txt 应在首位，a/b 不重复添加
        assert main_window._settings.recent_files[0] == "C:/c.txt"
        assert main_window._settings.recent_files.count("C:/a.txt") == 1
        assert main_window._settings.recent_files.count("C:/b.txt") == 1

    def test_removed_files_dont_trigger(
        self, main_window: MainWindow
    ) -> None:
        """文件被移除时不应触发添加。"""
        main_window._settings.recent_files = []
        main_window._on_files_changed(["C:/a.txt", "C:/b.txt"])
        initial = list(main_window._settings.recent_files)
        # 移除 b.txt
        main_window._on_files_changed(["C:/a.txt"])
        # recent_files 不应变（不添加也不移除）
        assert main_window._settings.recent_files == initial


# ---------------------------------------------------------------------------
# T-B6：_load_recent_file
# ---------------------------------------------------------------------------
class TestLoadRecentFile:
    """``_load_recent_file`` 将文件添加到文件列表。"""

    def test_load_existing_file(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """点击存在的最近文件应添加到文件列表。"""
        file = tmp_path / "test.txt"
        file.write_text("content")
        main_window._load_recent_file(str(file))
        assert str(file) in main_window.file_list_widget.get_files()

    def test_load_missing_file_shows_status(
        self, main_window: MainWindow
    ) -> None:
        """点击不存在的文件应在状态栏显示提示。"""
        main_window._load_recent_file("C:/nonexistent_12345.txt")
        # 不应抛异常，且文件不应加入列表
        assert "C:/nonexistent_12345.txt" not in main_window.file_list_widget.get_files()


# ---------------------------------------------------------------------------
# T-B6：保存/加载预设加入最近预设
# ---------------------------------------------------------------------------
class TestPresetAddsToRecent:
    """保存/加载预设成功后加入最近预设列表。"""

    def test_save_preset_adds_to_recent(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """保存预设成功后应加入最近预设列表。"""
        preset_path = tmp_path / "preset.json"
        # 模拟文件保存对话框返回路径
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(preset_path), ""),
        )
        # 禁用磁盘保存
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        main_window._settings.recent_presets = []

        main_window._on_save_preset()

        assert str(preset_path) in main_window._settings.recent_presets

    def test_load_preset_adds_to_recent(
        self, main_window: MainWindow, tmp_path, monkeypatch
    ) -> None:
        """加载预设成功后应加入最近预设列表。"""
        # 创建一个有效的预设文件
        preset_path = tmp_path / "preset.json"
        cfg = BalconConfig.create_default()
        from balcon_batch_tts.persistence.preset import save_preset
        save_preset(str(preset_path), cfg)

        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(preset_path), ""),
        )
        monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)
        main_window._settings.recent_presets = []

        main_window._on_load_preset()

        assert str(preset_path) in main_window._settings.recent_presets

    def test_load_recent_preset_adds_to_recent(
        self, main_window: MainWindow, tmp_path
    ) -> None:
        """从最近预设菜单加载后应移到首位。"""
        # 创建一个有效的预设文件
        preset_path = tmp_path / "preset.json"
        cfg = BalconConfig.create_default()
        from balcon_batch_tts.persistence.preset import save_preset
        save_preset(str(preset_path), cfg)

        main_window._settings.recent_presets = ["C:/old.json"]
        main_window._load_recent_preset(str(preset_path))
        # 新加载的预设应在首位
        assert main_window._settings.recent_presets[0] == str(preset_path)
