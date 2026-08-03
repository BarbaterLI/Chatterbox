"""audio_encoder 模块单元测试。

验证 :class:`AudioFormat` 枚举与 ffmpeg 转码引擎行为，包括：
- AudioFormat 枚举属性（extension/encoder/is_wav/needs_ffmpeg）
- AudioFormat.from_extension 扩展名推断
- build_encode_args 命令行参数构建
- build_encode_preview 命令行预览
- find_ffmpeg / validate_ffmpeg 路径查找与校验
- encode_audio 转码执行（通过 mock subprocess）

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import io
import os
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from balcon_batch_tts.core.audio_encoder import (
    FFMPEG_ENV_VAR,
    AudioFormat,
    EncoderDetector,
    EncoderError,
    EncoderNotFoundError,
    EncoderTimeoutError,
    _ENCODER_PRIORITY,
    _ffmpeg_path_cache,
    build_encode_args,
    build_encode_preview,
    build_encode_stream_args,
    clear_ffmpeg_cache,
    encode_audio,
    encode_audio_from_stream,
    find_ffmpeg,
    terminate_ffmpeg,
    validate_ffmpeg,
)


# ---------------------------------------------------------------------------
# FakeProcess: 模拟 subprocess.Popen 子进程
# ---------------------------------------------------------------------------
class _FakeProcess:
    """模拟 subprocess.Popen 子进程，支持管道读取和轮询。

    使用 :class:`io.StringIO` 模拟 stdout/stderr 管道，读取线程可从中
    读取内容并在 EOF 时退出。``never_exit=True`` 时进程不会自然退出，
    ``wait()`` 始终抛出 :class:`subprocess.TimeoutExpired`，需通过
    ``terminate()`` / ``kill()`` 终止。
    """

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        never_exit: bool = False,
    ) -> None:
        self.returncode: int | None = None if never_exit else returncode
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.pid = 12345
        self._terminated = False
        self._killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout or 0)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self._killed = True
        self.returncode = -9

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return (self.stdout.getvalue(), self.stderr.getvalue())


# ---------------------------------------------------------------------------
# AudioFormat 枚举属性
# ---------------------------------------------------------------------------
class TestAudioFormatProperties:
    """``AudioFormat`` 枚举属性契约。"""

    def test_wav_extension(self) -> None:
        assert AudioFormat.WAV.extension == "wav"

    def test_mp3_extension(self) -> None:
        assert AudioFormat.MP3.extension == "mp3"

    def test_ogg_extension(self) -> None:
        assert AudioFormat.OGG.extension == "ogg"

    def test_aac_extension(self) -> None:
        assert AudioFormat.AAC.extension == "aac"

    def test_flac_extension(self) -> None:
        assert AudioFormat.FLAC.extension == "flac"

    def test_wma_extension(self) -> None:
        assert AudioFormat.WMA.extension == "wma"

    def test_wav_is_wav(self) -> None:
        assert AudioFormat.WAV.is_wav is True

    def test_mp3_is_not_wav(self) -> None:
        assert AudioFormat.MP3.is_wav is False

    def test_wav_does_not_need_ffmpeg(self) -> None:
        assert AudioFormat.WAV.needs_ffmpeg is False

    def test_mp3_needs_ffmpeg(self) -> None:
        assert AudioFormat.MP3.needs_ffmpeg is True

    def test_all_non_wav_formats_need_ffmpeg(self) -> None:
        for fmt in AudioFormat:
            if fmt is AudioFormat.WAV:
                continue
            assert fmt.needs_ffmpeg is True

    def test_wav_encoder(self) -> None:
        assert AudioFormat.WAV.encoder == "pcm_s16le"

    def test_mp3_encoder(self) -> None:
        assert AudioFormat.MP3.encoder == "libmp3lame"

    def test_ogg_encoder(self) -> None:
        assert AudioFormat.OGG.encoder == "libvorbis"

    def test_aac_encoder(self) -> None:
        assert AudioFormat.AAC.encoder == "aac"

    def test_flac_encoder(self) -> None:
        assert AudioFormat.FLAC.encoder == "flac"

    def test_wma_encoder(self) -> None:
        assert AudioFormat.WMA.encoder == "wmav2"


# ---------------------------------------------------------------------------
# 音质保障：320kbps 等效参数
# ---------------------------------------------------------------------------
class TestAudioQualityAssurance:
    """音质保障：有损格式不低于 320kbps。"""

    def test_wav_is_lossless(self) -> None:
        assert AudioFormat.WAV.is_lossless is True

    def test_flac_is_lossless(self) -> None:
        assert AudioFormat.FLAC.is_lossless is True

    def test_mp3_is_lossy(self) -> None:
        assert AudioFormat.MP3.is_lossy is True

    def test_ogg_is_lossy(self) -> None:
        assert AudioFormat.OGG.is_lossy is True

    def test_aac_is_lossy(self) -> None:
        assert AudioFormat.AAC.is_lossy is True

    def test_wma_is_lossy(self) -> None:
        assert AudioFormat.WMA.is_lossy is True

    def test_wav_default_extra_args_empty(self) -> None:
        """WAV 无损，无需比特率参数。"""
        assert AudioFormat.WAV.default_extra_args == []

    def test_flac_default_extra_args_empty(self) -> None:
        """FLAC 无损，无需比特率参数。"""
        assert AudioFormat.FLAC.default_extra_args == []

    def test_mp3_default_extra_args_320k(self) -> None:
        """MP3 默认 320kbps。"""
        args = AudioFormat.MP3.default_extra_args
        assert "-b:a" in args
        idx = args.index("-b:a")
        assert args[idx + 1] == "320k"

    def test_aac_default_extra_args_320k(self) -> None:
        """AAC 默认 320kbps。"""
        args = AudioFormat.AAC.default_extra_args
        assert "-b:a" in args
        idx = args.index("-b:a")
        assert args[idx + 1] == "320k"

    def test_wma_default_extra_args_320k(self) -> None:
        """WMA 默认 320kbps。"""
        args = AudioFormat.WMA.default_extra_args
        assert "-b:a" in args
        idx = args.index("-b:a")
        assert args[idx + 1] == "320k"

    def test_ogg_default_extra_args_quality_10(self) -> None:
        """OGG 默认质量 10（约 500kbps，远超 320kbps）。"""
        args = AudioFormat.OGG.default_extra_args
        assert "-q:a" in args
        idx = args.index("-q:a")
        assert args[idx + 1] == "10"


class TestBuildEncodeArgsQuality:
    """``build_encode_args`` 在默认情况下应用 320kbps。"""

    def test_mp3_default_args_include_320k(self) -> None:
        """MP3 默认参数应包含 -b:a 320k。"""
        args = build_encode_args("src.wav", "dst.mp3", AudioFormat.MP3)
        assert "-b:a" in args
        idx = args.index("-b:a")
        assert args[idx + 1] == "320k"

    def test_aac_default_args_include_320k(self) -> None:
        """AAC 默认参数应包含 -b:a 320k。"""
        args = build_encode_args("src.wav", "dst.aac", AudioFormat.AAC)
        assert "-b:a" in args
        idx = args.index("-b:a")
        assert args[idx + 1] == "320k"

    def test_ogg_default_args_include_quality_10(self) -> None:
        """OGG 默认参数应包含 -q:a 10。"""
        args = build_encode_args("src.wav", "dst.ogg", AudioFormat.OGG)
        assert "-q:a" in args
        idx = args.index("-q:a")
        assert args[idx + 1] == "10"

    def test_wav_default_args_no_bitrate(self) -> None:
        """WAV 默认参数不应包含比特率。"""
        args = build_encode_args("src.wav", "dst.wav", AudioFormat.WAV)
        assert "-b:a" not in args
        assert "-q:a" not in args

    def test_flac_default_args_no_bitrate(self) -> None:
        """FLAC 默认参数不应包含比特率。"""
        args = build_encode_args("src.wav", "dst.flac", AudioFormat.FLAC)
        assert "-b:a" not in args
        assert "-q:a" not in args

    def test_explicit_empty_extra_args_overrides_default(self) -> None:
        """显式传入空列表 [] 应覆盖默认 320kbps（用户自负音质）。"""
        args = build_encode_args(
            "src.wav", "dst.mp3", AudioFormat.MP3, extra_args=[]
        )
        # 不应包含 -b:a
        assert "-b:a" not in args

    def test_explicit_low_bitrate_overrides_default(self) -> None:
        """显式传入低比特率应覆盖默认（用户自负音质）。"""
        args = build_encode_args(
            "src.wav", "dst.mp3", AudioFormat.MP3,
            extra_args=["-b:a", "128k"],
        )
        idx = args.index("-b:a")
        assert args[idx + 1] == "128k"


# ---------------------------------------------------------------------------
# AudioFormat.from_extension
# ---------------------------------------------------------------------------
class TestAudioFormatFromExtension:
    """``AudioFormat.from_extension`` 扩展名推断。"""

    def test_from_extension_wav(self) -> None:
        assert AudioFormat.from_extension(".wav") is AudioFormat.WAV

    def test_from_extension_mp3(self) -> None:
        assert AudioFormat.from_extension(".mp3") is AudioFormat.MP3

    def test_from_extension_ogg(self) -> None:
        assert AudioFormat.from_extension(".ogg") is AudioFormat.OGG

    def test_from_extension_without_dot(self) -> None:
        assert AudioFormat.from_extension("mp3") is AudioFormat.MP3

    def test_from_extension_uppercase(self) -> None:
        assert AudioFormat.from_extension(".MP3") is AudioFormat.MP3

    def test_from_extension_mixed_case(self) -> None:
        assert AudioFormat.from_extension("Mp3") is AudioFormat.MP3

    def test_from_extension_unknown_returns_wav(self) -> None:
        assert AudioFormat.from_extension(".unknown") is AudioFormat.WAV

    def test_from_extension_empty_returns_wav(self) -> None:
        assert AudioFormat.from_extension("") is AudioFormat.WAV


# ---------------------------------------------------------------------------
# build_encode_args
# ---------------------------------------------------------------------------
class TestBuildEncodeArgs:
    """``build_encode_args`` 命令行参数构建。"""

    def test_basic_args_mp3(self) -> None:
        args = build_encode_args("src.wav", "dst.mp3", AudioFormat.MP3)
        # 应包含 -y -i src.wav -c:a libmp3lame dst.mp3
        assert args[0] == "-y"
        assert args[1] == "-i"
        assert args[2] == "src.wav"
        assert "-c:a" in args
        idx = args.index("-c:a")
        assert args[idx + 1] == "libmp3lame"
        assert args[-1] == "dst.mp3"

    def test_basic_args_wav(self) -> None:
        args = build_encode_args("src.wav", "dst.wav", AudioFormat.WAV)
        assert args[0] == "-y"
        assert "-c:a" in args
        idx = args.index("-c:a")
        assert args[idx + 1] == "pcm_s16le"

    def test_args_with_extra_args(self) -> None:
        args = build_encode_args(
            "src.wav", "dst.mp3", AudioFormat.MP3,
            extra_args=["-b:a", "192k"],
        )
        # extra_args 应在 -c:a 之前
        assert "-b:a" in args
        assert "192k" in args
        idx_extra = args.index("-b:a")
        idx_codec = args.index("-c:a")
        assert idx_extra < idx_codec

    def test_args_without_extra_args(self) -> None:
        """不指定 extra_args 时使用默认 320kbps（MP3 是有损格式）。"""
        args = build_encode_args("src.wav", "dst.mp3", AudioFormat.MP3)
        # 默认应包含 -b:a 320k（音质保障）
        assert "-b:a" in args
        assert "320k" in args

    def test_args_order(self) -> None:
        """参数顺序：-y -i src [extra...] -c:a encoder -- dst。

        ``--`` 分隔符防止 dst_path 以 ``-`` 开头时被 ffmpeg 误解析为选项
        （参数注入防护）。
        """
        args = build_encode_args(
            "src.wav", "dst.mp3", AudioFormat.MP3,
            extra_args=["-b:a", "192k"],
        )
        assert args == [
            "-y", "-i", "src.wav",
            "-b:a", "192k",
            "-c:a", "libmp3lame",
            "--",
            "dst.mp3",
        ]

    def test_default_args_mp3_include_320k(self) -> None:
        """默认情况（不指定 extra_args）应包含 320kbps。"""
        args = build_encode_args("src.wav", "dst.mp3", AudioFormat.MP3)
        assert "-b:a" in args
        assert "320k" in args


# ---------------------------------------------------------------------------
# build_encode_preview
# ---------------------------------------------------------------------------
class TestBuildEncodePreview:
    """``build_encode_preview`` 命令行预览。"""

    def test_preview_simple(self) -> None:
        args = ["-y", "-i", "src.wav", "-c:a", "libmp3lame", "dst.mp3"]
        preview = build_encode_preview("/usr/bin/ffmpeg", args)
        assert "/usr/bin/ffmpeg" in preview
        assert "src.wav" in preview
        assert "dst.mp3" in preview

    def test_preview_path_with_space_quoted(self) -> None:
        args = ["-y", "-i", "src.wav", "dst.mp3"]
        preview = build_encode_preview("/path with space/ffmpeg", args)
        assert '"/path with space/ffmpeg"' in preview

    def test_preview_arg_with_space_quoted(self) -> None:
        args = ["-y", "-i", "/path with space/src.wav", "dst.mp3"]
        preview = build_encode_preview("/usr/bin/ffmpeg", args)
        assert '"/path with space/src.wav"' in preview


# ---------------------------------------------------------------------------
# find_ffmpeg / validate_ffmpeg
# ---------------------------------------------------------------------------
class TestFindFfmpeg:
    """``find_ffmpeg`` 路径查找。"""

    def test_find_ffmpeg_returns_none_when_not_found(
        self, monkeypatch
    ) -> None:
        """环境变量、PATH、Windows 常见路径都未找到时返回 None。"""
        monkeypatch.delenv(FFMPEG_ENV_VAR, raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        monkeypatch.setattr("os.path.isfile", lambda _: False)
        result = find_ffmpeg()
        assert result is None

    def test_find_ffmpeg_from_env_var(self, monkeypatch, tmp_path) -> None:
        """环境变量指定的路径优先。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")
        monkeypatch.setenv(FFMPEG_ENV_VAR, str(fake_ffmpeg))
        monkeypatch.setattr("shutil.which", lambda _: None)

        result = find_ffmpeg()
        assert result is not None
        assert os.path.normpath(result) == os.path.normpath(str(fake_ffmpeg))

    def test_find_ffmpeg_env_var_invalid_falls_back(
        self, monkeypatch, tmp_path
    ) -> None:
        """环境变量指向不存在的文件时回退到 PATH 查找。"""
        monkeypatch.setenv(FFMPEG_ENV_VAR, "/nonexistent/ffmpeg.exe")
        path_ffmpeg = tmp_path / "ffmpeg"
        path_ffmpeg.write_text("fake")
        monkeypatch.setattr("shutil.which", lambda _: str(path_ffmpeg))

        result = find_ffmpeg()
        assert result is not None
        assert os.path.normpath(result) == os.path.normpath(str(path_ffmpeg))

    def test_find_ffmpeg_from_path(self, monkeypatch, tmp_path) -> None:
        """PATH 中找到 ffmpeg。"""
        monkeypatch.delenv(FFMPEG_ENV_VAR, raising=False)
        path_ffmpeg = tmp_path / "ffmpeg"
        path_ffmpeg.write_text("fake")
        monkeypatch.setattr("shutil.which", lambda _: str(path_ffmpeg))

        result = find_ffmpeg()
        assert result is not None
        assert os.path.normpath(result) == os.path.normpath(str(path_ffmpeg))


class TestValidateFfmpeg:
    """``validate_ffmpeg`` 路径校验。"""

    def test_validate_valid_path(self, tmp_path) -> None:
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")
        result = validate_ffmpeg(str(fake_ffmpeg))
        assert os.path.normpath(result) == os.path.normpath(str(fake_ffmpeg))

    def test_validate_none_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.find_ffmpeg",
            lambda: None,
        )
        with pytest.raises(EncoderNotFoundError):
            validate_ffmpeg(None)

    def test_validate_empty_string_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.find_ffmpeg",
            lambda: None,
        )
        with pytest.raises(EncoderNotFoundError):
            validate_ffmpeg("")

    def test_validate_invalid_path_raises(self) -> None:
        with pytest.raises(EncoderNotFoundError):
            validate_ffmpeg("/nonexistent/ffmpeg.exe")


# ---------------------------------------------------------------------------
# encode_audio
# ---------------------------------------------------------------------------
class TestEncodeAudio:
    """``encode_audio`` 转码执行（通过 mock subprocess）。"""

    def test_encode_audio_success(self, monkeypatch, tmp_path) -> None:
        """转码成功返回 0。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        mock_process = _FakeProcess(
            returncode=0, stdout="stdout", stderr="stderr"
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        rc, stdout, stderr = encode_audio(
            str(src), str(dst), AudioFormat.MP3, ffmpeg_path=str(fake_ffmpeg)
        )
        assert rc == 0
        assert stdout == "stdout"
        assert stderr == "stderr"

    def test_encode_audio_failure_returns_nonzero(
        self, monkeypatch, tmp_path
    ) -> None:
        """ffmpeg 返回非零码时不抛异常，返回该码。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        mock_process = _FakeProcess(
            returncode=1, stdout="", stderr="error output"
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        rc, stdout, stderr = encode_audio(
            str(src), str(dst), AudioFormat.MP3, ffmpeg_path=str(fake_ffmpeg)
        )
        assert rc == 1
        assert stderr == "error output"

    def test_encode_audio_cancel_raises(self, monkeypatch, tmp_path) -> None:
        """取消事件触发时抛出 EncoderError 并终止进程。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        cancel_event = threading.Event()
        cancel_event.set()

        mock_process = _FakeProcess(never_exit=True)

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        with pytest.raises(EncoderError, match="已取消"):
            encode_audio(
                str(src), str(dst), AudioFormat.MP3,
                ffmpeg_path=str(fake_ffmpeg),
                cancel_event=cancel_event,
            )
        # 验证进程被 terminate
        assert mock_process._terminated

    def test_encode_audio_timeout_raises(self, monkeypatch, tmp_path) -> None:
        """超时触发 EncoderTimeoutError。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        mock_process = _FakeProcess(never_exit=True)

        # mock time.monotonic 让超时立即触发
        time_values = iter([0.0, 100.0])
        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.time.monotonic",
            lambda: next(time_values),
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        with pytest.raises(EncoderTimeoutError):
            encode_audio(
                str(src), str(dst), AudioFormat.MP3,
                ffmpeg_path=str(fake_ffmpeg),
                timeout=10.0,
            )

    def test_encode_audio_ffmpeg_not_found(self, tmp_path) -> None:
        """ffmpeg 未找到时抛 EncoderNotFoundError。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"

        with pytest.raises(EncoderNotFoundError):
            encode_audio(
                str(src), str(dst), AudioFormat.MP3,
                ffmpeg_path="/nonexistent/ffmpeg.exe",
            )

    def test_encode_audio_large_stderr_no_deadlock(
        self, monkeypatch, tmp_path
    ) -> None:
        """子进程产生大量 stderr（>64KB）时不应死锁。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        large_stderr = "x" * (64 * 1024 + 100)  # 超过 64KB 管道缓冲区
        mock_process = _FakeProcess(
            returncode=0, stdout="", stderr=large_stderr
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        rc, stdout, stderr = encode_audio(
            str(src), str(dst), AudioFormat.MP3, ffmpeg_path=str(fake_ffmpeg)
        )
        assert rc == 0
        assert len(stderr) == len(large_stderr)
        assert stderr == large_stderr

    def test_encode_audio_stdout_stderr_accumulation(
        self, monkeypatch, tmp_path
    ) -> None:
        """验证返回的 stdout/stderr 内容完整。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        stdout_content = "frame= 100 fps=30\nframe= 200 fps=30\n"
        stderr_content = "Encoding...\nDone.\n"
        mock_process = _FakeProcess(
            returncode=0,
            stdout=stdout_content,
            stderr=stderr_content,
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        rc, stdout, stderr = encode_audio(
            str(src), str(dst), AudioFormat.MP3, ffmpeg_path=str(fake_ffmpeg)
        )
        assert rc == 0
        assert stdout == stdout_content
        assert stderr == stderr_content

    def test_encode_audio_large_stdout_no_deadlock(
        self, monkeypatch, tmp_path
    ) -> None:
        """子进程产生大量 stdout（>64KB）时不应死锁。"""
        src = tmp_path / "src.wav"
        src.write_text("fake wav")
        dst = tmp_path / "dst.mp3"
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        large_stdout = "y" * (64 * 1024 + 200)
        mock_process = _FakeProcess(
            returncode=0, stdout=large_stdout, stderr=""
        )

        monkeypatch.setattr(
            "balcon_batch_tts.core.audio_encoder.subprocess.Popen",
            lambda *args, **kwargs: mock_process,
        )

        rc, stdout, stderr = encode_audio(
            str(src), str(dst), AudioFormat.MP3, ffmpeg_path=str(fake_ffmpeg)
        )
        assert rc == 0
        assert stdout == large_stdout
        assert stderr == ""


# ---------------------------------------------------------------------------
# terminate_ffmpeg
# ---------------------------------------------------------------------------
class TestTerminateFfmpeg:
    """``terminate_ffmpeg`` 安全终止子进程。"""

    def test_terminate_calls_terminate_then_wait(self) -> None:
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        terminate_ffmpeg(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()

    def test_terminate_upgrades_to_kill_on_timeout(self) -> None:
        mock_process = MagicMock()
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="ffmpeg", timeout=2),
            0,
        ]
        terminate_ffmpeg(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_terminate_swallows_exceptions(self) -> None:
        """所有异常都应被捕获，不向调用方抛出。"""
        mock_process = MagicMock()
        mock_process.terminate.side_effect = OSError("terminated")
        mock_process.wait.side_effect = OSError("no process")
        # 不应抛出异常
        terminate_ffmpeg(mock_process)


# ---------------------------------------------------------------------------
# Task 9: 编码器优先级选择 (best_encoder)
# ---------------------------------------------------------------------------
class TestBestEncoder:
    """``AudioFormat.best_encoder()`` 按优先级选择编码器。"""

    def test_returns_default_when_none(self) -> None:
        """``available_encoders=None`` 时返回默认编码器。"""
        for fmt in AudioFormat:
            assert fmt.best_encoder(None) == fmt.encoder

    def test_returns_default_when_empty_set(self) -> None:
        """空集合时回退到默认编码器。"""
        for fmt in AudioFormat:
            assert fmt.best_encoder(set()) == fmt.encoder

    def test_aac_prefers_libfdk_aac(self) -> None:
        """AAC 优先使用 libfdk_aac（高质量）。"""
        available = {"aac", "libfdk_aac", "libmp3lame"}
        assert AudioFormat.AAC.best_encoder(available) == "libfdk_aac"

    def test_aac_falls_back_to_builtin(self) -> None:
        """无 libfdk_aac 时回退到内置 aac。"""
        available = {"aac", "libmp3lame"}
        assert AudioFormat.AAC.best_encoder(available) == "aac"

    def test_mp3_prefers_libmp3lame(self) -> None:
        """MP3 优先使用 libmp3lame。"""
        available = {"libmp3lame", "mp3_mf", "mp3float"}
        assert AudioFormat.MP3.best_encoder(available) == "libmp3lame"

    def test_mp3_falls_back_to_mp3_mf(self) -> None:
        """无 libmp3lame 时使用 mp3_mf。"""
        available = {"mp3_mf", "mp3float"}
        assert AudioFormat.MP3.best_encoder(available) == "mp3_mf"

    def test_ogg_prefers_libvorbis(self) -> None:
        """OGG 优先使用 libvorbis。"""
        available = {"libvorbis", "vorbis"}
        assert AudioFormat.OGG.best_encoder(available) == "libvorbis"

    def test_no_match_returns_default(self) -> None:
        """无任何优先编码器可用时回退到默认。"""
        # 提供完全不相关的编码器
        available = {"libx264", "libvpx"}
        for fmt in AudioFormat:
            assert fmt.best_encoder(available) == fmt.encoder

    def test_wav_always_returns_pcm_s16le(self) -> None:
        """WAV 格式始终使用 pcm_s16le。"""
        available = {"pcm_s16le", "pcm_s24le"}
        assert AudioFormat.WAV.best_encoder(available) == "pcm_s16le"

    def test_priority_dict_covers_all_formats(self) -> None:
        """``_ENCODER_PRIORITY`` 应覆盖所有格式。"""
        for fmt in AudioFormat:
            assert fmt.value in _ENCODER_PRIORITY


# ---------------------------------------------------------------------------
# Task 9: 编码器检测 (EncoderDetector)
# ---------------------------------------------------------------------------
class TestEncoderDetector:
    """``EncoderDetector`` 解析 ffmpeg -encoders 输出。"""

    def teardown_method(self) -> None:
        """每个测试后清除缓存，避免跨测试污染。"""
        EncoderDetector.clear_cache()

    def test_detect_parses_encoders_output(self) -> None:
        """应正确解析 ffmpeg -encoders 输出文本。"""
        fake_output = (
            "Encoders:\n"
            " V..... libx264              H.264\n"
            " A..... libmp3lame           MP3\n"
            " A..... aac                  AAC\n"
            " A..... libfdk_aac           Fraunhofer FDK AAC\n"
            " S..... srt                  SubRip\n"
        )
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            encoders = EncoderDetector.detect("/fake/ffmpeg")
            assert "libx264" in encoders
            assert "libmp3lame" in encoders
            assert "aac" in encoders
            assert "libfdk_aac" in encoders
            assert "srt" in encoders

    def test_detect_caches_results(self) -> None:
        """相同路径第二次调用应使用缓存，不重复执行 subprocess。"""
        mock_result = MagicMock()
        mock_result.stdout = "A..... aac  AAC\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            EncoderDetector.detect("/fake/ffmpeg")
            assert mock_run.call_count == 1
            # 第二次调用应命中缓存
            EncoderDetector.detect("/fake/ffmpeg")
            assert mock_run.call_count == 1

    def test_detect_returns_empty_on_failure(self) -> None:
        """subprocess 失败时返回空集合（不抛异常）。"""
        with patch("subprocess.run", side_effect=OSError("not found")):
            encoders = EncoderDetector.detect("/fake/ffmpeg")
            assert encoders == set()

    def test_detect_returns_empty_on_timeout(self) -> None:
        """超时时返回空集合。"""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10),
        ):
            encoders = EncoderDetector.detect("/fake/ffmpeg")
            assert encoders == set()

    def test_clear_cache_forces_redetection(self) -> None:
        """清除缓存后应重新执行检测。"""
        mock_result = MagicMock()
        mock_result.stdout = "A..... aac  AAC\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            EncoderDetector.detect("/fake/ffmpeg")
            EncoderDetector.clear_cache()
            EncoderDetector.detect("/fake/ffmpeg")
            assert mock_run.call_count == 2

    def test_detect_skips_short_lines(self) -> None:
        """短行（< 8 字符）应被跳过。"""
        fake_output = "A.. aac\n"  # 太短
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            encoders = EncoderDetector.detect("/fake/ffmpeg")
            # "A.. aac" 只有 7 字符，应被跳过
            assert encoders == set()

    def test_detect_different_paths_independent_cache(self) -> None:
        """不同 ffmpeg 路径应有独立的缓存条目。"""
        mock_result1 = MagicMock()
        mock_result1.stdout = "A..... aac  AAC\n"
        mock_result2 = MagicMock()
        mock_result2.stdout = "A..... libfdk_aac  FDK AAC\n"

        with patch(
            "subprocess.run",
            side_effect=[mock_result1, mock_result2],
        ) as mock_run:
            enc1 = EncoderDetector.detect("/ffmpeg1")
            enc2 = EncoderDetector.detect("/ffmpeg2")
            assert enc1 != enc2
            assert "aac" in enc1
            assert "libfdk_aac" in enc2
            assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# Task 9: ffmpeg 路径缓存
# ---------------------------------------------------------------------------
class TestFfmpegPathCache:
    """``validate_ffmpeg`` 路径缓存与 ``clear_ffmpeg_cache`` 行为。"""

    def setup_method(self) -> None:
        """每个测试前清除缓存。"""
        clear_ffmpeg_cache()

    def teardown_method(self) -> None:
        """每个测试后清除缓存。"""
        clear_ffmpeg_cache()

    def test_validate_caches_valid_path(self, tmp_path) -> None:
        """有效路径校验后应缓存结果。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        result1 = validate_ffmpeg(str(fake_ffmpeg))
        # 缓存应包含该路径
        assert str(fake_ffmpeg) in _ffmpeg_path_cache
        assert _ffmpeg_path_cache[str(fake_ffmpeg)] == result1

    def test_validate_caches_not_found(self) -> None:
        """无效路径应缓存 ``None``（未找到）。"""
        with pytest.raises(EncoderNotFoundError):
            validate_ffmpeg("/nonexistent/ffmpeg.exe")
        # 缓存应记录 None
        assert "/nonexistent/ffmpeg.exe" in _ffmpeg_path_cache
        assert _ffmpeg_path_cache["/nonexistent/ffmpeg.exe"] is None

    def test_cached_not_found_raises_again(self) -> None:
        """缓存命中 ``None`` 时应再次抛出 ``EncoderNotFoundError``。"""
        with pytest.raises(EncoderNotFoundError):
            validate_ffmpeg("/nonexistent/ffmpeg.exe")
        # 第二次应命中缓存（不调用 os.path.isfile）
        with patch("os.path.isfile", side_effect=AssertionError("不应调用 isfile")):
            with pytest.raises(EncoderNotFoundError):
                validate_ffmpeg("/nonexistent/ffmpeg.exe")

    def test_clear_cache_empties_path_cache(self, tmp_path) -> None:
        """``clear_ffmpeg_cache`` 应清除路径缓存。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")
        validate_ffmpeg(str(fake_ffmpeg))
        assert len(_ffmpeg_path_cache) > 0
        clear_ffmpeg_cache()
        assert len(_ffmpeg_path_cache) == 0

    def test_clear_cache_empties_encoder_cache(self, tmp_path) -> None:
        """``clear_ffmpeg_cache`` 应同时清除编码器检测缓存。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        mock_result = MagicMock()
        mock_result.stdout = "A..... aac  AAC\n"
        with patch("subprocess.run", return_value=mock_result):
            EncoderDetector.detect(str(fake_ffmpeg))
        assert len(EncoderDetector._cache) > 0

        clear_ffmpeg_cache()
        assert len(EncoderDetector._cache) == 0

    def test_cached_valid_path_skips_isfile(self, tmp_path) -> None:
        """缓存命中有效路径时不应再次调用 ``os.path.isfile``。"""
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffmpeg.write_text("fake")

        # 第一次校验并缓存
        validate_ffmpeg(str(fake_ffmpeg))

        # 第二次应命中缓存，不调用 isfile
        with patch("os.path.isfile", side_effect=AssertionError("不应调用 isfile")):
            result = validate_ffmpeg(str(fake_ffmpeg))
            assert result is not None


# ---------------------------------------------------------------------------
# Task 9: build_encode_args 支持 encoder 参数
# ---------------------------------------------------------------------------
class TestBuildEncodeArgsWithEncoder:
    """``build_encode_args`` / ``build_encode_stream_args`` 的 encoder 参数。"""

    def test_build_encode_args_uses_custom_encoder(self) -> None:
        """``encoder`` 参数应覆盖 ``fmt.encoder``。"""
        args = build_encode_args(
            src_wav="input.wav",
            dst_path="output.mp3",
            fmt=AudioFormat.MP3,
            encoder="mp3_mf",
        )
        assert "-c:a" in args
        idx = args.index("-c:a")
        assert args[idx + 1] == "mp3_mf"

    def test_build_encode_args_defaults_to_fmt_encoder(self) -> None:
        """``encoder=None`` 时使用 ``fmt.encoder``。"""
        args = build_encode_args(
            src_wav="input.wav",
            dst_path="output.mp3",
            fmt=AudioFormat.MP3,
        )
        idx = args.index("-c:a")
        assert args[idx + 1] == AudioFormat.MP3.encoder

    def test_build_encode_stream_args_uses_custom_encoder(self) -> None:
        """流式参数应支持 ``encoder`` 参数。"""
        args = build_encode_stream_args(
            dst_path="output.aac",
            fmt=AudioFormat.AAC,
            encoder="libfdk_aac",
        )
        idx = args.index("-c:a")
        assert args[idx + 1] == "libfdk_aac"

    def test_build_encode_stream_args_defaults_to_fmt_encoder(self) -> None:
        """流式参数 ``encoder=None`` 时使用默认编码器。"""
        args = build_encode_stream_args(
            dst_path="output.aac",
            fmt=AudioFormat.AAC,
        )
        idx = args.index("-c:a")
        assert args[idx + 1] == AudioFormat.AAC.encoder
