"""SAPI5 配置模型模块。

定义 :class:`SapiConfig` dataclass，封装 SAPI5 语音合成参数，作为 GUI 与
:mod:`chatterbox.core.sapi_runner` 之间的统一数据载体。

与基于命令行工具（如 balcon、blb2txt）的配置类不同，SAPI5 通过 COM 接口
直接调用，不经过命令行参数。因此 ``_FIELD_TO_OPTION`` 与 ``_schema`` 声明
为空，仅为复用 :class:`BaseToolConfig` 提供的 :meth:`to_dict` /
:meth:`from_dict` / :meth:`create_default` 序列化能力；:meth:`to_args` 与
:meth:`validate` 在空 schema 下返回空结果。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from chatterbox.core.base_config import BaseToolConfig
from chatterbox.core.parameter_schema import ParamSpec


@dataclass
class SapiConfig(BaseToolConfig):
    """SAPI5 语音合成参数的配置模型。

    字段对应 :mod:`chatterbox.core.sapi_runner` 中合成函数的入参。
    所有字段均有默认值，:meth:`create_default` 返回的实例对应 SAPI5 系统
    默认语音、正常语速、最大音量、正常音调、UTF-8 编码。

    由于 SAPI5 不走命令行，``_FIELD_TO_OPTION`` 与 ``_schema`` 为空，
    仅 :meth:`to_dict` / :meth:`from_dict` / :meth:`create_default` 可用。

    Attributes:
        voice_name: SAPI5 语音名称；空字符串表示使用系统默认语音。
        rate: 语速，范围 -10~10，0 为正常语速。
        volume: 音量，范围 0~100，100 为最大音量。
        pitch: 音调，范围 -10~10，0 为正常音调；通过 SAPI5 XML
            ``<pitch absmiddle="...">`` 标记实现。
        input_encoding: 输入文本文件的字符编码。
        audio_format: SAPI5 SpeechAudioFormatType 枚举值，决定合成音频的
            采样率/位深/声道。常用值：
            - 22 = SAFTPCM_16kHz_16Bit_Mono（默认，向后兼容）
            - 21 = SAFTPCM_22kHz_16Bit_Mono
            - 31 = SAFTPCM_44kHz_16Bit_Stereo
            - 32 = SAFTPCM_48kHz_16Bit_Stereo
        max_text_bytes: 非 WAV 模式下走 SpMemoryStream 的文本字节上限。超过
            此阈值的文本降级到文件模式（合成到临时 WAV → ffmpeg 转码 → 删除
            临时 WAV），避免大文本下 12 并发 SpMemoryStream 导致 OOM。
            默认 262144（256KB）。
    """

    voice_name: str = ""
    rate: int = 0
    volume: int = 100
    pitch: int = 0
    input_encoding: str = "utf-8"
    audio_format: int = 22  # SAPI5 SpeechAudioFormatType，默认 16kHz/16bit/Mono
    max_text_bytes: int = 262144  # 256KB, 超过此大小的文本在非WAV模式下降级到文件模式

    # SAPI5 不走命令行，无字段→选项映射；声明为空仅为满足 BaseToolConfig 接口。
    _FIELD_TO_OPTION: ClassVar[dict[str, str]] = {}
    # SAPI5 不走命令行，无 schema 声明；声明为空仅为满足 BaseToolConfig 接口。
    _schema: ClassVar[list[ParamSpec]] = []


__all__ = ["SapiConfig"]
