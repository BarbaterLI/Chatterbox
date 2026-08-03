"""SettingsDialog 内联校验与外观分组测试（T-C5）。

验证：
- 路径输入框 textChanged 实时触发 InlineIndicator 校验（ok/error/hidden）
- 并发数 >12 时显示 warning 指示器，≤12 时隐藏
- 「重置为默认」按钮弹确认对话框，确认后还原字段
- 外观分组：主题 comboBox / 密度 comboBox / 字号缩放滑块 / 动画开关
- 对应 getter 方法（get_theme / get_density / get_font_scale /
  get_disable_animations）返回值正确

测试在 offscreen Qt 平台下运行，使用 monkeypatch 替换 QMessageBox 避免弹窗。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QCheckBox

from balcon_batch_tts.gui.main_window import SettingsDialog
from balcon_batch_tts.gui.widgets.inline_indicator import InlineIndicator
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
    """返回三个路径均有效的 AppSettings 实例。"""
    return AppSettings(
        balcon_path=_make_fake_exe(tmp_path, "balcon.exe"),
        blb2txt_path=_make_fake_exe(tmp_path, "blb2txt.exe"),
        blb2txt_lite_path=_make_fake_exe(tmp_path, "blb2txt_lite.exe"),
        max_concurrency=2,
    )


# ---------------------------------------------------------------------------
# T-C5：内联路径校验
# ---------------------------------------------------------------------------
class TestPathInlineValidation:
    """``SettingsDialog`` 路径输入框内联校验行为。"""

    def test_path_indicators_are_inline_indicators(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """三个路径行均应包含 InlineIndicator 实例。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.path_indicator, InlineIndicator)
        assert isinstance(dialog.blb2txt_path_indicator, InlineIndicator)
        assert isinstance(dialog.blb2txt_lite_path_indicator, InlineIndicator)

    def test_valid_path_shows_ok_indicator(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """有效路径应使指示器显示 ok 状态。"""
        dialog = SettingsDialog(fake_settings)
        # 初始路径有效（fake_settings 的 balcon_path 指向真实空文件）
        assert dialog.path_indicator._state == "ok"

    def test_invalid_path_shows_error_indicator(
        self, qapp: QApplication, fake_settings: AppSettings, tmp_path
    ) -> None:
        """不存在的路径应使指示器显示 error 状态。"""
        dialog = SettingsDialog(fake_settings)
        invalid_path = str(tmp_path / "nonexistent.exe")
        dialog.path_edit.setText(invalid_path)
        assert dialog.path_indicator._state == "error"

    def test_empty_path_hides_indicator(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """空路径应使指示器隐藏（hidden 状态）。"""
        dialog = SettingsDialog(fake_settings)
        dialog.path_edit.setText("")
        assert dialog.path_indicator._state == "hidden"
        assert dialog.path_indicator.isVisible() is False

    def test_blb2txt_path_indicator_valid(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt 主版本路径有效时指示器显示 ok。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.blb2txt_path_indicator._state == "ok"

    def test_blb2txt_path_indicator_invalid(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt 主版本路径无效时指示器显示 error。"""
        dialog = SettingsDialog(fake_settings)
        dialog.blb2txt_path_edit.setText("C:/nonexistent/blb2txt.exe")
        assert dialog.blb2txt_path_indicator._state == "error"

    def test_blb2txt_lite_path_indicator_valid(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt 精简版路径有效时指示器显示 ok。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.blb2txt_lite_path_indicator._state == "ok"

    def test_blb2txt_lite_path_indicator_empty(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """blb2txt 精简版路径为空时指示器隐藏。"""
        dialog = SettingsDialog(fake_settings)
        dialog.blb2txt_lite_path_edit.setText("")
        assert dialog.blb2txt_lite_path_indicator._state == "hidden"

    def test_text_changed_triggers_validation(
        self, qapp: QApplication, fake_settings: AppSettings, tmp_path
    ) -> None:
        """textChanged 信号应实时触发校验（ok → error → hidden）。"""
        dialog = SettingsDialog(fake_settings)
        # 初始 ok
        assert dialog.path_indicator._state == "ok"
        # 改为无效路径
        dialog.path_edit.setText(str(tmp_path / "missing.exe"))
        assert dialog.path_indicator._state == "error"
        # 改为空
        dialog.path_edit.setText("")
        assert dialog.path_indicator._state == "hidden"


# ---------------------------------------------------------------------------
# T-C5：并发数内联警告
# ---------------------------------------------------------------------------
class TestConcurrencyWarning:
    """并发数 >12 时显示内联警告指示器。"""

    def test_concurrency_indicator_is_inline_indicator(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """并发数行应包含 InlineIndicator 实例。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.concurrency_indicator, InlineIndicator)

    def test_low_concurrency_hides_indicator(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """并发数 ≤12 时指示器隐藏。"""
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(8)
        assert dialog.concurrency_indicator._state == "hidden"

    def test_high_concurrency_shows_warning(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """并发数 >12 时指示器显示 warning 状态。"""
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(13)
        assert dialog.concurrency_indicator._state == "warning"

    def test_boundary_value_12_hides_indicator(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """并发数恰好 12 时指示器隐藏（边界值）。"""
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(12)
        assert dialog.concurrency_indicator._state == "hidden"

    def test_boundary_value_13_shows_warning(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """并发数恰好 13 时指示器显示 warning（边界值）。"""
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(13)
        assert dialog.concurrency_indicator._state == "warning"

    def test_warning_to_hidden_on_decrease(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """从 >12 降回 ≤12 时指示器应隐藏。"""
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(16)
        assert dialog.concurrency_indicator._state == "warning"
        dialog.concurrency_spin.setValue(4)
        assert dialog.concurrency_indicator._state == "hidden"


# ---------------------------------------------------------------------------
# T-C5：重置为默认
# ---------------------------------------------------------------------------
class TestResetToDefaults:
    """「重置为默认」按钮行为。"""

    def test_reset_button_exists(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """对话框应包含 reset_button。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.reset_button is not None
        assert dialog.reset_button.text() == "重置为默认"

    def test_reset_restores_paths(
        self, qapp: QApplication, fake_settings: AppSettings, monkeypatch
    ) -> None:
        """确认重置后路径字段还原为默认值。"""
        # 用户确认
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.question",
            lambda *a, **k: 16384,  # QMessageBox.StandardButton.Yes
        )
        dialog = SettingsDialog(fake_settings)
        # 修改路径
        dialog.path_edit.setText("C:/modified/balcon.exe")
        dialog.blb2txt_path_edit.setText("C:/modified/blb2txt.exe")
        # 重置
        dialog._on_reset_to_defaults()
        defaults = AppSettings()
        assert dialog.path_edit.text() == defaults.balcon_path
        assert dialog.blb2txt_path_edit.text() == defaults.blb2txt_path

    def test_reset_restores_concurrency(
        self, qapp: QApplication, fake_settings: AppSettings, monkeypatch
    ) -> None:
        """确认重置后并发数还原为默认值。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.question",
            lambda *a, **k: 16384,  # Yes
        )
        dialog = SettingsDialog(fake_settings)
        dialog.concurrency_spin.setValue(16)
        dialog._on_reset_to_defaults()
        defaults = AppSettings()
        assert dialog.concurrency_spin.value() == defaults.max_concurrency

    def test_reset_restores_theme(
        self, qapp: QApplication, fake_settings: AppSettings, monkeypatch
    ) -> None:
        """确认重置后主题还原为默认值。"""
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.question",
            lambda *a, **k: 16384,  # Yes
        )
        dialog = SettingsDialog(fake_settings)
        dialog.theme_combo.setCurrentIndex(0)  # 改为亮色
        dialog._on_reset_to_defaults()
        defaults = AppSettings()
        assert dialog.get_theme() == defaults.theme

    def test_reset_cancelled_keeps_values(
        self, qapp: QApplication, fake_settings: AppSettings, monkeypatch
    ) -> None:
        """用户取消时字段保持修改后的值。"""
        # 用户取消（No）
        monkeypatch.setattr(
            "balcon_batch_tts.gui.main_window.QMessageBox.question",
            lambda *a, **k: 65536,  # QMessageBox.StandardButton.No
        )
        dialog = SettingsDialog(fake_settings)
        modified_path = "C:/modified/balcon.exe"
        dialog.path_edit.setText(modified_path)
        dialog._on_reset_to_defaults()
        assert dialog.path_edit.text() == modified_path


# ---------------------------------------------------------------------------
# T-C5：外观分组
# ---------------------------------------------------------------------------
class TestAppearanceGroup:
    """外观分组控件（主题/密度/字号缩放/动画开关）。"""

    def test_appearance_group_exists(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """对话框应包含 appearance_group。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.appearance_group is not None
        assert dialog.appearance_group.title() == "外观"

    def test_theme_combo_has_three_items(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """主题 comboBox 应有 3 项（亮色/暗色/跟随系统）。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.theme_combo, QComboBox)
        assert dialog.theme_combo.count() == 3
        assert dialog.theme_combo.itemText(0) == "亮色"
        assert dialog.theme_combo.itemText(1) == "暗色"
        assert dialog.theme_combo.itemText(2) == "跟随系统"

    def test_theme_combo_item_data(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """主题 comboBox 的 itemData 应为 light/dark/auto。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.theme_combo.itemData(0) == "light"
        assert dialog.theme_combo.itemData(1) == "dark"
        assert dialog.theme_combo.itemData(2) == "auto"

    def test_density_combo_has_two_items(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """密度 comboBox 应有 2 项（舒适/紧凑）。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.density_combo, QComboBox)
        assert dialog.density_combo.count() == 2
        assert dialog.density_combo.itemText(0) == "舒适"
        assert dialog.density_combo.itemText(1) == "紧凑"

    def test_density_combo_item_data(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """密度 comboBox 的 itemData 应为 comfortable/compact。"""
        dialog = SettingsDialog(fake_settings)
        assert dialog.density_combo.itemData(0) == "comfortable"
        assert dialog.density_combo.itemData(1) == "compact"

    def test_font_scale_slider_exists(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """字号缩放滑块应存在且范围为 85~130。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.font_scale_slider, QSlider)
        assert dialog.font_scale_slider.minimum() == 85
        assert dialog.font_scale_slider.maximum() == 130

    def test_animations_checkbox_exists(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """动画开关 checkbox 应存在。"""
        dialog = SettingsDialog(fake_settings)
        assert isinstance(dialog.animations_checkbox, QCheckBox)


# ---------------------------------------------------------------------------
# T-C5：Getter 方法
# ---------------------------------------------------------------------------
class TestAppearanceGetters:
    """外观分组 getter 方法返回值正确性。"""

    def test_get_theme_light(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_theme 在选择亮色时返回 'light'。"""
        dialog = SettingsDialog(fake_settings)
        dialog.theme_combo.setCurrentIndex(0)
        assert dialog.get_theme() == "light"

    def test_get_theme_dark(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_theme 在选择暗色时返回 'dark'。"""
        dialog = SettingsDialog(fake_settings)
        dialog.theme_combo.setCurrentIndex(1)
        assert dialog.get_theme() == "dark"

    def test_get_theme_auto(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_theme 在选择跟随系统时返回 'auto'。"""
        dialog = SettingsDialog(fake_settings)
        dialog.theme_combo.setCurrentIndex(2)
        assert dialog.get_theme() == "auto"

    def test_get_density_comfortable(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_density 在选择舒适时返回 'comfortable'。"""
        dialog = SettingsDialog(fake_settings)
        dialog.density_combo.setCurrentIndex(0)
        assert dialog.get_density() == "comfortable"

    def test_get_density_compact(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_density 在选择紧凑时返回 'compact'。"""
        dialog = SettingsDialog(fake_settings)
        dialog.density_combo.setCurrentIndex(1)
        assert dialog.get_density() == "compact"

    def test_get_font_scale(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_font_scale 返回滑块值 / 100。"""
        dialog = SettingsDialog(fake_settings)
        dialog.font_scale_slider.setValue(110)
        assert dialog.get_font_scale() == pytest.approx(1.10)

    def test_get_font_scale_min(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_font_scale 在最小值时返回 0.85。"""
        dialog = SettingsDialog(fake_settings)
        dialog.font_scale_slider.setValue(85)
        assert dialog.get_font_scale() == pytest.approx(0.85)

    def test_get_font_scale_max(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_font_scale 在最大值时返回 1.30。"""
        dialog = SettingsDialog(fake_settings)
        dialog.font_scale_slider.setValue(130)
        assert dialog.get_font_scale() == pytest.approx(1.30)

    def test_get_disable_animations_checked(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_disable_animations 在勾选时返回 True。"""
        dialog = SettingsDialog(fake_settings)
        dialog.animations_checkbox.setChecked(True)
        assert dialog.get_disable_animations() is True

    def test_get_disable_animations_unchecked(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """get_disable_animations 在未勾选时返回 False。"""
        dialog = SettingsDialog(fake_settings)
        dialog.animations_checkbox.setChecked(False)
        assert dialog.get_disable_animations() is False

    def test_initial_values_reflect_settings(
        self, qapp: QApplication, fake_settings: AppSettings
    ) -> None:
        """对话框初始值应反映 settings 中的值。"""
        fake_settings.theme = "dark"
        fake_settings.density = "compact"
        fake_settings.font_scale = 1.15
        fake_settings.disable_animations = True
        dialog = SettingsDialog(fake_settings)
        assert dialog.get_theme() == "dark"
        assert dialog.get_density() == "compact"
        assert dialog.get_font_scale() == pytest.approx(1.15)
        assert dialog.get_disable_animations() is True
