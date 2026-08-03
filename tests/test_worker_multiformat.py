"""BalconTask 多格式输出单元测试。

验证 :class:`BalconTask` 在不同 ``output_format`` 下的行为：
- WAV 格式：保持原行为（balcon 直接输出到最终路径）
- 非 WAV 格式：balcon 输出临时 WAV → ffmpeg 转码 → 删除临时 WAV
- 转码失败时保留临时 WAV 并发射 error 信号
- 取消时正确终止 balcon 与 ffmpeg 子进程

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.audio_encoder import AudioFormat, EncoderError
from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.worker import BalconTask


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# WAV 格式（默认，向后兼容）
# ---------------------------------------------------------------------------
class TestWavFormat:
    """WAV 格式保持原行为契约。"""

    def test_wav_uses_final_output_path(self, qapp: QApplication) -> None:
        """WAV 格式：``w_output`` 应直接指向最终输出路径。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="/output/final.wav",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.WAV,
        )
        args = task._build_args()
        # args 中应包含 -w /output/final.wav
        assert "-w" in args
        idx = args.index("-w")
        assert args[idx + 1] == "/output/final.wav"

    def test_wav_default_output_format(self, qapp: QApplication) -> None:
        """默认 ``output_format`` 应为 WAV（向后兼容）。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="/output/final.wav",
            balcon_path="/fake/balcon.exe",
        )
        assert task._output_format is AudioFormat.WAV

    def test_wav_no_transcode_called(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """WAV 格式：``_exec`` 不应调用转码。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(tmp_path / "final.wav"),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.WAV,
        )

        # mock run_balcon 返回成功
        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (0, "", "")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                task._exec(task._build_args())
                mock_encode.assert_not_called()


# ---------------------------------------------------------------------------
# 非 WAV 格式（多格式输出）
# ---------------------------------------------------------------------------
class TestNonWavFormat:
    """非 WAV 格式：balcon 输出临时 WAV → ffmpeg 转码 → 删除临时 WAV。"""

    def test_mp3_uses_temp_wav_path(self, qapp: QApplication) -> None:
        """MP3 格式：``w_output`` 应指向临时 WAV 路径。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="/output/final.mp3",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )
        args = task._build_args()
        assert "-w" in args
        idx = args.index("-w")
        # 应指向临时 WAV，而非最终 mp3
        temp_path = args[idx + 1]
        assert temp_path.endswith(".tmp.wav")
        assert ".final.mp3" in temp_path  # 文件名前缀有 .

    def test_temp_wav_path_naming(self, qapp: QApplication) -> None:
        """临时 WAV 命名规则：``.<filename>.tmp.wav``。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="/output/final.mp3",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
        )
        temp = task._temp_wav_path()
        assert temp == os.path.join("/output", ".final.mp3.tmp.wav")

    def test_temp_wav_path_no_directory(self, qapp: QApplication) -> None:
        """输出路径无目录时，临时文件位于当前目录。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="final.mp3",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
        )
        temp = task._temp_wav_path()
        assert temp == os.path.join(".", ".final.mp3.tmp.wav")

    def test_mp3_transcode_called_on_success(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """MP3 格式：balcon 成功后应调用 ffmpeg 转码。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        # 创建临时 WAV 文件模拟 balcon 已输出
        temp_wav = task._temp_wav_path()
        with open(temp_wav, "w") as f:
            f.write("fake wav content")

        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (0, "", "")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                mock_encode.return_value = (0, "", "")
                task._exec(task._build_args())
                mock_encode.assert_called_once()
                # 校验调用参数
                call_args = mock_encode.call_args
                assert call_args.kwargs["fmt"] is AudioFormat.MP3
                assert call_args.kwargs["ffmpeg_path"] == "/fake/ffmpeg.exe"

        # 转码成功后临时 WAV 应被删除
        assert not os.path.exists(temp_wav)

    def test_transcode_failure_keeps_temp_wav(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """转码失败时应保留临时 WAV 便于诊断。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        temp_wav = task._temp_wav_path()
        with open(temp_wav, "w") as f:
            f.write("fake wav content")

        # 收集 error 信号
        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (0, "", "")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                mock_encode.return_value = (1, "", "encode error")
                task._exec(task._build_args())

        # 应发射 error 信号
        assert len(errors) == 1
        assert "input.txt" in errors[0][0]
        assert "转码失败" in errors[0][1]

        # 临时 WAV 应保留
        assert os.path.exists(temp_wav)

    def test_transcode_missing_temp_wav_emits_error(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """balcon 成功但临时 WAV 不存在时应发射 error。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        # 不创建临时 WAV 文件
        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (0, "", "")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                task._exec(task._build_args())
                mock_encode.assert_not_called()

        assert len(errors) == 1
        assert "临时 WAV 文件不存在" in errors[0][1]

    def test_balcon_failure_skips_transcode(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """balcon 失败（返回码非零）时不进入转码阶段。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (1, "", "balcon error")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                rc, _, _ = task._exec(task._build_args())
                mock_encode.assert_not_called()
                assert rc == 1

    def test_transcode_encoder_error_emits_error(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``encode_audio`` 抛出 ``EncoderError`` 时应发射 error 信号。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        temp_wav = task._temp_wav_path()
        with open(temp_wav, "w") as f:
            f.write("fake wav content")

        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch("balcon_batch_tts.core.worker.run_balcon") as mock_run:
            mock_run.return_value = (0, "", "")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio"
            ) as mock_encode:
                mock_encode.side_effect = EncoderError("ffmpeg not found")
                task._exec(task._build_args())

        assert len(errors) == 1
        assert "转码失败" in errors[0][1]
        assert "ffmpeg not found" in errors[0][1]


# ---------------------------------------------------------------------------
# 各格式覆盖测试
# ---------------------------------------------------------------------------
class TestAllFormatsIntegration:
    """所有非 WAV 格式都能正确触发转码流程。"""

    @pytest.mark.parametrize(
        "fmt", [fmt for fmt in AudioFormat if fmt.needs_ffmpeg]
    )
    def test_each_format_uses_temp_wav(
        self, qapp: QApplication, fmt: AudioFormat
    ) -> None:
        """每种非 WAV 格式都应使用临时 WAV 路径。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=f"/output/final.{fmt.extension}",
            balcon_path="/fake/balcon.exe",
            output_format=fmt,
            ffmpeg_path="/fake/ffmpeg.exe",
        )
        args = task._build_args()
        idx = args.index("-w")
        temp_path = args[idx + 1]
        assert temp_path.endswith(".tmp.wav")

    @pytest.mark.parametrize("fmt", list(AudioFormat))
    def test_each_format_can_be_constructed(
        self, qapp: QApplication, fmt: AudioFormat
    ) -> None:
        """每种格式都能被构造（不抛异常）。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=f"/output/final.{fmt.extension}",
            balcon_path="/fake/balcon.exe",
            output_format=fmt,
            ffmpeg_path="/fake/ffmpeg.exe",
        )
        assert task._output_format is fmt


# ---------------------------------------------------------------------------
# Task 4: 管道流式转码（balcon stdout → ffmpeg stdin）
# ---------------------------------------------------------------------------
class TestPipeStreaming:
    """管道流式转码路径测试。

    验证：
    - 非 WAV 格式优先使用管道模式（``run_balcon_to_stream`` + ``encode_audio_from_stream``）
    - 管道模式成功时不调用文件模式的 ``run_balcon`` / ``encode_audio``
    - 管道模式失败时回退到文件模式
    - WAV 格式不走管道模式
    - 取消时不回退
    - ``_build_pipe_args`` 生成正确的 ``-o`` 参数（无 ``-w``）
    """

    def test_build_pipe_args_has_o_no_w(self, qapp: QApplication) -> None:
        """管道模式参数应包含 ``-o`` 且不包含 ``-w``。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path="/output/final.mp3",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )
        pipe_args = task._build_pipe_args()
        assert "-o" in pipe_args
        assert "-w" not in pipe_args

    def test_build_pipe_args_includes_input_file(self, qapp: QApplication) -> None:
        """管道模式参数应包含输入文件。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="my_input.txt",
            config=config,
            output_path="/output/final.mp3",
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )
        pipe_args = task._build_pipe_args()
        assert "-f" in pipe_args
        idx = pipe_args.index("-f")
        assert pipe_args[idx + 1] == "my_input.txt"

    def test_pipe_mode_called_for_non_wav(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """非 WAV 格式应优先调用管道模式函数。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        # mock 管道模式函数返回成功
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock()
        mock_thread = MagicMock()
        mock_thread.join = MagicMock()

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.return_value = (mock_proc, mock_thread, [])
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                mock_enc_stream.return_value = (0, "", "")
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    with patch(
                        "balcon_batch_tts.core.worker.encode_audio"
                    ) as mock_enc:
                        task._exec(task._build_args())
                        # 管道模式函数应被调用
                        mock_stream.assert_called_once()
                        mock_enc_stream.assert_called_once()
                        # 文件模式函数不应被调用
                        mock_run.assert_not_called()
                        mock_enc.assert_not_called()

    def test_pipe_mode_success_returns_zero(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """管道模式成功时应返回返回码 0。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock()
        mock_thread = MagicMock()

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.return_value = (mock_proc, mock_thread, [])
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                mock_enc_stream.return_value = (0, "", "")
                rc, _, _ = task._exec(task._build_args())
                assert rc == 0

    def test_pipe_failure_falls_back_to_file_mode(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """管道模式失败时应回退到文件模式。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        # 创建临时 WAV 模拟文件模式的 balcon 输出
        temp_wav = task._temp_wav_path()
        with open(temp_wav, "w") as f:
            f.write("fake wav")

        # 管道模式抛出异常
        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.side_effect = Exception("pipe broke")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    mock_run.return_value = (0, "", "")
                    with patch(
                        "balcon_batch_tts.core.worker.encode_audio"
                    ) as mock_enc:
                        mock_enc.return_value = (0, "", "")
                        rc, _, _ = task._exec(task._build_args())
                        # 管道模式被调用但失败
                        mock_stream.assert_called_once()
                        # 文件模式被调用作为回退
                        mock_run.assert_called_once()
                        mock_enc.assert_called_once()
                        assert rc == 0

    def test_pipe_failure_emits_fallback_log(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """管道模式失败时应发射回退日志消息。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        temp_wav = task._temp_wav_path()
        with open(temp_wav, "w") as f:
            f.write("fake wav")

        logs = []
        task.signals.log.connect(lambda msg: logs.append(msg))

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.side_effect = Exception("pipe broke")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ):
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    mock_run.return_value = (0, "", "")
                    with patch(
                        "balcon_batch_tts.core.worker.encode_audio"
                    ) as mock_enc:
                        mock_enc.return_value = (0, "", "")
                        task._exec(task._build_args())

        # 应有回退日志
        fallback_logs = [l for l in logs if "管道模式失败" in l]
        assert len(fallback_logs) >= 1

    def test_cancel_does_not_fall_back(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """取消导致的管道失败不应回退到文件模式。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        # 设置取消事件
        task._cancel_event.set()

        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.side_effect = EncoderError("任务已取消")
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ):
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    with patch(
                        "balcon_batch_tts.core.worker.encode_audio"
                    ) as mock_enc:
                        rc, _, _ = task._exec(task._build_args())
                        # 不应回退到文件模式
                        mock_run.assert_not_called()
                        mock_enc.assert_not_called()
                        assert rc == -1
                        assert len(errors) == 1

    def test_wav_format_does_not_use_pipe(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """WAV 格式不应调用管道模式函数。"""
        config = BalconConfig.create_default()
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(tmp_path / "final.wav"),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.WAV,
        )

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    mock_run.return_value = (0, "", "")
                    task._exec(task._build_args())
                    # WAV 格式不走管道
                    mock_stream.assert_not_called()
                    mock_enc_stream.assert_not_called()

    def test_pipe_balcon_failure_returns_error(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """管道模式中 balcon 失败（返回码非零）应返回错误，不回退。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.returncode = 1  # balcon 失败
        mock_proc.wait = MagicMock()
        mock_thread = MagicMock()

        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.return_value = (mock_proc, mock_thread, [b"balcon error"])
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                mock_enc_stream.return_value = (0, "", "")
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    rc, _, _ = task._exec(task._build_args())
                    # balcon 失败返回非零码，不回退
                    assert rc != 0
                    mock_run.assert_not_called()
                    assert len(errors) == 1

    def test_pipe_ffmpeg_failure_returns_error(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """管道模式中 ffmpeg 失败（返回码非零）应返回错误，不回退。"""
        config = BalconConfig.create_default()
        output_path = tmp_path / "final.mp3"
        task = BalconTask(
            input_file="input.txt",
            config=config,
            output_path=str(output_path),
            balcon_path="/fake/balcon.exe",
            output_format=AudioFormat.MP3,
            ffmpeg_path="/fake/ffmpeg.exe",
        )

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.returncode = 0  # balcon 成功
        mock_proc.wait = MagicMock()
        mock_thread = MagicMock()

        errors = []
        task.signals.error.connect(lambda name, msg: errors.append((name, msg)))

        with patch(
            "balcon_batch_tts.core.worker.run_balcon_to_stream"
        ) as mock_stream:
            mock_stream.return_value = (mock_proc, mock_thread, [])
            with patch(
                "balcon_batch_tts.core.worker.encode_audio_from_stream"
            ) as mock_enc_stream:
                mock_enc_stream.return_value = (1, "", "encode error")
                with patch(
                    "balcon_batch_tts.core.worker.run_balcon"
                ) as mock_run:
                    rc, _, _ = task._exec(task._build_args())
                    # ffmpeg 失败返回非零码，不回退
                    assert rc == 1
                    mock_run.assert_not_called()
                    assert len(errors) == 1
