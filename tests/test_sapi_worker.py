"""sapi_worker 模块单元测试。

mock ``sapi_runner`` 的 COM 调用函数，验证 :class:`SapiTask` 的
``_build_args``、``run`` 流程（WAV 直出 / 非 WAV 管道转码）、取消、
空文件处理、SapiError 错误传播，以及 ``_read_text_file`` 的编码处理。

测试需要 QApplication 实例（offscreen 模式），因为 ``SapiTask`` 继承
``QRunnable`` 且使用 ``TaskSignals``（QObject）。
"""
from __future__ import annotations

import os

# 在导入 PySide6 之前设置 offscreen 平台，避免在无显示环境失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.audio_encoder import AudioFormat
from balcon_batch_tts.core.sapi_config import SapiConfig
from balcon_batch_tts.core.sapi_worker import SapiTask


# ---------------------------------------------------------------------------
# QApplication 会话级单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# _build_args
# ---------------------------------------------------------------------------
class TestBuildArgs:
    """``_build_args`` 应返回空列表（SAPI5 无命令行参数）。"""

    def test_build_args_returns_empty(self, qapp: QApplication) -> None:
        config = SapiConfig.create_default()
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="output.wav",
        )
        assert task._build_args() == []

    def test_build_args_returns_empty_with_custom_config(
        self, qapp: QApplication
    ) -> None:
        config = SapiConfig(voice_name="TestVoice", rate=5, volume=80, pitch=3)
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="output.wav",
        )
        assert task._build_args() == []

    def test_build_args_returns_list_type(
        self, qapp: QApplication
    ) -> None:
        """返回值应为 list 类型。"""
        config = SapiConfig.create_default()
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="output.wav",
        )
        result = task._build_args()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# run: WAV 格式
# ---------------------------------------------------------------------------
class TestRunWav:
    """WAV 格式输出应通过 ``synthesize_to_file`` 直接合成。"""

    def test_run_wav(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """WAV 格式：mock ``synthesize_to_file``，验证信号发射。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello world", encoding="utf-8")
        output_path = str(tmp_path / "out.wav")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path=output_path,
            output_format=AudioFormat.WAV,
        )

        started: list[str] = []
        finished: list[tuple] = []
        task.signals.started.connect(lambda f: started.append(f))
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
             ) as mock_synth:
            task.run()

        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args.kwargs
        assert call_kwargs["text"] == "hello world"
        assert call_kwargs["output_path"] == output_path
        assert call_kwargs["voice_name"] == ""
        assert call_kwargs["rate"] == 0
        assert call_kwargs["volume"] == 100
        assert call_kwargs["pitch"] == 0

        assert len(started) == 1
        assert started[0] == "input.txt"
        assert len(finished) == 1
        assert finished[0][0] == "input.txt"
        assert finished[0][1] == 0  # returncode 0


# ---------------------------------------------------------------------------
# run: 非 WAV 格式（管道转码）
# ---------------------------------------------------------------------------
class TestRunNonWav:
    """非 WAV 格式应通过 ``synthesize_to_memory`` + ``encode_audio_from_stream``。"""

    def test_run_non_wav(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """非 WAV 格式：mock 合成到内存 + ffmpeg 转码。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello world", encoding="utf-8")
        output_path = str(tmp_path / "out.mp3")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path=output_path,
            output_format=AudioFormat.MP3,
            ffmpeg_path="/usr/bin/ffmpeg",
        )

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_memory",
                 return_value=b"wav bytes",
             ) as mock_synth_mem, \
             patch(
                 "balcon_batch_tts.core.sapi_worker.encode_audio_from_stream"
             ) as mock_encode:
            task.run()

        mock_synth_mem.assert_called_once()
        mock_encode.assert_called_once()

        # 验证 encode_audio_from_stream 的参数
        encode_kwargs = mock_encode.call_args.kwargs
        assert encode_kwargs["dst_path"] == output_path
        assert encode_kwargs["fmt"] == AudioFormat.MP3
        assert encode_kwargs["ffmpeg_path"] == "/usr/bin/ffmpeg"
        # input_stream 应为 BytesIO，包含 wav bytes
        input_stream = encode_kwargs["input_stream"]
        assert input_stream.getvalue() == b"wav bytes"

        assert len(finished) == 1
        assert finished[0][1] == 0


# ---------------------------------------------------------------------------
# run: 取消
# ---------------------------------------------------------------------------
class TestRunCancelled:
    """取消事件设置时应提前返回。"""

    def test_run_cancelled(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """取消事件设置时 ``run`` 应发射 finished(-1) 并提前返回。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )
        task._cancel_event.set()

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
             ) as mock_synth:
            task.run()

        assert len(finished) == 1
        assert finished[0][1] == -1  # 取消返回码
        assert "取消" in finished[0][2]
        mock_synth.assert_not_called()


# ---------------------------------------------------------------------------
# run: 空文件
# ---------------------------------------------------------------------------
class TestRunEmptyFile:
    """空文本文件时应正常返回（不合成）。"""

    def test_run_empty_file(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        input_file = tmp_path / "empty.txt"
        input_file.write_text("", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
             ) as mock_synth:
            task.run()

        assert len(finished) == 1
        assert finished[0][1] == 0  # 空文件视为成功
        mock_synth.assert_not_called()

    def test_run_whitespace_only_file(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """仅含空白字符的文件也应视为空文件。"""
        input_file = tmp_path / "ws.txt"
        input_file.write_text("   \n\t  \n", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
             ) as mock_synth:
            task.run()

        assert len(finished) == 1
        assert finished[0][1] == 0
        mock_synth.assert_not_called()


# ---------------------------------------------------------------------------
# run: SapiError 错误传播
# ---------------------------------------------------------------------------
class TestRunSapiError:
    """``SapiError`` 时应发射 error 信号并以返回码 -1 结束。"""

    def test_run_sapi_error(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        from balcon_batch_tts.core.sapi_runner import SapiError

        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )

        error: list[tuple] = []
        finished: list[tuple] = []
        task.signals.error.connect(lambda f, msg: error.append((f, msg)))
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file",
                 side_effect=SapiError("COM error"),
             ):
            task.run()

        assert len(error) == 1
        assert error[0][0] == "input.txt"
        assert "COM error" in error[0][1]
        assert len(finished) == 1
        assert finished[0][1] == -1

    def test_run_unexpected_error(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """未预期异常也应发射 error 信号。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )

        error: list[tuple] = []
        finished: list[tuple] = []
        task.signals.error.connect(lambda f, msg: error.append((f, msg)))
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
             patch(
                 "balcon_batch_tts.core.sapi_worker.synthesize_to_file",
                 side_effect=RuntimeError("unexpected"),
             ):
            task.run()

        assert len(error) == 1
        assert "unexpected" in error[0][1]
        assert finished[0][1] == -1


# ---------------------------------------------------------------------------
# run: COM 生命周期
# ---------------------------------------------------------------------------
class TestComLifecycle:
    """COM 生命周期：``init_com`` 幂等性、``SapiError`` 时 SpVoice 失效。"""

    def test_com_init_called_once_per_thread(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """同一线程连续运行两个任务，``CoInitialize`` 仅调用一次。

        ``init_com`` 通过线程本地 ``com_initialized`` 标志保证幂等：首个任务
        实际执行 ``CoInitialize``，第二个任务跳过。本测试不 mock
        ``sapi_worker.init_com``，而是 mock ``sapi_runner.pythoncom``，让真实
        的幂等逻辑执行并验证 ``CoInitialize`` 调用次数。
        """
        from balcon_batch_tts.core import sapi_runner

        # 清理可能残留的 com_initialized 标志，确保首任务实际初始化
        if hasattr(sapi_runner._thread_local, "com_initialized"):
            del sapi_runner._thread_local.com_initialized

        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task1 = SapiTask(
            input_file=str(input_file), config=config, output_path="out1.wav"
        )
        task2 = SapiTask(
            input_file=str(input_file), config=config, output_path="out2.wav"
        )

        finished: list[tuple] = []
        for task in (task1, task2):
            task.signals.finished.connect(
                lambda f, rc, err, t: finished.append((f, rc, err, t))
            )

        try:
            with patch(
                "balcon_batch_tts.core.sapi_runner._SAPI_AVAILABLE", True
            ), patch(
                "balcon_batch_tts.core.sapi_runner.pythoncom"
            ) as mock_pythoncom, patch(
                "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
            ):
                task1.run()
                task2.run()

            # 幂等性：两个任务在同一线程，CoInitialize 仅调用一次
            assert mock_pythoncom.CoInitialize.call_count == 1
            assert len(finished) == 2
            assert all(f[1] == 0 for f in finished)
        finally:
            # 清理线程本地 COM 标志，避免影响后续测试
            if hasattr(sapi_runner._thread_local, "com_initialized"):
                del sapi_runner._thread_local.com_initialized

    def test_invalidate_thread_voice_on_sapi_error(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """``SapiError`` 时应调用 ``invalidate_thread_voice`` 失效缓存 SpVoice。"""
        from balcon_batch_tts.core.sapi_runner import SapiError

        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file), config=config, output_path="out.wav"
        )

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_file",
            side_effect=SapiError("COM error"),
        ), patch(
            "balcon_batch_tts.core.sapi_worker.invalidate_thread_voice"
        ) as mock_invalidate:
            task.run()

        mock_invalidate.assert_called_once()
        assert len(finished) == 1
        assert finished[0][1] == -1

    def test_invalidate_not_called_on_success(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """合成成功时不应调用 ``invalidate_thread_voice``。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello", encoding="utf-8")

        config = SapiConfig.create_default()
        task = SapiTask(
            input_file=str(input_file), config=config, output_path="out.wav"
        )

        finished: list[tuple] = []
        task.signals.finished.connect(
            lambda f, rc, err, t: finished.append((f, rc, err, t))
        )

        with patch("balcon_batch_tts.core.sapi_worker.init_com"), patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
        ), patch(
            "balcon_batch_tts.core.sapi_worker.invalidate_thread_voice"
        ) as mock_invalidate:
            task.run()

        mock_invalidate.assert_not_called()
        assert len(finished) == 1
        assert finished[0][1] == 0


# ---------------------------------------------------------------------------
# _read_text_file: 编码处理
# ---------------------------------------------------------------------------
class TestReadTextFileEncoding:
    """``_read_text_file`` 应使用 ``config.input_encoding`` 读取文件。"""

    def test_read_text_file_encoding(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """使用 config.input_encoding 读取文件内容。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("你好世界", encoding="gbk")

        config = SapiConfig(input_encoding="gbk")
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )
        text = task._read_text_file()
        assert text == "你好世界"

    def test_read_text_file_utf8(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """默认 utf-8 编码应正确读取。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello 世界", encoding="utf-8")

        config = SapiConfig.create_default()  # input_encoding = utf-8
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )
        text = task._read_text_file()
        assert text == "hello 世界"

    def test_read_text_file_big5(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Big5 编码应正确读取。"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("你好", encoding="big5")

        config = SapiConfig(input_encoding="big5")
        task = SapiTask(
            input_file=str(input_file),
            config=config,
            output_path="out.wav",
        )
        text = task._read_text_file()
        assert text == "你好"


# ---------------------------------------------------------------------------
# _exec_pipe: 内存预算与降级
# ---------------------------------------------------------------------------
class TestExecPipeMemoryBudget:
    """``_exec_pipe`` 应在文本超限时降级到文件模式，否则走内存管道。"""

    def test_exec_pipe_falls_back_to_file_mode_for_large_text(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """文本字节数超过 max_text_bytes 时降级到文件模式。

        降级路径：synthesize_to_file → encode_audio → os.remove。
        不应调用 synthesize_to_memory / encode_audio_from_stream。
        """
        config = SapiConfig.create_default()
        config.max_text_bytes = 100  # 极低阈值，强制触发降级
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path=str(tmp_path / "out.mp3"),
            output_format=AudioFormat.MP3,
            ffmpeg_path="/usr/bin/ffmpeg",
        )

        with patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
        ) as mock_synth_file, patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_memory"
        ) as mock_synth_mem, patch(
            "balcon_batch_tts.core.sapi_worker.encode_audio",
            return_value=(0, "", ""),
        ) as mock_encode, patch(
            "balcon_batch_tts.core.sapi_worker.encode_audio_from_stream"
        ) as mock_encode_stream, patch(
            "balcon_batch_tts.core.sapi_worker.os.path.isfile", return_value=True
        ), patch(
            "balcon_batch_tts.core.sapi_worker.os.remove"
        ) as mock_remove:
            task._exec_pipe("x" * 200, "test.txt")

        # 降级路径：synthesize_to_file 被调用
        mock_synth_file.assert_called_once()
        synth_kwargs = mock_synth_file.call_args.kwargs
        assert synth_kwargs["text"] == "x" * 200
        assert synth_kwargs["output_path"].endswith(".out.mp3.tmp.wav")
        assert synth_kwargs["voice_name"] == ""
        assert synth_kwargs["rate"] == 0
        assert synth_kwargs["volume"] == 100
        assert synth_kwargs["pitch"] == 0
        assert synth_kwargs["audio_format"] == 22

        # 内存路径不应被调用
        mock_synth_mem.assert_not_called()
        mock_encode_stream.assert_not_called()

        # encode_audio 被调用（文件转码）
        mock_encode.assert_called_once()
        enc_kwargs = mock_encode.call_args.kwargs
        assert enc_kwargs["dst_path"] == str(tmp_path / "out.mp3")
        assert enc_kwargs["fmt"] == AudioFormat.MP3
        assert enc_kwargs["ffmpeg_path"] == "/usr/bin/ffmpeg"
        assert enc_kwargs["src_wav"].endswith(".out.mp3.tmp.wav")

        # 临时 WAV 应被删除
        mock_remove.assert_called_once()
        removed_path = mock_remove.call_args.args[0]
        assert removed_path.endswith(".out.mp3.tmp.wav")

    def test_exec_pipe_uses_memory_mode_for_small_text(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """文本字节数未超过 max_text_bytes 时走内存管道模式。

        内存路径：synthesize_to_memory → encode_audio_from_stream。
        不应调用 synthesize_to_file / encode_audio。
        """
        config = SapiConfig.create_default()
        config.max_text_bytes = 10000  # 高阈值，不触发降级
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path=str(tmp_path / "out.mp3"),
            output_format=AudioFormat.MP3,
            ffmpeg_path="/usr/bin/ffmpeg",
        )

        with patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
        ) as mock_synth_file, patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_memory",
            return_value=b"wav bytes",
        ) as mock_synth_mem, patch(
            "balcon_batch_tts.core.sapi_worker.encode_audio"
        ) as mock_encode, patch(
            "balcon_batch_tts.core.sapi_worker.encode_audio_from_stream",
            return_value=(0, "", ""),
        ) as mock_encode_stream:
            task._exec_pipe("small", "test.txt")

        # 内存路径：synthesize_to_memory 被调用
        mock_synth_mem.assert_called_once()
        mem_kwargs = mock_synth_mem.call_args.kwargs
        assert mem_kwargs["text"] == "small"
        assert mem_kwargs["voice_name"] == ""
        assert mem_kwargs["rate"] == 0
        assert mem_kwargs["volume"] == 100
        assert mem_kwargs["pitch"] == 0
        assert mem_kwargs["audio_format"] == 22

        # encode_audio_from_stream 被调用
        mock_encode_stream.assert_called_once()
        enc_kwargs = mock_encode_stream.call_args.kwargs
        assert enc_kwargs["dst_path"] == str(tmp_path / "out.mp3")
        assert enc_kwargs["fmt"] == AudioFormat.MP3
        assert enc_kwargs["ffmpeg_path"] == "/usr/bin/ffmpeg"
        # input_stream 为 BytesIO 包装的 wav bytes
        assert enc_kwargs["input_stream"].getvalue() == b"wav bytes"

        # 文件路径不应被调用
        mock_synth_file.assert_not_called()
        mock_encode.assert_not_called()

    def test_exec_pipe_via_file_cleans_up_temp_wav_on_encode_failure(
        self,
        qapp: QApplication,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """ffmpeg 转码失败时仍应删除临时 WAV，并抛出 SapiError。"""
        from balcon_batch_tts.core.sapi_runner import SapiError

        config = SapiConfig.create_default()
        config.max_text_bytes = 100
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path=str(tmp_path / "out.mp3"),
            output_format=AudioFormat.MP3,
            ffmpeg_path="/usr/bin/ffmpeg",
        )

        with patch(
            "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
        ), patch(
            "balcon_batch_tts.core.sapi_worker.encode_audio",
            return_value=(1, "", "ffmpeg error"),
        ), patch(
            "balcon_batch_tts.core.sapi_worker.os.path.isfile", return_value=True
        ), patch(
            "balcon_batch_tts.core.sapi_worker.os.remove"
        ) as mock_remove:
            with pytest.raises(SapiError, match="ffmpeg 转码失败"):
                task._exec_pipe("x" * 200, "test.txt")

        # 即使转码失败，临时 WAV 也应被删除
        mock_remove.assert_called_once()


# ---------------------------------------------------------------------------
# _temp_wav_path: 命名规则
# ---------------------------------------------------------------------------
class TestTempWavPath:
    """``_temp_wav_path`` 命名规则：``.{最终文件名}.tmp.wav``，同目录。"""

    def test_temp_wav_path_naming(
        self, qapp: QApplication
    ) -> None:
        """临时 WAV 路径应为 ``.{filename}.tmp.wav``，位于同目录。"""
        config = SapiConfig.create_default()
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="/tmp/out.mp3",
            output_format=AudioFormat.MP3,
        )
        # 使用 os.path.join 保证跨平台路径分隔符一致
        assert task._temp_wav_path() == os.path.join("/tmp", ".out.mp3.tmp.wav")

    def test_temp_wav_path_relative(
        self, qapp: QApplication
    ) -> None:
        """相对路径（无目录）时使用 ``.`` 作为目录。"""
        config = SapiConfig.create_default()
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="out.mp3",
            output_format=AudioFormat.MP3,
        )
        assert task._temp_wav_path() == os.path.join(".", ".out.mp3.tmp.wav")

    def test_temp_wav_path_with_subdirectory(
        self, qapp: QApplication
    ) -> None:
        """带子目录的输出路径应保留目录结构。"""
        config = SapiConfig.create_default()
        task = SapiTask(
            input_file="input.txt",
            config=config,
            output_path="output/audio.mp3",
            output_format=AudioFormat.MP3,
        )
        assert task._temp_wav_path() == os.path.join(
            "output", ".audio.mp3.tmp.wav"
        )
