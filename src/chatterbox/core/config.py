"""balcon 配置模型模块。

定义 :class:`BalconConfig` dataclass，封装 balcon.exe 全部 63 个命令行参数。
提供参数列表生成、校验与序列化能力，作为 GUI 与命令行之间的统一数据载体。

字段命名采用 Python 风格（snake_case），通过类级常量 ``_FIELD_TO_OPTION``
映射到 balcon 选项名。所有字段均有默认值，:meth:`create_default` 返回的实例
即对应 balcon 的默认行为。

通用方法（:meth:`to_args` / :meth:`validate` / :meth:`to_dict` /
:meth:`from_dict` / :meth:`create_default`）由 :class:`BaseToolConfig` 提供，
本类仅负责声明字段、``_FIELD_TO_OPTION`` 与 ``_schema`` 三个 ``ClassVar``。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from chatterbox.core.base_config import BaseToolConfig
from chatterbox.core.parameter_schema import PARAMETER_SCHEMA, ParamSpec


class ConfigValidationError(Exception):
    """配置校验失败异常。

    Attributes:
        errors: 校验错误信息列表（每条对应一个字段的违规）。
    """

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class BalconConfig(BaseToolConfig):
    """balcon 全部命令行参数的配置模型（63 个字段）。

    字段分组与 :data:`parameter_schema.PARAMETER_SCHEMA` 保持一致，
    顺序亦与 schema 声明顺序相同，确保 :meth:`to_args` 输出顺序稳定。

    通用方法继承自 :class:`BaseToolConfig`，本类仅声明字段与两个
    ``ClassVar``（``_FIELD_TO_OPTION`` 与 ``_schema``）。
    """

    # --- Input ---
    f_files: list[str] = field(default_factory=list)
    fl_files: list[str] = field(default_factory=list)
    c_clipboard: bool = False
    t_texts: list[str] = field(default_factory=list)
    i_stdin: bool = False
    ln_lines: list[str] = field(default_factory=list)
    encoding: str | None = None

    # --- Output ---
    w_output: str | None = None
    o_stdout: bool = False
    raw: bool = False
    ignore_length: bool = False
    delete_file: bool = False

    # --- Voice ---
    n_voice: str | None = None
    id_langid: int | None = None
    s_rate: int | None = None
    p_pitch: int | None = None
    v_volume: int | None = None
    e_sentence_pause: int | None = None
    a_paragraph_pause: int | None = None

    # --- Device ---
    b_device_index: int | None = None
    r_device_name: str | None = None

    # --- AudioFormat ---
    fr_sample_rate: str | None = None
    bt_bit_depth: str | None = None
    ch_channels: str | None = None

    # --- Silence ---
    silence_begin: int | None = None
    silence_end: int | None = None

    # --- Dictionary ---
    d_dicts: list[str] = field(default_factory=list)

    # --- Subtitles ---
    sub: bool = False
    sub_format: str | None = None
    sub_fit: bool = False
    sub_fit_lib: bool = False
    sub_max: int | None = None

    # --- LRC ---
    lrc: bool = False
    lrc_length: int | None = None
    lrc_fname: str | None = None
    lrc_enc: str | None = None
    lrc_offset: int | None = None
    lrc_artist: str | None = None
    lrc_album: str | None = None
    lrc_title: str | None = None
    lrc_author: str | None = None
    lrc_creator: str | None = None
    lrc_sent: bool = False
    lrc_para: bool = False

    # --- SRT ---
    srt: bool = False
    srt_length: int | None = None
    srt_fname: str | None = None
    srt_enc: str | None = None

    # --- Visemes ---
    vs_visemes: str | None = None

    # --- TextFilter ---
    ignore_square_brackets: bool = False
    ignore_curly_brackets: bool = False
    ignore_angle_brackets: bool = False
    ignore_round_brackets: bool = False
    ignore_url: bool = False
    ignore_comments: bool = False

    # --- MultiVoice ---
    voice1_name: str | None = None
    voice1_langid: list[str] = field(default_factory=list)
    voice1_rate: int | None = None
    voice1_pitch: int | None = None
    voice1_volume: int | None = None
    voice1_roman: bool = False
    voice1_digit: bool = False
    voice1_length: int | None = None

    # 字段名 → balcon 选项名映射（按字段声明顺序，与 schema 一致）。
    # 使用 ClassVar 避免被 dataclass 当作字段处理。
    _FIELD_TO_OPTION: ClassVar[dict[str, str]] = {
        # Input
        "f_files": "-f",
        "fl_files": "-fl",
        "c_clipboard": "-c",
        "t_texts": "-t",
        "i_stdin": "-i",
        "ln_lines": "-ln",
        "encoding": "--encoding",
        # Output
        "w_output": "-w",
        "o_stdout": "-o",
        "raw": "--raw",
        "ignore_length": "--ignore-length",
        "delete_file": "--delete-file",
        # Voice
        "n_voice": "-n",
        "id_langid": "-id",
        "s_rate": "-s",
        "p_pitch": "-p",
        "v_volume": "-v",
        "e_sentence_pause": "-e",
        "a_paragraph_pause": "-a",
        # Device
        "b_device_index": "-b",
        "r_device_name": "-r",
        # AudioFormat
        "fr_sample_rate": "-fr",
        "bt_bit_depth": "-bt",
        "ch_channels": "-ch",
        # Silence
        "silence_begin": "--silence-begin",
        "silence_end": "--silence-end",
        # Dictionary
        "d_dicts": "-d",
        # Subtitles
        "sub": "-sub",
        "sub_format": "--sub-format",
        "sub_fit": "--sub-fit",
        "sub_fit_lib": "--sub-fit-lib",
        "sub_max": "--sub-max",
        # LRC
        "lrc": "-lrc",
        "lrc_length": "--lrc-length",
        "lrc_fname": "--lrc-fname",
        "lrc_enc": "--lrc-enc",
        "lrc_offset": "--lrc-offset",
        "lrc_artist": "--lrc-artist",
        "lrc_album": "--lrc-album",
        "lrc_title": "--lrc-title",
        "lrc_author": "--lrc-author",
        "lrc_creator": "--lrc-creator",
        "lrc_sent": "--lrc-sent",
        "lrc_para": "--lrc-para",
        # SRT
        "srt": "-srt",
        "srt_length": "--srt-length",
        "srt_fname": "--srt-fname",
        "srt_enc": "--srt-enc",
        # Visemes
        "vs_visemes": "-vs",
        # TextFilter
        "ignore_square_brackets": "--ignore-square-brackets",
        "ignore_curly_brackets": "--ignore-curly-brackets",
        "ignore_angle_brackets": "--ignore-angle-brackets",
        "ignore_round_brackets": "--ignore-round-brackets",
        "ignore_url": "--ignore-url",
        "ignore_comments": "--ignore-comments",
        # MultiVoice
        "voice1_name": "--voice1-name",
        "voice1_langid": "--voice1-langid",
        "voice1_rate": "--voice1-rate",
        "voice1_pitch": "--voice1-pitch",
        "voice1_volume": "--voice1-volume",
        "voice1_roman": "--voice1-roman",
        "voice1_digit": "--voice1-digit",
        "voice1_length": "--voice1-length",
    }

    # 参数声明列表，作为通用方法的查找来源。引用 balcon schema 常量。
    _schema: ClassVar[list[ParamSpec]] = PARAMETER_SCHEMA


__all__ = ["BalconConfig", "ConfigValidationError"]
