"""SAPI5 COM 封装模块。

提供 Windows SAPI5 语音合成的 COM 调用封装，包括语音枚举、合成到文件、
合成到内存以及线程本地 SpVoice 池管理。

模块通过 pywin32 调用 SAPI5 COM 接口，所有 COM 异常均封装为
:class:`SapiError` 以便上层统一处理。每个使用 SpVoice 的线程应先调用
:func:`init_com` 初始化 COM（幂等，每线程仅实际初始化一次）。线程退出前
调用 :func:`uninit_thread_com` 原子清理 SpVoice 引用并释放 COM；SpVoice
进入异常状态时调用 :func:`invalidate_thread_voice` 失效缓存实例。

语音令牌缓存：每个线程通过 ``_thread_local.voice_token_cache`` 字典缓存
"语音名称 → voice token"映射，避免每次合成重复遍历 ``GetVoices()`` 集合
（O(N) 查找）。同 voice_name 的后续合成命中缓存直接赋值 ``voice.Voice``；
:func:`invalidate_thread_voice` 会同时清空此缓存。

纯 core 层模块，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

import threading
import time
from xml.sax.saxutils import escape as _xml_escape

try:
    import win32com.client
    import pythoncom
    _SAPI_AVAILABLE = True
except ImportError:
    _SAPI_AVAILABLE = False


# 线程本地 SpVoice 实例缓存，避免每次合成重复创建/释放 COM 对象。
_thread_local = threading.local()


class SapiError(Exception):
    """SAPI5 调用异常。"""


def init_com() -> None:
    """初始化当前线程的 COM（幂等，每线程仅实际初始化一次）。

    封装 :func:`pythoncom.CoInitialize`。通过线程本地 ``com_initialized`` 标志
    保证幂等：首次调用实际执行 ``CoInitialize`` 并置标志为 True，后续同线程
    调用为空操作。非 Windows 环境下（pywin32 不可用）抛出 :class:`SapiError`。

    COM 释放应通过 :func:`uninit_thread_com` 完成（原子清理 SpVoice +
    ``CoUninitialize``）；:func:`uninit_com` 保留为直接释放 COM 的低层接口。
    """
    if not _SAPI_AVAILABLE:
        raise SapiError("pywin32 不可用")
    if getattr(_thread_local, 'com_initialized', False):
        return
    pythoncom.CoInitialize()
    _thread_local.com_initialized = True


def uninit_com() -> None:
    """释放当前线程的 COM。

    封装 :func:`pythoncom.CoUninitialize`。应与 :func:`init_com` 配对调用。
    pywin32 不可用时本函数为空操作。
    """
    if not _SAPI_AVAILABLE:
        return
    pythoncom.CoUninitialize()


def list_voices() -> list[str]:
    """枚举系统已安装的 SAPI5 语音名称列表。

    优先复用线程本地 SpVoice 实例（适用于 Worker 线程批量任务场景）；
    若当前线程无缓存 SpVoice（如主线程），则创建临时 SpVoice 枚举后释放。

    调用前需确保当前线程已通过 :func:`init_com` 初始化 COM。

    Returns:
        语音名称列表。

    Raises:
        SapiError: pywin32 不可用或 COM 调用失败。
    """
    if not _SAPI_AVAILABLE:
        raise SapiError("pywin32 不可用")
    temp_voice = None
    voices = None
    try:
        cached = getattr(_thread_local, 'voice', None)
        if cached is not None:
            # 复用线程本地 SpVoice（Worker 线程场景）
            voices = cached.GetVoices()
        else:
            # 创建临时 SpVoice（主线程或无缓存场景）
            temp_voice = win32com.client.Dispatch("SAPI.SpVoice")
            voices = temp_voice.GetVoices()
        names: list[str] = []
        for i in range(voices.Count):
            names.append(voices.Item(i).GetDescription())
        return names
    except SapiError:
        raise
    except Exception as e:
        raise SapiError(f"枚举 SAPI5 语音失败: {e}") from e
    finally:
        # 显式释放临时 COM 对象的本地引用，使 COM 对象可尽早被 GC 回收，
        # 确保在调用方执行 CoUninitialize 前所有 COM 引用已释放。
        # 不缓存到 _thread_local（主线程不应长期持有 SpVoice）。
        temp_voice = None
        voices = None


def _get_thread_voice():
    """获取或创建线程本地 SpVoice 实例。"""
    voice = getattr(_thread_local, 'voice', None)
    if voice is None:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        _thread_local.voice = voice
    return voice


def _select_voice(voice, voice_name: str) -> None:
    """设置 voice.Voice，使用线程本地缓存避免重复 GetVoices() 遍历。

    通过 ``_thread_local.voice_token_cache`` 字典缓存"语音名称 → voice token"
    映射。命中缓存时直接赋值 ``voice.Voice = token``，避免每次合成都遍历
    ``GetVoices()`` 集合（O(N) 查找）。缓存未命中时遍历查找，找到后写入缓存。

    Args:
        voice: SpVoice 实例（已通过 :func:`_get_thread_voice` 获取）。
        voice_name: 目标语音名称；空字符串使用系统默认语音，不做任何设置。

    Raises:
        SapiError: 指定 voice_name 在 ``GetVoices()`` 集合中未找到。
    """
    if not voice_name:
        return  # 空字符串使用系统默认，无需设置
    cache = getattr(_thread_local, 'voice_token_cache', None)
    if cache is None:
        cache = {}
        _thread_local.voice_token_cache = cache
    token = cache.get(voice_name)
    if token is not None:
        voice.Voice = token
        return
    # 缓存未命中：遍历 GetVoices() 查找
    voices = voice.GetVoices()
    for i in range(voices.Count):
        t = voices.Item(i)
        if t.GetDescription() == voice_name:
            voice.Voice = t
            cache[voice_name] = t
            return
    raise SapiError(f"未找到语音: {voice_name}")


def _speak_with_cancel(voice, text: str, cancel_event: threading.Event | None) -> None:
    """执行 Speak，支持取消。无 cancel_event 或未设置时等价于同步阻塞 Speak。

    使用 SPF_ASYNC=1 启动异步合成，轮询 voice.Status.RunningState 判断完成。
    cancel_event 设置时调用 voice.Skip("Sentence", 0, 0) 跳过剩余内容并抛出
    :class:`SapiError`，使上层能感知取消并以返回码 -1 结束。

    Args:
        voice: 已配置好 Voice/Rate/Volume 与输出流的 SpVoice 实例。
        text: 待合成文本（已按需包裹 SAPI5 XML 标记）。
        cancel_event: 取消事件；None 时走同步模式（性能略优），非 None 时
            走异步轮询模式。

    Raises:
        SapiError: 轮询状态失败，或 cancel_event 被设置后终止合成。
    """
    if cancel_event is None:
        # 无取消需求，使用同步模式（性能略优）
        voice.Speak(text, 0)
        return

    # 异步模式：SPF_ASYNC = 1
    voice.Speak(text, 1)

    # 轮询完成状态，间隔 100ms（满足 200ms 取消响应目标）
    while True:
        try:
            # voice.Status.RunningState: 0=未运行(SRSEDone), 1=运行中(SRSEIsSpeaking),
            # 2=暂停(SRSEPaused)
            status = voice.Status
            running = status.RunningState
            if running == 0:  # 已完成
                return
        except Exception as e:
            raise SapiError(f"查询 SpVoice 状态失败: {e}") from e

        if cancel_event.is_set():
            # 取消：跳过剩余句子终止合成
            try:
                voice.Skip("Sentence", 0, 0)
            except Exception:
                pass  # Skip 失败不阻塞取消流程
            raise SapiError("合成已取消")

        time.sleep(0.1)


def _wrap_pitch(text: str, pitch: int) -> str:
    """将文本包裹在 SAPI5 ``<pitch absmiddle>`` XML 标记中，并对文本内容
    进行 XML 转义以防止注入。

    当 ``pitch`` 为 0 时直接返回原文本（SAPI5 以纯文本模式处理，无需转义）。
    当 ``pitch`` 非 0 时，用 ``<pitch absmiddle="{pitch}">...</pitch>`` 包裹文本，
    并通过 :func:`xml.sax.saxutils.escape` 转义文本中的 ``&``、``<``、``>``，
    防止用户文本破坏 XML 结构或注入 SAPI5 标记（如 ``<silence>``、``<emph>``）。

    Args:
        text: 待合成文本。
        pitch: 音调值，范围 -10~10；0 时不包裹。

    Returns:
        处理后的文本：``pitch==0`` 返回原文本，否则返回 XML 转义后包裹
        ``<pitch>`` 标记的字符串。
    """
    if pitch == 0:
        return text
    escaped = _xml_escape(text)
    return f'<pitch absmiddle="{pitch}">{escaped}</pitch>'


def synthesize_to_file(text: str, output_path: str, voice_name: str = "",
                        rate: int = 0, volume: int = 100, pitch: int = 0,
                        audio_format: int = 22,
                        cancel_event: threading.Event | None = None) -> None:
    """合成语音到 WAV 文件。

    Args:
        text: 待合成文本。
        output_path: 输出 WAV 文件路径。
        voice_name: SAPI5 语音名称；空字符串使用系统默认语音。
        rate: 语速，范围 -10~10，0 为正常语速。
        volume: 音量，范围 0~100，100 为最大音量。
        pitch: 音调，范围 -10~10；非 0 时通过 SAPI5 XML ``<pitch absmiddle>``
            标记实现。
        audio_format: SAPI5 SpeechAudioFormatType 枚举值，默认 22
            （SAFTPCM_16kHz_16Bit_Mono）。
        cancel_event: 取消事件；None 时使用同步阻塞 ``Speak``，非 None 时
            通过 :func:`_speak_with_cancel` 走异步轮询模式，事件设置后
            在 200ms 内终止合成并抛出 :class:`SapiError`。

    Raises:
        SapiError: pywin32 不可用、指定语音未找到、合成失败或取消。
    """
    if not _SAPI_AVAILABLE:
        raise SapiError("pywin32 不可用")
    try:
        voice = _get_thread_voice()
        _select_voice(voice, voice_name)
        voice.Rate = rate
        voice.Volume = volume
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        # 设置音频格式（采样率/位深/声道），默认 22 = SAFTPCM_16kHz_16Bit_Mono。
        stream.SetFormat(audio_format)
        # SSFMCreateForWrite = 3：以写入模式打开文件流，输出 WAV 格式。
        stream.Open(output_path, 3)
        voice.AudioOutputStream = stream
        speak_text = _wrap_pitch(text, pitch)
        _speak_with_cancel(voice, speak_text, cancel_event)
        stream.Close()
    except SapiError:
        raise
    except Exception as e:
        raise SapiError(f"合成到文件失败: {e}") from e


def synthesize_to_memory(text: str, voice_name: str = "", rate: int = 0,
                          volume: int = 100, pitch: int = 0,
                          audio_format: int = 22,
                          cancel_event: threading.Event | None = None) -> bytes:
    """合成语音到内存，返回 WAV bytes。

    Args:
        text: 待合成文本。
        voice_name: SAPI5 语音名称；空字符串使用系统默认语音。
        rate: 语速，范围 -10~10，0 为正常语速。
        volume: 音量，范围 0~100，100 为最大音量。
        pitch: 音调，范围 -10~10；非 0 时通过 SAPI5 XML ``<pitch absmiddle>``
            标记实现。
        audio_format: SAPI5 SpeechAudioFormatType 枚举值，默认 22
            （SAFTPCM_16kHz_16Bit_Mono）。
        cancel_event: 取消事件；None 时使用同步阻塞 ``Speak``，非 None 时
            通过 :func:`_speak_with_cancel` 走异步轮询模式，事件设置后
            在 200ms 内终止合成并抛出 :class:`SapiError`。

    Returns:
        WAV 格式的音频字节串。

    Raises:
        SapiError: pywin32 不可用、指定语音未找到、合成失败或取消。
    """
    if not _SAPI_AVAILABLE:
        raise SapiError("pywin32 不可用")
    try:
        voice = _get_thread_voice()
        _select_voice(voice, voice_name)
        voice.Rate = rate
        voice.Volume = volume
        stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
        # 设置音频格式（采样率/位深/声道），默认 22 = SAFTPCM_16kHz_16Bit_Mono。
        stream.SetFormat(audio_format)
        voice.AudioOutputStream = stream
        speak_text = _wrap_pitch(text, pitch)
        _speak_with_cancel(voice, speak_text, cancel_event)
        data = stream.GetData()
        return bytes(data)
    except SapiError:
        raise
    except Exception as e:
        raise SapiError(f"合成到内存失败: {e}") from e


def cleanup_thread() -> None:
    """清理线程本地 SpVoice 引用。

    释放当前线程缓存的 SpVoice 实例，使 COM 对象可被垃圾回收。应在使用
    完毕后调用；调用 :func:`uninit_com` 之前建议先调用本函数。
    """
    if hasattr(_thread_local, 'voice'):
        del _thread_local.voice


def uninit_thread_com() -> None:
    """原子释放当前线程的 COM 资源。

    依次执行 :func:`cleanup_thread`（释放线程本地 SpVoice）与
    :func:`pythoncom.CoUninitialize`（释放 COM），仅当 ``com_initialized=True``
    时执行；执行后置标志为 False。pywin32 不可用时为空操作。

    QThreadPool 复用线程跨任务，故 :class:`SapiTask` 不应在 ``run()`` 中调用
    本函数；COM 清理在线程退出时由 pythoncom atexit 钩子隐式完成。
    """
    if not _SAPI_AVAILABLE:
        return
    if not getattr(_thread_local, 'com_initialized', False):
        return
    cleanup_thread()
    pythoncom.CoUninitialize()
    _thread_local.com_initialized = False


def invalidate_thread_voice() -> None:
    """失效线程本地 SpVoice 缓存与语音令牌缓存。

    删除 ``_thread_local.voice``（若存在），使下次合成时重新创建 SpVoice 实例。
    同时清空 ``_thread_local.voice_token_cache``（若存在），使下次合成重新遍历
    ``GetVoices()`` 查找语音令牌。在 SpVoice 进入异常/损坏状态时调用（如
    ``voice.Speak()`` 抛出 COM 异常后）。
    """
    if hasattr(_thread_local, 'voice'):
        del _thread_local.voice
    if hasattr(_thread_local, 'voice_token_cache'):
        _thread_local.voice_token_cache.clear()
        del _thread_local.voice_token_cache


__all__ = ["SapiError", "init_com", "uninit_com", "uninit_thread_com",
           "invalidate_thread_voice", "list_voices", "synthesize_to_file",
           "synthesize_to_memory", "cleanup_thread"]
