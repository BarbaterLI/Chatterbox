"""balcon 参数声明式 Schema。

以 dataclass 形式声明 balcon.exe 全部命令行参数，作为 GUI 动态渲染与
配置校验的统一数据源。新增 balcon 参数时仅需在此模块追加一条
``ParamSpec`` 记录，无需改动 GUI 代码。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterable


class ParamKind(str, enum.Enum):
    """balcon 参数类型枚举。

    继承 ``str`` 便于直接序列化与作为字典键使用。
    """

    flag = "flag"
    int = "int"
    str = "str"
    file = "file"
    choice = "choice"


@dataclass
class ParamSpec:
    """单个 balcon 参数的声明式描述。

    Attributes:
        name: 主选项名（如 ``-s`` 或 ``--lrc-length``）。
        alias: 别名（如 ``-enc`` 是 ``--encoding`` 的别名）。
        kind: 参数类型，见 :class:`ParamKind`。
        group: GUI 分组名（如 ``Voice``、``LRC``）。
        multiple: 是否允许多值（balcon 中可重复出现的选项）。
        min_value: 数值类型的最小值（含）。
        max_value: 数值类型的最大值（含）。
        choices: ``choice`` 类型的可选值列表。
        default: 默认值；``flag`` 类型应为 ``bool`` 或 ``None``。
        help: 中文帮助文本。
    """

    name: str
    kind: ParamKind
    group: str
    alias: str | None = None
    multiple: bool = False
    min_value: int | None = None
    max_value: int | None = None
    choices: list[str] | None = None
    default: str | int | bool | None = None
    help: str = ""

    def __post_init__(self) -> None:
        if self.kind is ParamKind.choice:
            if not self.choices:
                raise ValueError(
                    f"choice 类型参数 {self.name!r} 必须提供非空 choices"
                )
        if self.kind is ParamKind.flag:
            if self.default is not None and not isinstance(self.default, bool):
                raise TypeError(
                    f"flag 类型参数 {self.name!r} 的 default 必须是 bool 或 None，"
                    f"实际为 {type(self.default).__name__}"
                )


# ---------------------------------------------------------------------------
# balcon 全部参数声明（按分组顺序排列）
# ---------------------------------------------------------------------------
PARAMETER_SCHEMA: list[ParamSpec] = [
    # --- Input ---
    ParamSpec(
        name="-f",
        kind=ParamKind.file,
        group="Input",
        multiple=True,
        help="输入文本文件",
    ),
    ParamSpec(
        name="-fl",
        kind=ParamKind.file,
        group="Input",
        multiple=True,
        help="输入文件列表文件",
    ),
    ParamSpec(
        name="-c",
        kind=ParamKind.flag,
        group="Input",
        help="从剪贴板获取文本",
    ),
    ParamSpec(
        name="-t",
        kind=ParamKind.str,
        group="Input",
        multiple=True,
        help="命令行文本",
    ),
    ParamSpec(
        name="-i",
        kind=ParamKind.flag,
        group="Input",
        help="从 STDIN 获取文本",
    ),
    ParamSpec(
        name="-ln",
        kind=ParamKind.str,
        group="Input",
        multiple=True,
        help="选择行号（如 26-34）",
    ),
    ParamSpec(
        name="--encoding",
        alias="-enc",
        kind=ParamKind.choice,
        group="Input",
        choices=["ansi", "utf8", "unicode"],
        help="输入文本编码",
    ),

    # --- Output ---
    ParamSpec(
        name="-w",
        kind=ParamKind.file,
        group="Output",
        help="输出 WAV 文件",
    ),
    ParamSpec(
        name="-o",
        kind=ParamKind.flag,
        group="Output",
        help="输出到 STDOUT",
    ),
    ParamSpec(
        name="--raw",
        kind=ParamKind.flag,
        group="Output",
        help="原始 PCM（无 WAV 头）",
    ),
    ParamSpec(
        name="--ignore-length",
        alias="-il",
        kind=ParamKind.flag,
        group="Output",
        help="省略 WAV 头长度",
    ),
    ParamSpec(
        name="--delete-file",
        alias="-df",
        kind=ParamKind.flag,
        group="Output",
        help="完成后删除输入文件",
    ),

    # --- Voice ---
    ParamSpec(
        name="-n",
        kind=ParamKind.str,
        group="Voice",
        help="语音名称",
    ),
    ParamSpec(
        name="-id",
        kind=ParamKind.int,
        group="Voice",
        help="语言 ID",
    ),
    ParamSpec(
        name="-s",
        kind=ParamKind.int,
        group="Voice",
        min_value=-10,
        max_value=10,
        default=0,
        help="语速。范围 -10 到 10，默认 0，正值加快、负值减慢。",
    ),
    ParamSpec(
        name="-p",
        kind=ParamKind.int,
        group="Voice",
        min_value=-10,
        max_value=10,
        default=0,
        help="音调。范围 -10 到 10，默认 0，单位半音。",
    ),
    ParamSpec(
        name="-v",
        kind=ParamKind.int,
        group="Voice",
        min_value=0,
        max_value=100,
        default=100,
        help="音量。范围 0 到 100，默认 0（使用 balcon 默认），单位百分比。",
    ),
    ParamSpec(
        name="-e",
        kind=ParamKind.int,
        group="Voice",
        min_value=0,
        default=0,
        help="句间停顿（毫秒）",
    ),
    ParamSpec(
        name="-a",
        kind=ParamKind.int,
        group="Voice",
        min_value=0,
        default=0,
        help="段间停顿（毫秒）",
    ),

    # --- Device ---
    ParamSpec(
        name="-b",
        kind=ParamKind.int,
        group="Device",
        min_value=0,
        help="音频输出设备索引。0 = 默认设备（不传 -b）。",
    ),
    ParamSpec(
        name="-r",
        kind=ParamKind.str,
        group="Device",
        help="音频输出设备名称",
    ),

    # --- AudioFormat ---
    ParamSpec(
        name="-fr",
        kind=ParamKind.choice,
        group="AudioFormat",
        choices=["8", "11", "12", "16", "22", "24", "32", "44", "48"],
        help="采样率（kHz 近似值）。注意：11=11025 Hz，22=22050 Hz，44=44100 Hz。",
    ),
    ParamSpec(
        name="-bt",
        kind=ParamKind.choice,
        group="AudioFormat",
        choices=["8", "16"],
        help="位深。可选 8/16，默认 16（balcon 默认）。",
    ),
    ParamSpec(
        name="-ch",
        kind=ParamKind.choice,
        group="AudioFormat",
        choices=["1", "2"],
        help="声道数。可选 1/2，默认 1（单声道，balcon 默认）。",
    ),

    # --- Silence ---
    ParamSpec(
        name="--silence-begin",
        alias="-sb",
        kind=ParamKind.int,
        group="Silence",
        min_value=0,
        default=0,
        help="起始静音（毫秒）",
    ),
    ParamSpec(
        name="--silence-end",
        alias="-se",
        kind=ParamKind.int,
        group="Silence",
        min_value=0,
        default=0,
        help="结尾静音（毫秒）",
    ),

    # --- Dictionary ---
    ParamSpec(
        name="-d",
        kind=ParamKind.file,
        group="Dictionary",
        multiple=True,
        help="字典文件（*.BXD, *.DIC, *.REX）",
    ),

    # --- Subtitles ---
    ParamSpec(
        name="-sub",
        kind=ParamKind.flag,
        group="Subtitles",
        help="将输入作为字幕处理",
    ),
    ParamSpec(
        name="--sub-format",
        kind=ParamKind.choice,
        group="Subtitles",
        choices=["srt", "lrc", "ssa", "ass", "smi", "vtt"],
        help="字幕格式",
    ),
    ParamSpec(
        name="--sub-fit",
        alias="-sf",
        kind=ParamKind.flag,
        group="Subtitles",
        help="自动提高语速以适配时间间隔",
    ),
    ParamSpec(
        name="--sub-fit-lib",
        alias="-sfl",
        kind=ParamKind.flag,
        group="Subtitles",
        help="使用 SoundTouch 库适配时间间隔",
    ),
    ParamSpec(
        name="--sub-max",
        alias="-sm",
        kind=ParamKind.int,
        group="Subtitles",
        min_value=-10,
        max_value=200,
        help="最大语速率。范围 -10 到 200，默认 0（不限制），单位百分比（100=1倍速）。",
    ),

    # --- LRC ---
    ParamSpec(
        name="-lrc",
        kind=ParamKind.flag,
        group="LRC",
        help="创建 LRC 文件",
    ),
    ParamSpec(
        name="--lrc-length",
        kind=ParamKind.int,
        group="LRC",
        min_value=1,
        help="LRC 文本行最大长度（字符）",
    ),
    ParamSpec(
        name="--lrc-fname",
        kind=ParamKind.file,
        group="LRC",
        help="LRC 文件名",
    ),
    ParamSpec(
        name="--lrc-enc",
        kind=ParamKind.choice,
        group="LRC",
        choices=["ansi", "utf8", "unicode"],
        default="ansi",
        help="LRC 文件编码",
    ),
    ParamSpec(
        name="--lrc-offset",
        kind=ParamKind.int,
        group="LRC",
        help="LRC 时间偏移（毫秒）",
    ),
    ParamSpec(
        name="--lrc-artist",
        kind=ParamKind.str,
        group="LRC",
        help="LRC artist 标签",
    ),
    ParamSpec(
        name="--lrc-album",
        kind=ParamKind.str,
        group="LRC",
        help="LRC album 标签",
    ),
    ParamSpec(
        name="--lrc-title",
        kind=ParamKind.str,
        group="LRC",
        help="LRC title 标签",
    ),
    ParamSpec(
        name="--lrc-author",
        kind=ParamKind.str,
        group="LRC",
        help="LRC author 标签",
    ),
    ParamSpec(
        name="--lrc-creator",
        kind=ParamKind.str,
        group="LRC",
        help="LRC creator 标签",
    ),
    ParamSpec(
        name="--lrc-sent",
        kind=ParamKind.flag,
        group="LRC",
        help="句后插入空行",
    ),
    ParamSpec(
        name="--lrc-para",
        kind=ParamKind.flag,
        group="LRC",
        help="段后插入空行",
    ),

    # --- SRT ---
    ParamSpec(
        name="-srt",
        kind=ParamKind.flag,
        group="SRT",
        help="创建 SRT 文件",
    ),
    ParamSpec(
        name="--srt-length",
        kind=ParamKind.int,
        group="SRT",
        min_value=1,
        help="SRT 文本行最大长度（字符）",
    ),
    ParamSpec(
        name="--srt-fname",
        kind=ParamKind.file,
        group="SRT",
        help="SRT 文件名",
    ),
    ParamSpec(
        name="--srt-enc",
        kind=ParamKind.choice,
        group="SRT",
        choices=["ansi", "utf8", "unicode"],
        default="ansi",
        help="SRT 文件编码",
    ),

    # --- Visemes ---
    ParamSpec(
        name="-vs",
        kind=ParamKind.file,
        group="Visemes",
        help="visemes 输出文本文件",
    ),

    # --- TextFilter ---
    ParamSpec(
        name="--ignore-square-brackets",
        alias="-isb",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略 [方括号] 内文本",
    ),
    ParamSpec(
        name="--ignore-curly-brackets",
        alias="-icb",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略 {花括号} 内文本",
    ),
    ParamSpec(
        name="--ignore-angle-brackets",
        alias="-iab",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略 <尖括号> 内文本",
    ),
    ParamSpec(
        name="--ignore-round-brackets",
        alias="-irb",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略 (圆括号) 内文本",
    ),
    ParamSpec(
        name="--ignore-url",
        alias="-iu",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略 URL",
    ),
    ParamSpec(
        name="--ignore-comments",
        alias="-ic",
        kind=ParamKind.flag,
        group="TextFilter",
        help="忽略注释（// 和 /* */）",
    ),

    # --- MultiVoice ---
    ParamSpec(
        name="--voice1-name",
        kind=ParamKind.str,
        group="MultiVoice",
        help="外文词附加语音名称",
    ),
    ParamSpec(
        name="--voice1-langid",
        kind=ParamKind.str,
        group="MultiVoice",
        multiple=True,
        help="外文词语言 ID（逗号分隔或多次指定）",
    ),
    ParamSpec(
        name="--voice1-rate",
        kind=ParamKind.int,
        group="MultiVoice",
        min_value=-10,
        max_value=10,
        default=0,
        help="附加语音语速",
    ),
    ParamSpec(
        name="--voice1-pitch",
        kind=ParamKind.int,
        group="MultiVoice",
        min_value=-10,
        max_value=10,
        default=0,
        help="附加语音音调",
    ),
    ParamSpec(
        name="--voice1-volume",
        kind=ParamKind.int,
        group="MultiVoice",
        min_value=0,
        max_value=100,
        default=100,
        help="附加语音音量",
    ),
    ParamSpec(
        name="--voice1-roman",
        kind=ParamKind.flag,
        group="MultiVoice",
        help="用默认语音读罗马数字",
    ),
    ParamSpec(
        name="--voice1-digit",
        kind=ParamKind.flag,
        group="MultiVoice",
        help="用默认语音读数字",
    ),
    ParamSpec(
        name="--voice1-length",
        kind=ParamKind.int,
        group="MultiVoice",
        min_value=0,
        help="外文文本最小长度。范围 0 到 1000，默认 0（自动），单位字符。",
    ),
]


# ---------------------------------------------------------------------------
# 分组聚合与查找工具
# ---------------------------------------------------------------------------
ALL_GROUP_NAMES: list[str] = [
    "Input",
    "Output",
    "Voice",
    "Device",
    "AudioFormat",
    "Silence",
    "Dictionary",
    "Subtitles",
    "LRC",
    "SRT",
    "Visemes",
    "TextFilter",
    "MultiVoice",
]


GROUP_TITLES: dict[str, str] = {
    "Input": "输入",
    "Output": "输出",
    "Voice": "语音",
    "Device": "音频设备",
    "AudioFormat": "音频格式",
    # Silence 已合并入 Voice Tab（GUI 层）
    "Silence": "静音",
    "Dictionary": "字典",
    "Subtitles": "字幕",
    "LRC": "LRC 歌词",
    "SRT": "SRT 字幕",
    "Visemes": "Visemes 视位",
    "TextFilter": "文本过滤",
    "MultiVoice": "多语音（外文词）",
}


def _build_params_by_group(schema: Iterable[ParamSpec]) -> dict[str, list[ParamSpec]]:
    grouped: dict[str, list[ParamSpec]] = {name: [] for name in ALL_GROUP_NAMES}
    for spec in schema:
        if spec.group not in grouped:
            # 防御性：schema 中出现了 ALL_GROUP_NAMES 之外的分组。
            grouped[spec.group] = []
        grouped[spec.group].append(spec)
    return grouped


PARAMS_BY_GROUP: dict[str, list[ParamSpec]] = _build_params_by_group(PARAMETER_SCHEMA)


def get_param(name: str) -> ParamSpec | None:
    """按主选项名或别名查找 ``ParamSpec``。

    Args:
        name: 选项名，可以是主名（如 ``--encoding``）或别名（如 ``-enc``）。

    Returns:
        匹配到的 ``ParamSpec``；未找到时返回 ``None``。
    """
    for spec in PARAMETER_SCHEMA:
        if spec.name == name or spec.alias == name:
            return spec
    return None


__all__ = [
    "ParamKind",
    "ParamSpec",
    "PARAMETER_SCHEMA",
    "PARAMS_BY_GROUP",
    "ALL_GROUP_NAMES",
    "GROUP_TITLES",
    "get_param",
]
