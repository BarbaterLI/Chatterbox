"""SAPI5 直达 TTS 任务工作单元。

定义 :class:`SapiTask`，封装单个 SAPI5 COM TTS 任务的执行逻辑，继承自
:class:`chatterbox.core.base_worker.BaseToolTask`。

性能优化：
- 线程本地 SpVoice 复用（通过 sapi_runner._get_thread_voice()）
- COM 初始化仅在首次任务时执行
- 非 WAV 格式使用 SpMemoryStream → ffmpeg 管道转码（无临时文件）
- 大文本降级：非 WAV 模式下文本字节数超过 ``max_text_bytes`` 时降级到
  文件模式（合成到临时 WAV → ffmpeg 转码 → 删除临时 WAV），避免 12 并发
  下 SpMemoryStream OOM
"""
from __future__ import annotations

import io
import logging
import os
import time

from chatterbox.core.audio_encoder import (
    AudioFormat,
    encode_audio,
    encode_audio_from_stream,
)
from chatterbox.core.base_worker import BaseToolTask
from chatterbox.core.sapi_config import SapiConfig
from chatterbox.core.sapi_runner import (
    SapiError,
    cleanup_thread,
    init_com,
    invalidate_thread_voice,
    synthesize_to_file,
    synthesize_to_memory,
    uninit_com,
)
from chatterbox.core.tool_type import ProcessPriority

logger = logging.getLogger(__name__)


class SapiTask(BaseToolTask):
    """单个 SAPI5 COM TTS 任务的 QRunnable 工作单元。

    在子线程中通过 SAPI5 COM 接口直接调用语音合成，无需外部命令行工具。
    COM 生命周期由 :mod:`sapi_runner` 管理：``init_com`` 幂等（每线程仅首次
    实际执行 ``CoInitialize``），QThreadPool 复用线程跨任务故 ``run()`` 不
    释放 COM——清理在线程退出时由 pythoncom atexit 钩子隐式完成。线程本地
    SpVoice 实例跨任务复用；当 ``SapiError`` 发生时调用
    ``invalidate_thread_voice`` 失效缓存实例，使下个任务重建 SpVoice。

    多格式输出：WAV 格式直接输出到文件；非 WAV 格式通过
    ``SpMemoryStream`` 合成到内存，再经 ffmpeg 管道转码，无临时文件。

    Attributes:
        input_file: 输入文本文件路径。
        config: SAPI5 配置。
        output_path: 输出音频文件路径。
        index: 任务在批次中的序号。
        output_format: 音频输出格式，默认 :attr:`AudioFormat.WAV`。
        ffmpeg_path: ffmpeg 路径（非 WAV 时使用）。
        process_priority: ffmpeg 子进程优先级（SAPI5 COM 无子进程），
            默认 ``None``（正常）。
        extra_encode_args: 额外的 ffmpeg 编码参数（如 VBR ``["-q:a", "2"]``），
            为 ``None`` 时使用格式默认参数（有损格式 320kbps CBR）。
    """

    def __init__(
        self,
        input_file: str,
        config: SapiConfig,
        output_path: str,
        index: int = 0,
        output_format: AudioFormat = AudioFormat.WAV,
        ffmpeg_path: str | None = None,
        process_priority: ProcessPriority | str | None = None,
        extra_encode_args: list[str] | None = None,
    ) -> None:
        super().__init__(input_file=input_file, output_path=output_path, index=index)
        self._config = config
        self._output_format = output_format
        self._ffmpeg_path = ffmpeg_path
        self._process_priority = process_priority
        self._extra_encode_args = extra_encode_args

    def _build_args(self) -> list[str]:
        """SAPI5 无命令行参数，返回空列表（仅满足基类抽象方法）。"""
        return []

    def _exec(self, args: list[str]) -> tuple[int, str, str]:
        """未使用（已覆写 :meth:`run`），直接返回未实现。"""
        return -1, "", "not implemented"

    def run(self) -> None:
        """QRunnable 入口：执行单个 SAPI5 合成任务。

        流程：
        1. 发射 ``started`` 信号
        2. ``init_com`` 初始化 COM（幂等：每线程首次实际初始化，后续空操作）
        3. 检查取消 → 读取文本 → 合成（WAV 直出 / 非 WAV 管道转码）
        4. 发射 ``finished`` 信号

        COM 不在 ``run()`` 中释放：QThreadPool 复用线程跨任务，COM 保持初始
        化状态供后续任务复用；线程退出时由 pythoncom atexit 钩子隐式清理。

        ``SapiError`` 时调用 ``invalidate_thread_voice`` 失效线程本地 SpVoice
        缓存（使下个任务重建实例），并发射 ``error`` 信号以返回码 -1 结束。
        未预期异常同样发射 ``error`` 信号。
        """
        start_time = time.time()
        filename = os.path.basename(self._input_file)

        self.signals.started.emit(filename)
        self.signals.log.emit(f"开始处理: {self._input_file}")

        try:
            # 初始化 COM（幂等：每线程首次调用时实际初始化，后续为空操作）
            init_com()

            # 检查取消
            if self._cancel_event.is_set():
                self.signals.finished.emit(filename, -1, "已取消", time.time() - start_time)
                return

            # 读取文本文件
            text = self._read_text_file()
            if not text.strip():
                self.signals.log.emit(f"文件为空: {filename}")
                self.signals.finished.emit(filename, 0, "", time.time() - start_time)
                return

            # 合成
            if self._output_format.is_wav:
                self._exec_wav(text, filename)
            else:
                self._exec_pipe(text, filename)

            elapsed = time.time() - start_time
            self.signals.finished.emit(filename, 0, "", elapsed)
            self.signals.log.emit(f"完成: {filename} 耗时={elapsed:.1f}s")

        except SapiError as e:
            # SpVoice 可能进入损坏状态，失效线程本地缓存使下个任务重建实例
            invalidate_thread_voice()
            elapsed = time.time() - start_time
            self.signals.error.emit(filename, str(e))
            self.signals.finished.emit(filename, -1, str(e), elapsed)
        except Exception as e:
            elapsed = time.time() - start_time
            self.signals.error.emit(filename, str(e))
            self.signals.finished.emit(filename, -1, str(e), elapsed)

    def _read_text_file(self) -> str:
        """使用 ``self._config.input_encoding`` 读取输入文本文件内容。"""
        with open(
            self._input_file, "r", encoding=self._config.input_encoding
        ) as f:
            return f.read()

    def _exec_wav(self, text: str, filename: str) -> None:
        """WAV 格式直接输出到文件。

        Args:
            text: 待合成文本。
            filename: 输入文件名（用于日志）。
        """
        self.signals.log.emit(f"SAPI5 合成 → {self._output_path}")
        synthesize_to_file(
            text=text,
            output_path=self._output_path,
            voice_name=self._config.voice_name,
            rate=self._config.rate,
            volume=self._config.volume,
            pitch=self._config.pitch,
            audio_format=self._config.audio_format,
            cancel_event=self._cancel_event,
        )

    def _exec_pipe(self, text: str, filename: str) -> None:
        """非 WAV 格式管道转码或降级文件转码。

        正常路径：合成到内存（SpMemoryStream）得到 WAV bytes，包装为
        :class:`io.BytesIO` 后传入 :func:`encode_audio_from_stream`，由 ffmpeg
        从 stdin 读取并转码，消除临时文件 I/O。

        降级路径：当文本字节数超过 :attr:`SapiConfig.max_text_bytes` 时，
        SpMemoryStream 在 12 并发下可能 OOM（1MB 文本可产生 50-100MB WAV），
        改用文件模式：``synthesize_to_file`` → 临时 WAV → ``encode_audio``
        转码 → 删除临时 WAV。

        Args:
            text: 待合成文本。
            filename: 输入文件名（用于日志）。
        """
        text_bytes = len(text.encode(self._config.input_encoding))
        if text_bytes > self._config.max_text_bytes:
            # 降级到文件模式：避免 SpMemoryStream 在大文本下 OOM
            self.signals.log.emit(
                f"文本大小 {text_bytes}B 超过阈值 {self._config.max_text_bytes}B，"
                f"降级到文件模式"
            )
            self._exec_pipe_via_file(text, filename)
            return
        # 正常管道模式：SpMemoryStream → ffmpeg stdin
        self.signals.log.emit(f"SAPI5 合成 → 内存 → ffmpeg → {self._output_path}")
        wav_bytes = synthesize_to_memory(
            text=text,
            voice_name=self._config.voice_name,
            rate=self._config.rate,
            volume=self._config.volume,
            pitch=self._config.pitch,
            audio_format=self._config.audio_format,
            cancel_event=self._cancel_event,
        )
        # encode_audio_from_stream 期望二进制输入流（启动 ffmpeg 后会关闭），
        # synthesize_to_memory 返回 bytes，需用 BytesIO 包装。
        encode_audio_from_stream(
            input_stream=io.BytesIO(wav_bytes),
            dst_path=self._output_path,
            fmt=self._output_format,
            ffmpeg_path=self._ffmpeg_path,
            extra_args=self._extra_encode_args,
            cancel_event=self._cancel_event,
            process_priority=self._process_priority,
        )

    def _temp_wav_path(self) -> str:
        """生成临时 WAV 文件路径（与最终输出同目录）。

        命名规则：``.{最终文件名}.tmp.wav``，位于同目录便于转码后原子性删除，
        避免跨盘移动开销。例如 ``output.mp3`` → ``.output.mp3.tmp.wav``。
        """
        directory = os.path.dirname(self._output_path) or "."
        filename = os.path.basename(self._output_path)
        return os.path.join(directory, f".{filename}.tmp.wav")

    def _exec_pipe_via_file(self, text: str, filename: str) -> None:
        """降级路径：合成到临时 WAV → ffmpeg 转码 → 删除临时 WAV。

        当文本字节数超过 :attr:`SapiConfig.max_text_bytes` 时，为避免
        SpMemoryStream 在大文本并发下 OOM，改走文件模式两阶段转码。

        Args:
            text: 待合成文本。
            filename: 输入文件名（用于日志）。

        Raises:
            SapiError: ffmpeg 转码失败（返回码非零）。
        """
        temp_wav = self._temp_wav_path()
        try:
            self.signals.log.emit(
                f"SAPI5 合成 → 临时 WAV → ffmpeg → {self._output_path}"
            )
            synthesize_to_file(
                text=text,
                output_path=temp_wav,
                voice_name=self._config.voice_name,
                rate=self._config.rate,
                volume=self._config.volume,
                pitch=self._config.pitch,
                audio_format=self._config.audio_format,
                cancel_event=self._cancel_event,
            )
            # 转码到最终格式
            enc_rc, _enc_stdout, enc_stderr = encode_audio(
                src_wav=temp_wav,
                dst_path=self._output_path,
                fmt=self._output_format,
                ffmpeg_path=self._ffmpeg_path,
                extra_args=self._extra_encode_args,
                cancel_event=self._cancel_event,
                process_priority=self._process_priority,
            )
            if enc_rc != 0:
                raise SapiError(
                    f"ffmpeg 转码失败（返回码 {enc_rc}）: "
                    f"{enc_stderr[:200] if enc_stderr else '无错误输出'}"
                )
        finally:
            # 删除临时 WAV（无论成功失败）
            if os.path.isfile(temp_wav):
                try:
                    os.remove(temp_wav)
                except OSError as exc:
                    logger.warning("删除临时 WAV 失败 %s: %s", temp_wav, exc)


__all__ = ["SapiTask"]
