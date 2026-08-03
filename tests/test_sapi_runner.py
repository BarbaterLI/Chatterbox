"""sapi_runner 模块单元测试。

使用 ``unittest.mock`` 模拟 pywin32 COM 调用（``win32com.client.Dispatch`` 与
``pythoncom.CoInitialize`` / ``CoUninitialize``），验证语音枚举、合成到文件、
合成到内存、线程本地 SpVoice 复用及 COM 生命周期管理。

测试环境可能没有 pywin32 或没有 SAPI5 引擎，因此在导入 ``sapi_runner`` 前
通过 ``sys.modules`` 注入 mock，确保 ``_SAPI_AVAILABLE = True``。
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# 在导入 sapi_runner 前 mock pywin32（仅当不可用时）。
# 若 pywin32 已安装则保留真实模块，测试中通过 patch sapi_runner.win32com
# / sapi_runner.pythoncom 替换引用。
if "win32com" not in sys.modules:
    sys.modules["win32com"] = MagicMock()
    sys.modules["win32com.client"] = MagicMock()
if "pythoncom" not in sys.modules:
    sys.modules["pythoncom"] = MagicMock()

from balcon_batch_tts.core import sapi_runner
from balcon_batch_tts.core.sapi_runner import (
    SapiError,
    _get_thread_voice,
    cleanup_thread,
    init_com,
    invalidate_thread_voice,
    list_voices,
    synthesize_to_file,
    synthesize_to_memory,
    uninit_com,
)


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_thread_local() -> None:
    """每个测试前后清理线程本地 SpVoice 缓存与 COM 初始化标志，确保测试隔离。"""
    cleanup_thread()
    # 清理 voice_token_cache（Task 14）：cleanup_thread 仅删除 voice 实例，
    # 不清除语音令牌缓存，需在此显式清理以保证测试隔离。
    if hasattr(sapi_runner._thread_local, "voice_token_cache"):
        sapi_runner._thread_local.voice_token_cache.clear()
        del sapi_runner._thread_local.voice_token_cache
    if hasattr(sapi_runner._thread_local, "com_initialized"):
        del sapi_runner._thread_local.com_initialized
    yield
    cleanup_thread()
    if hasattr(sapi_runner._thread_local, "voice_token_cache"):
        sapi_runner._thread_local.voice_token_cache.clear()
        del sapi_runner._thread_local.voice_token_cache
    if hasattr(sapi_runner._thread_local, "com_initialized"):
        del sapi_runner._thread_local.com_initialized


def _make_dispatch_side_effect(
    voice: MagicMock | None = None,
    file_stream: MagicMock | None = None,
    memory_stream: MagicMock | None = None,
):
    """创建 ``win32com.client.Dispatch`` 的 side_effect，按 ProgID 返回不同 mock。

    Args:
        voice: ``SAPI.SpVoice`` 返回的 mock。
        file_stream: ``SAPI.SpFileStream`` 返回的 mock。
        memory_stream: ``SAPI.SpMemoryStream`` 返回的 mock。
    """
    def _dispatch(prog_id: str):
        if prog_id == "SAPI.SpVoice":
            return voice or MagicMock()
        if prog_id == "SAPI.SpFileStream":
            return file_stream or MagicMock()
        if prog_id == "SAPI.SpMemoryStream":
            return memory_stream or MagicMock()
        return MagicMock()
    return _dispatch


# ---------------------------------------------------------------------------
# list_voices
# ---------------------------------------------------------------------------
class TestListVoices:
    """``list_voices`` 应枚举 SAPI5 语音名称列表。"""

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices(self, mock_win32com: MagicMock) -> None:
        """mock SpVoice.GetVoices() 返回语音名称列表。"""
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 2
        item0 = MagicMock()
        item0.GetDescription.return_value = "Microsoft Anna"
        item1 = MagicMock()
        item1.GetDescription.return_value = "Microsoft David"
        voices_mock.Item.side_effect = [item0, item1]
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.return_value = voice_mock

        result = list_voices()
        assert result == ["Microsoft Anna", "Microsoft David"]
        mock_win32com.client.Dispatch.assert_called_once_with("SAPI.SpVoice")

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices_empty(self, mock_win32com: MagicMock) -> None:
        """无语音时返回空列表。"""
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 0
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.return_value = voice_mock

        assert list_voices() == []

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices_sapi_error(self, mock_win32com: MagicMock) -> None:
        """COM 异常时应封装为 SapiError 抛出。"""
        mock_win32com.client.Dispatch.side_effect = Exception("COM error")

        with pytest.raises(SapiError):
            list_voices()

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices_single(self, mock_win32com: MagicMock) -> None:
        """单个语音应正确返回。"""
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 1
        item0 = MagicMock()
        item0.GetDescription.return_value = "Only Voice"
        voices_mock.Item.return_value = item0
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.return_value = voice_mock

        assert list_voices() == ["Only Voice"]

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices_reuses_thread_voice(
        self, mock_win32com: MagicMock
    ) -> None:
        """线程本地已有 SpVoice 时应复用，不调用 Dispatch。"""
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 2
        item0 = MagicMock()
        item0.GetDescription.return_value = "Microsoft Anna"
        item1 = MagicMock()
        item1.GetDescription.return_value = "Microsoft David"
        voices_mock.Item.side_effect = [item0, item1]
        voice_mock.GetVoices.return_value = voices_mock
        # 设置线程本地 SpVoice 缓存（模拟 Worker 线程场景）
        sapi_runner._thread_local.voice = voice_mock

        result = list_voices()

        assert result == ["Microsoft Anna", "Microsoft David"]
        # 复用线程本地 SpVoice，不应调用 Dispatch
        mock_win32com.client.Dispatch.assert_not_called()

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_list_voices_creates_temp_voice_when_no_cache(
        self, mock_win32com: MagicMock
    ) -> None:
        """线程本地无 SpVoice 缓存时应创建临时 SpVoice。"""
        # 确保线程本地无缓存（autouse fixture 已清理，显式断言）
        assert not hasattr(sapi_runner._thread_local, "voice")
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 1
        item0 = MagicMock()
        item0.GetDescription.return_value = "Only Voice"
        voices_mock.Item.return_value = item0
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.return_value = voice_mock

        result = list_voices()

        assert result == ["Only Voice"]
        mock_win32com.client.Dispatch.assert_called_once_with("SAPI.SpVoice")


# ---------------------------------------------------------------------------
# synthesize_to_file
# ---------------------------------------------------------------------------
class TestSynthesizeToFile:
    """``synthesize_to_file`` 应通过 SpFileStream 合成到 WAV 文件。"""

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_file(self, mock_win32com: MagicMock) -> None:
        """mock SpFileStream，验证调用流程。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        synthesize_to_file("hello world", "output.wav")

        # 验证 SpFileStream.Open 被调用
        file_stream_mock.Open.assert_called_once_with("output.wav", 3)
        # 验证 AudioOutputStream 被设置
        assert voice_mock.AudioOutputStream == file_stream_mock
        # 验证 Speak 被调用（pitch=0 时文本不包裹 XML）
        voice_mock.Speak.assert_called_once_with("hello world", 0)
        # 验证 stream.Close 被调用
        file_stream_mock.Close.assert_called_once()
        # 验证 Rate / Volume 被设置
        assert voice_mock.Rate == 0
        assert voice_mock.Volume == 100

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_file_with_voice_name(
        self, mock_win32com: MagicMock
    ) -> None:
        """指定 voice_name 时应匹配并设置语音。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 2
        item0 = MagicMock()
        item0.GetDescription.return_value = "Voice A"
        item1 = MagicMock()
        item1.GetDescription.return_value = "Voice B"
        voices_mock.Item.side_effect = [item0, item1]
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        synthesize_to_file("hello", "out.wav", voice_name="Voice B")

        # 验证语音被设置为 item1（Voice B）
        assert voice_mock.Voice == item1
        voice_mock.Speak.assert_called_once_with("hello", 0)

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_file_voice_not_found(
        self, mock_win32com: MagicMock
    ) -> None:
        """未找到指定语音时应抛出 SapiError。"""
        voice_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 1
        item0 = MagicMock()
        item0.GetDescription.return_value = "Other Voice"
        voices_mock.Item.return_value = item0
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock
        )

        with pytest.raises(SapiError, match="未找到语音"):
            synthesize_to_file("hello", "out.wav", voice_name="Missing Voice")

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_with_pitch(self, mock_win32com: MagicMock) -> None:
        """pitch != 0 时文本应包裹 XML ``<pitch absmiddle="...">`` 标记。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        synthesize_to_file("hello", "out.wav", pitch=5)

        expected = '<pitch absmiddle="5">hello</pitch>'
        voice_mock.Speak.assert_called_once_with(expected, 0)

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_with_negative_pitch(
        self, mock_win32com: MagicMock
    ) -> None:
        """负数 pitch 也应正确包裹 XML 标记。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        synthesize_to_file("hello", "out.wav", pitch=-3)

        expected = '<pitch absmiddle="-3">hello</pitch>'
        voice_mock.Speak.assert_called_once_with(expected, 0)

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_file_com_error(
        self, mock_win32com: MagicMock
    ) -> None:
        """COM 调用异常时应封装为 SapiError。"""
        mock_win32com.client.Dispatch.side_effect = Exception("COM failed")

        with pytest.raises(SapiError):
            synthesize_to_file("hello", "out.wav")


# ---------------------------------------------------------------------------
# synthesize_to_memory
# ---------------------------------------------------------------------------
class TestSynthesizeToMemory:
    """``synthesize_to_memory`` 应通过 SpMemoryStream 合成并返回 bytes。"""

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_memory(self, mock_win32com: MagicMock) -> None:
        """mock SpMemoryStream，验证返回 bytes。"""
        voice_mock = MagicMock()
        memory_stream_mock = MagicMock()
        memory_stream_mock.GetData.return_value = b"wav audio data"
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, memory_stream=memory_stream_mock
        )

        result = synthesize_to_memory("hello")

        assert result == b"wav audio data"
        # 验证 SetFormat 被调用（SAFTPCM_16kHz_16Bit_Mono = 22）
        memory_stream_mock.SetFormat.assert_called_once_with(22)
        # 验证 AudioOutputStream 被设置
        assert voice_mock.AudioOutputStream == memory_stream_mock
        # 验证 Speak 被调用
        voice_mock.Speak.assert_called_once_with("hello", 0)

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_memory_returns_bytes(
        self, mock_win32com: MagicMock
    ) -> None:
        """返回值必须为 bytes 类型。"""
        voice_mock = MagicMock()
        memory_stream_mock = MagicMock()
        memory_stream_mock.GetData.return_value = [1, 2, 3, 4]
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, memory_stream=memory_stream_mock
        )

        result = synthesize_to_memory("hello")
        assert isinstance(result, bytes)
        assert result == b"\x01\x02\x03\x04"

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_memory_with_pitch(
        self, mock_win32com: MagicMock
    ) -> None:
        """pitch != 0 时文本应包裹 XML 标记。"""
        voice_mock = MagicMock()
        memory_stream_mock = MagicMock()
        memory_stream_mock.GetData.return_value = b"data"
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, memory_stream=memory_stream_mock
        )

        synthesize_to_memory("hello", pitch=-5)

        expected = '<pitch absmiddle="-5">hello</pitch>'
        voice_mock.Speak.assert_called_once_with(expected, 0)

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_synthesize_to_memory_com_error(
        self, mock_win32com: MagicMock
    ) -> None:
        """COM 调用异常时应封装为 SapiError。"""
        mock_win32com.client.Dispatch.side_effect = Exception("COM failed")

        with pytest.raises(SapiError):
            synthesize_to_memory("hello")


# ---------------------------------------------------------------------------
# 线程本地 SpVoice 复用
# ---------------------------------------------------------------------------
class TestThreadLocalVoiceReuse:
    """``_get_thread_voice`` 应在同线程内复用 SpVoice 实例。"""

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_thread_local_voice_reuse(self, mock_win32com: MagicMock) -> None:
        """同线程调用 ``_get_thread_voice()`` 应返回同一实例。"""
        voice_mock = MagicMock()
        mock_win32com.client.Dispatch.return_value = voice_mock

        v1 = _get_thread_voice()
        v2 = _get_thread_voice()

        assert v1 is v2
        assert v1 is voice_mock
        # Dispatch 应仅被调用一次（第二次从缓存返回）
        mock_win32com.client.Dispatch.assert_called_once_with("SAPI.SpVoice")

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_cleanup_thread_clears_cache(self, mock_win32com: MagicMock) -> None:
        """``cleanup_thread`` 后再次获取应创建新实例。"""
        voice1 = MagicMock()
        mock_win32com.client.Dispatch.return_value = voice1

        v1 = _get_thread_voice()
        assert v1 is voice1

        cleanup_thread()

        voice2 = MagicMock()
        mock_win32com.client.Dispatch.return_value = voice2
        v2 = _get_thread_voice()
        assert v2 is voice2
        assert v1 is not v2


# ---------------------------------------------------------------------------
# COM 生命周期：init_com / uninit_com
# ---------------------------------------------------------------------------
class TestComLifecycle:
    """``init_com`` / ``uninit_com`` 应封装 pythoncom 调用。"""

    @patch("balcon_batch_tts.core.sapi_runner.pythoncom")
    def test_init_com(self, mock_pythoncom: MagicMock) -> None:
        """``init_com`` 应调用 ``pythoncom.CoInitialize``。"""
        init_com()
        mock_pythoncom.CoInitialize.assert_called_once()

    @patch("balcon_batch_tts.core.sapi_runner.pythoncom")
    def test_uninit_com(self, mock_pythoncom: MagicMock) -> None:
        """``uninit_com`` 应调用 ``pythoncom.CoUninitialize``。"""
        uninit_com()
        mock_pythoncom.CoUninitialize.assert_called_once()

    @patch("balcon_batch_tts.core.sapi_runner.pythoncom")
    def test_init_uninit_pair(self, mock_pythoncom: MagicMock) -> None:
        """``init_com`` 与 ``uninit_com`` 应可成对调用。"""
        init_com()
        uninit_com()
        mock_pythoncom.CoInitialize.assert_called_once()
        mock_pythoncom.CoUninitialize.assert_called_once()


# ---------------------------------------------------------------------------
# SpVoice 语音令牌缓存（Task 14）
# ---------------------------------------------------------------------------
class TestVoiceTokenCache:
    """``_select_voice`` 应使用线程本地缓存避免重复 ``GetVoices()`` 遍历。"""

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_voice_token_cache_hit(self, mock_win32com: MagicMock) -> None:
        """同 voice_name 多次合成时 ``GetVoices()`` 仅调用 1 次（缓存命中）。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 2
        item0 = MagicMock()
        item0.GetDescription.return_value = "Voice A"
        item1 = MagicMock()
        item1.GetDescription.return_value = "Voice B"
        # 使用 lambda 避免列表 side_effect 在多次调用后耗尽。
        voices_mock.Item.side_effect = lambda idx: item0 if idx == 0 else item1
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        # 第一次合成：缓存未命中，遍历 GetVoices() 找到 Voice B。
        synthesize_to_file("hello", "out1.wav", voice_name="Voice B")
        # 第二次合成：缓存命中，不应再调用 GetVoices()。
        synthesize_to_file("world", "out2.wav", voice_name="Voice B")

        # 关键断言：GetVoices() 仅被调用 1 次（第二次走缓存）。
        assert voice_mock.GetVoices.call_count == 1
        # 第二次合成的 Voice 仍应为 item1（Voice B）。
        assert voice_mock.Voice == item1
        # 两次 Speak 都应被调用。
        assert voice_mock.Speak.call_count == 2

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_voice_token_cache_miss_on_different_voice_name(
        self, mock_win32com: MagicMock
    ) -> None:
        """不同 voice_name 应各自触发一次 ``GetVoices()`` 遍历（缓存未命中）。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 2
        item0 = MagicMock()
        item0.GetDescription.return_value = "Voice A"
        item1 = MagicMock()
        item1.GetDescription.return_value = "Voice B"
        voices_mock.Item.side_effect = lambda idx: item0 if idx == 0 else item1
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        # 第一次合成 voice_name="Voice A"：GetVoices() 调用 1 次，缓存写入。
        synthesize_to_file("hello", "out1.wav", voice_name="Voice A")
        assert voice_mock.Voice == item0
        # 第二次合成 voice_name="Voice B"：缓存未命中，GetVoices() 再调用 1 次。
        synthesize_to_file("world", "out2.wav", voice_name="Voice B")
        assert voice_mock.Voice == item1

        # 关键断言：GetVoices() 被调用 2 次（每个唯一 voice_name 各 1 次）。
        assert voice_mock.GetVoices.call_count == 2

    @patch("balcon_batch_tts.core.sapi_runner.win32com")
    def test_invalidate_clears_voice_token_cache(
        self, mock_win32com: MagicMock
    ) -> None:
        """``invalidate_thread_voice`` 后再次合成应重新调用 ``GetVoices()``。"""
        voice_mock = MagicMock()
        file_stream_mock = MagicMock()
        voices_mock = MagicMock()
        voices_mock.Count = 1
        item0 = MagicMock()
        item0.GetDescription.return_value = "Voice A"
        voices_mock.Item.side_effect = lambda idx: item0
        voice_mock.GetVoices.return_value = voices_mock
        mock_win32com.client.Dispatch.side_effect = _make_dispatch_side_effect(
            voice=voice_mock, file_stream=file_stream_mock
        )

        # 第一次合成：GetVoices() 调用 1 次，缓存写入。
        synthesize_to_file("hello", "out1.wav", voice_name="Voice A")
        assert voice_mock.GetVoices.call_count == 1

        # 失效缓存：清除 voice 实例与 voice_token_cache。
        invalidate_thread_voice()

        # 第二次合成：缓存已被清除，应重新调用 GetVoices()。
        synthesize_to_file("world", "out2.wav", voice_name="Voice A")

        # 关键断言：GetVoices() 共被调用 2 次（失效后重新遍历）。
        assert voice_mock.GetVoices.call_count == 2
        assert voice_mock.Voice == item0
