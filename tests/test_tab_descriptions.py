"""集中验证所有 Tab 的 ``tab_description`` 富化文本。

Task T-D4 新增覆盖：
- 每个 Tab 的 ``tab_description()`` 返回非空字符串
- 描述比 ``tab_title()`` 更详细（长度严格大于标题）
- 描述中包含至少一个命令行选项标识符（``-`` 开头的 token）
- 每个 Tab 至少包含一组关键字断言（参数名或选项名）

本文件不实例化任何 Tab（``tab_description`` 为 classmethod），
因此无需 ``QApplication`` fixture，避免无显示环境开销。
"""
from __future__ import annotations

import re

from balcon_batch_tts.gui.tabs.audio_format_tab import AudioFormatTab
from balcon_batch_tts.gui.tabs.blb2txt_archives_images_tab import (
    Blb2txtArchivesImagesTab,
)
from balcon_batch_tts.gui.tabs.blb2txt_dict_notes_tab import (
    Blb2txtDictNotesTab,
)
from balcon_batch_tts.gui.tabs.blb2txt_eml_tab import Blb2txtEmlTab
from balcon_batch_tts.gui.tabs.blb2txt_input_tab import Blb2txtInputTab
from balcon_batch_tts.gui.tabs.blb2txt_misc_tab import Blb2txtMiscTab
from balcon_batch_tts.gui.tabs.blb2txt_output_tab import Blb2txtOutputTab
from balcon_batch_tts.gui.tabs.blb2txt_split_tab import Blb2txtSplitTab
from balcon_batch_tts.gui.tabs.blb2txt_tables_csv_tab import (
    Blb2txtTablesCsvTab,
)
from balcon_batch_tts.gui.tabs.blb2txt_text_processing_tab import (
    Blb2txtTextProcessingTab,
)
from balcon_batch_tts.gui.tabs.device_tab import DeviceTab
from balcon_batch_tts.gui.tabs.dictionary_tab import DictionaryTab
from balcon_batch_tts.gui.tabs.input_tab import InputTab
from balcon_batch_tts.gui.tabs.lrc_tab import LrcTab
from balcon_batch_tts.gui.tabs.multi_voice_tab import MultiVoiceTab
from balcon_batch_tts.gui.tabs.output_tab import OutputTab
from balcon_batch_tts.gui.tabs.srt_tab import SrtTab
from balcon_batch_tts.gui.tabs.subtitles_tab import SubtitlesTab
from balcon_batch_tts.gui.tabs.text_filter_tab import TextFilterTab
from balcon_batch_tts.gui.tabs.visemes_tab import VisemesTab
from balcon_batch_tts.gui.tabs.voice_tab import VoiceTab

# 每个 Tab 类 + 至少一个期望出现的关键字（参数名或选项名）
# 用于在通用断言之外补充针对性校验，确保描述与该 Tab 的参数对应。
_TAB_AND_KEYWORD: list[tuple[type, str]] = [
    (VoiceTab, "语速"),
    (DeviceTab, "-b"),
    (InputTab, "-c"),
    (OutputTab, "--delete-file"),
    (AudioFormatTab, "-fr"),
    (DictionaryTab, "-d"),
    (TextFilterTab, "--ignore-url"),
    (SrtTab, "--srt-enc"),
    (LrcTab, "--lrc-offset"),
    (SubtitlesTab, "--sub-max"),
    (MultiVoiceTab, "--voice1-rate"),
    (VisemesTab, "-vs"),
    (Blb2txtInputTab, "-if"),
    (Blb2txtOutputTab, "-n"),
    (Blb2txtArchivesImagesTab, "-dll"),
    (Blb2txtDictNotesTab, "--extract-summary"),
    (Blb2txtEmlTab, "--eml-save"),
    (Blb2txtMiscTab, "-cfg"),
    (Blb2txtSplitTab, "-m"),
    (Blb2txtTablesCsvTab, "--csv-comma"),
    (Blb2txtTextProcessingTab, "--remove-spaces"),
]

# 提取描述中所有以 ``-`` 开头的 token（如 ``-s``、``--silence-begin``）
_OPTION_PATTERN = re.compile(r"(?<![\w-])(--?[\w-]+)")


# ---------------------------------------------------------------------------
# 通用断言：遍历所有 Tab 类
# ---------------------------------------------------------------------------
def test_all_tab_descriptions_non_empty() -> None:
    """每个 Tab 的 ``tab_description()`` 应返回非空字符串。"""
    for tab_cls, _kw in _TAB_AND_KEYWORD:
        desc = tab_cls.tab_description()
        assert isinstance(desc, str), (
            f"{tab_cls.__name__}.tab_description() 应返回 str, "
            f"实际类型 {type(desc).__name__}"
        )
        assert desc.strip(), f"{tab_cls.__name__}.tab_description() 返回空字符串"


def test_all_tab_descriptions_richer_than_title() -> None:
    """``tab_description()`` 应比 ``tab_title()`` 更详细（长度严格大于标题）。"""
    for tab_cls, _kw in _TAB_AND_KEYWORD:
        desc = tab_cls.tab_description()
        title = tab_cls.tab_title()
        assert len(desc) > len(title), (
            f"{tab_cls.__name__}.tab_description() 长度 ({len(desc)}) "
            f"应大于 tab_title() 长度 ({len(title)})"
        )


def test_all_tab_descriptions_contain_option_token() -> None:
    """每个描述应包含至少一个命令行选项 token（``-`` 开头）。"""
    for tab_cls, _kw in _TAB_AND_KEYWORD:
        desc = tab_cls.tab_description()
        options = _OPTION_PATTERN.findall(desc)
        assert options, (
            f"{tab_cls.__name__}.tab_description() 未包含任何命令行选项 token: "
            f"{desc!r}"
        )


# ---------------------------------------------------------------------------
# 针对性关键字断言（参数名或选项名）
# ---------------------------------------------------------------------------
def test_tab_description_keywords() -> None:
    """针对每个 Tab 断言其描述中包含预定义的关键字。"""
    for tab_cls, keyword in _TAB_AND_KEYWORD:
        desc = tab_cls.tab_description()
        assert keyword in desc, (
            f"{tab_cls.__name__}.tab_description() 应包含关键字 {keyword!r}, "
            f"实际描述: {desc!r}"
        )


# ---------------------------------------------------------------------------
# 个别 Tab 的关键字参数范围抽样验证（确保范围/默认值出现在描述中）
# ---------------------------------------------------------------------------
def test_voice_tab_description_contains_rate_range() -> None:
    """VoiceTab 描述应包含语速范围 -10~10。"""
    desc = VoiceTab.tab_description()
    assert "-10~10" in desc, f"VoiceTab 描述应包含 -10~10, 实际: {desc!r}"
    assert "默认 0" in desc


def test_voice_tab_description_contains_volume_default() -> None:
    """VoiceTab 描述应包含音量默认 100。"""
    desc = VoiceTab.tab_description()
    assert "默认 100" in desc, f"VoiceTab 描述应包含 '默认 100', 实际: {desc!r}"


def test_subtitles_tab_description_contains_sub_max_range() -> None:
    """SubtitlesTab 描述应包含 --sub-max 范围 -10~200。"""
    desc = SubtitlesTab.tab_description()
    assert "-10~200" in desc, (
        f"SubtitlesTab 描述应包含 -10~200, 实际: {desc!r}"
    )


def test_multi_voice_tab_description_contains_length_range() -> None:
    """MultiVoiceTab 描述应包含 --voice1-length 范围 0~1000。"""
    desc = MultiVoiceTab.tab_description()
    assert "0~1000" in desc, (
        f"MultiVoiceTab 描述应包含 0~1000, 实际: {desc!r}"
    )


def test_lrc_tab_description_contains_offset_range() -> None:
    """LrcTab 描述应包含 --lrc-offset 范围 -60000~60000。"""
    desc = LrcTab.tab_description()
    assert "-60000~60000" in desc, (
        f"LrcTab 描述应包含 -60000~60000, 实际: {desc!r}"
    )


def test_blb2txt_output_tab_description_contains_naming_choices() -> None:
    """Blb2txtOutputTab 描述应包含命名模式可选值 1/2/3。"""
    desc = Blb2txtOutputTab.tab_description()
    assert "1=原名" in desc and "3=序号" in desc, (
        f"Blb2txtOutputTab 描述应包含命名模式选项, 实际: {desc!r}"
    )
