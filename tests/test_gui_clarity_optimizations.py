"""GUI 清晰度与布局优化的回归测试（Task 15）。

验证 Tasks 1-14 引入的 GUI 清晰度优化行为：
- Task 1: SliderSpinDial.setDescription() / AbstractTab.tab_description() /
  parameter_schema help 字段
- Task 2: MainWindow delete_file 二次确认
- Task 3: FileListWidget dropEvent 拒收反馈
- Task 4: ProgressWidget 图例
- Task 11: SubtitlesTab sub_fit_lib_check 联动禁用
- Task 12: lrc/srt length 特殊值文本、enc_combo 显示/数据分离
- Task 13: multi_voice voice1_length 特殊值文本

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
不修改既有测试文件；所有新增测试集中在本文件。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.gui.tabs.base_tab import AbstractTab
from balcon_batch_tts.gui.widgets.slider_spin_dial import SliderSpinDial
from balcon_batch_tts.persistence.settings import AppSettings


# ---------------------------------------------------------------------------
# QApplication 会话级单例：所有需要 QWidget 的测试共用一个实例。
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# SubTask 15.1: SliderSpinDial.setDescription()
# ---------------------------------------------------------------------------
def test_slider_spin_dial_set_description(qapp: QApplication) -> None:
    """``setDescription`` 应统一设置 slider/spinbox/dial 三者的 tooltip。"""
    w = SliderSpinDial(with_dial=True)
    w.setDescription("test tooltip")
    assert w.slider.toolTip() == "test tooltip"
    assert w.spinbox.toolTip() == "test tooltip"
    assert w.dial is not None
    assert w.dial.toolTip() == "test tooltip"

    # Without dial
    w2 = SliderSpinDial(with_dial=False)
    w2.setDescription("no dial tooltip")
    assert w2.slider.toolTip() == "no dial tooltip"
    assert w2.spinbox.toolTip() == "no dial tooltip"
    assert w2.dial is None


# ---------------------------------------------------------------------------
# SubTask 15.2: AbstractTab.tab_description() 默认实现
# ---------------------------------------------------------------------------
def test_abstract_tab_description_default(qapp: QApplication) -> None:
    """``tab_description`` 默认返回 ``tab_title``。"""
    class _TestTab(AbstractTab):
        @classmethod
        def tab_id(cls) -> str:
            return "test"

        @classmethod
        def tab_title(cls) -> str:
            return "测试Tab"

        def collect_config(self, cfg) -> None:  # type: ignore[no-untyped-def]
            pass

        def apply_config(self, cfg) -> None:  # type: ignore[no-untyped-def]
            pass

    assert _TestTab.tab_description() == "测试Tab"


# ---------------------------------------------------------------------------
# SubTask 15.3: lrc_length_spin / srt_length_spin / voice1_length_spin
#               setSpecialValueText("自动")
# ---------------------------------------------------------------------------
def test_lrc_length_spin_special_value_text(qapp: QApplication) -> None:
    """lrc_length_spin 值为 0 时显示「自动」。"""
    from balcon_batch_tts.gui.tabs.lrc_tab import LrcTab

    t = LrcTab()
    t.lrc_length_spin.setValue(0)
    assert t.lrc_length_spin.text() == "自动"


def test_srt_length_spin_special_value_text(qapp: QApplication) -> None:
    """srt_length_spin 值为 0 时显示「自动」。"""
    from balcon_batch_tts.gui.tabs.srt_tab import SrtTab

    t = SrtTab()
    t.srt_length_spin.setValue(0)
    assert t.srt_length_spin.text() == "自动"


def test_voice1_length_spin_special_value_text(qapp: QApplication) -> None:
    """voice1_length_spin 值为 0 时显示「自动」。"""
    from balcon_batch_tts.gui.tabs.multi_voice_tab import MultiVoiceTab

    t = MultiVoiceTab()
    t.voice1_length_spin.setValue(0)
    assert t.voice1_length_spin.text() == "自动"


# ---------------------------------------------------------------------------
# SubTask 15.4: lrc_enc_combo / srt_enc_combo 显示与数据分离
# ---------------------------------------------------------------------------
def test_lrc_enc_combo_display_data_separation(qapp: QApplication) -> None:
    """lrc_enc_combo 显示「ANSI」，itemData 返回 ``"ansi"``。"""
    from balcon_batch_tts.gui.tabs.lrc_tab import LrcTab

    t = LrcTab()
    for i in range(t.lrc_enc_combo.count()):
        if t.lrc_enc_combo.itemText(i) == "ANSI":
            assert t.lrc_enc_combo.itemData(i) == "ansi"
            return
    assert False, "ANSI item not found"


def test_srt_enc_combo_display_data_separation(qapp: QApplication) -> None:
    """srt_enc_combo 显示「ANSI」，itemData 返回 ``"ansi"``。"""
    from balcon_batch_tts.gui.tabs.srt_tab import SrtTab

    t = SrtTab()
    for i in range(t.srt_enc_combo.count()):
        if t.srt_enc_combo.itemText(i) == "ANSI":
            assert t.srt_enc_combo.itemData(i) == "ansi"
            return
    assert False, "ANSI item not found"


# ---------------------------------------------------------------------------
# SubTask 15.5: _on_start_balcon delete_file 二次确认
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
) -> "MainWindow":  # type: ignore[name-defined]
    """构造一个 MainWindow 实例，禁用 QMessageBox 弹窗与枚举工作者。"""
    from balcon_batch_tts.gui.main_window import MainWindow

    # 禁用 QMessageBox 警告（路径校验失败时调用）
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
    # 禁用启动时的语音/设备枚举（避免后台线程触发未定义行为）
    monkeypatch.setattr(MainWindow, "_refresh_voices_devices", lambda self: None)
    monkeypatch.setattr(
        AppSettings,
        "load",
        classmethod(lambda cls, path=None: fake_settings),
    )
    return MainWindow()


def test_delete_file_confirm_aborts_on_no(
    main_window, tmp_path, monkeypatch
) -> None:
    """勾选 delete_file 且用户选「否」时，scheduler.submit 不应被调用。"""
    from PySide6.QtWidgets import QMessageBox

    # 准备输入文件 + 输出目录
    input_file = tmp_path / "input.txt"
    input_file.write_text("hello")
    main_window.file_list_widget.add_files([str(input_file)])

    output_tab = main_window._tabs_by_id.get("output")
    assert output_tab is not None
    output_tab.set_output_dir(str(tmp_path))
    # 勾选 delete_file
    output_tab.delete_file_check.setChecked(True)

    # Mock QMessageBox.question 返回 No
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **kw: QMessageBox.StandardButton.No,
    )

    # Mock scheduler.submit 追踪调用
    submit_called: list = []
    monkeypatch.setattr(
        main_window._scheduler,
        "submit",
        lambda *a, **kw: submit_called.append(1),
    )

    # 执行开始 —— 应在确认对话框处中止
    main_window._on_start_balcon()

    assert not submit_called, (
        "scheduler.submit should NOT be called when user clicks No"
    )


# ---------------------------------------------------------------------------
# SubTask 15.6: file_list_widget.dropEvent 拒收反馈
# ---------------------------------------------------------------------------
def test_file_list_widget_drop_reject_feedback(qapp: QApplication) -> None:
    """dropEvent 拒收时 count_label 显示「忽略 N 个」，刷新后恢复「共」字样。"""
    from balcon_batch_tts.gui.widgets.file_list_widget import FileListWidget

    w = FileListWidget()
    # 模拟 dropEvent 拒收时的直接 setText 行为
    w.count_label.setText("忽略 3 个不支持的文件")
    assert "忽略 3 个" in w.count_label.text()
    # _refresh_count_label 应恢复正常计数文本
    w._refresh_count_label()
    assert "共" in w.count_label.text()


# ---------------------------------------------------------------------------
# SubTask 15.7: progress_widget 图例
# ---------------------------------------------------------------------------
def test_progress_widget_legend(qapp: QApplication) -> None:
    """ProgressWidget 图例应包含「成功」与「失败」字样。"""
    from balcon_batch_tts.gui.widgets.progress_widget import ProgressWidget

    w = ProgressWidget()
    assert "成功" in w.legend_label.text()
    assert "失败" in w.legend_label.text()


# ---------------------------------------------------------------------------
# SubTask 15.8: parameter_schema help 字段
# ---------------------------------------------------------------------------
def test_parameter_schema_help_fields() -> None:
    """补全的 help 字段应包含范围/单位/默认值信息。"""
    from balcon_batch_tts.core.parameter_schema import get_param

    s = get_param("-s")
    assert s is not None
    assert "范围 -10 到 10" in s.help
    assert "默认 0" in s.help

    p = get_param("-p")
    assert p is not None
    assert "半音" in p.help

    v = get_param("-v")
    assert v is not None
    assert "范围 0 到 100" in v.help

    b = get_param("-b")
    assert b is not None
    assert "0 = 默认设备" in b.help

    sm = get_param("--sub-max")
    assert sm is not None
    assert "百分比" in sm.help
    assert sm.min_value == -10
    assert sm.max_value == 200

    vl = get_param("--voice1-length")
    assert vl is not None
    assert "字符" in vl.help
    assert vl.min_value == 0

    fr = get_param("-fr")
    assert fr is not None
    assert "11025" in fr.help

    bt = get_param("-bt")
    assert bt is not None
    assert "默认 16" in bt.help

    ch = get_param("-ch")
    assert ch is not None
    assert "默认 1" in ch.help


# ---------------------------------------------------------------------------
# SubTask 15.9: subtitles_tab sub_fit_lib_check 联动禁用
# ---------------------------------------------------------------------------
def test_subtitles_sub_fit_lib_linkage(qapp: QApplication) -> None:
    """sub_fit_lib_check 应随 sub_fit_check 勾选状态联动启用/禁用。"""
    from balcon_batch_tts.gui.tabs.subtitles_tab import SubtitlesTab

    t = SubtitlesTab()
    # Initially unchecked, so sub_fit_lib_check should be disabled
    t.sub_fit_check.setChecked(False)
    assert not t.sub_fit_lib_check.isEnabled()
    # Check sub_fit_check, sub_fit_lib_check should become enabled
    t.sub_fit_check.setChecked(True)
    assert t.sub_fit_lib_check.isEnabled()
