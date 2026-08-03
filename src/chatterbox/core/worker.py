"""balcon 任务工作单元。

定义 :class:`BalconTask`，封装单个 balcon.exe 任务的执行逻辑，继承自
:class:`chatterbox.core.base_worker.BaseToolTask`，可由
:class:`PySide6.QtCore.QThreadPool` 调度到子线程运行。任务通过
:class:`chatterbox.utils.signals.TaskSignals` 向主线程报告状态
（开始/结束/日志/错误），并支持通过 :meth:`BalconTask.cancel` 安全取消
运行中的 balcon 子进程。

多格式输出支持：
- 当 ``output_format`` 为非 WAV 格式时，优先采用管道流式转码
  （balcon stdout → ffmpeg stdin），消除临时文件 I/O 开销
- 管道模式失败时自动回退到「balcon 输出临时 WAV → ffmpeg 转码 →
  删除临时 WAV」两阶段流程
- 临时 WAV 文件命名为 ``.<最终文件名>.tmp.wav``，位于最终输出同目录
- 转码失败时保留临时 WAV 便于诊断，发射 ``signals.error`` 信号
- ``output_format`` 与 ``ffmpeg_path`` 均有默认值，保持向后兼容
"""

from __future__ import annotations

import copy
import logging
import os
import subprocess

from chatterbox.core.audio_encoder import (
    AudioFormat,
    EncoderError,
    build_encode_args,
    build_encode_preview,
    encode_audio,
    encode_audio_from_stream,
)
from chatterbox.core.base_worker import BaseToolTask
from chatterbox.core.balcon_runner import (
    BalconError,
    build_command_preview,
    run_balcon,
    run_balcon_to_stream,
    terminate_balcon,
)
from chatterbox.core.config import BalconConfig
from chatterbox.core.tool_type import ProcessPriority

logger = logging.getLogger(__name__)


class BalconTask(BaseToolTask):
    """单个 balcon 任务的 QRunnable 工作单元。

    在子线程中调用 :func:`run_balcon` 执行 TTS 转换，通过 ``signals`` 报告
    进度与结果。可通过 :meth:`cancel` 取消运行中的子进程。

    多格式输出：当 ``output_format`` 非 WAV 时，优先使用管道流式转码
    （balcon stdout → ffmpeg stdin），失败时回退到临时文件模式。

    Attributes:
        input_file: 输入文件路径。
        config: balcon 配置（会被复制，``f_files``/``w_output`` 覆盖为本任务值）。
        output_path: 输出文件路径（扩展名应与 ``output_format`` 匹配）。
        balcon_path: balcon.exe 路径。
        index: 任务在批次中的序号（便于外部追踪）。
        signals: 任务信号对象。
        output_format: 音频输出格式，默认 :attr:`AudioFormat.WAV`（无需转码）。
        ffmpeg_path: ffmpeg 可执行文件路径，为 ``None`` 时自动查找。
            仅在 ``output_format`` 非 WAV 时使用。
        process_priority: 子进程优先级（balcon + ffmpeg），默认 ``None``（正常）。
        extra_encode_args: 额外的 ffmpeg 编码参数（如 VBR ``["-q:a", "2"]``），
            为 ``None`` 时使用格式默认参数（有损格式 320kbps CBR）。
    """

    def __init__(
        self,
        input_file: str,
        config: BalconConfig,
        output_path: str,
        balcon_path: str,
        index: int = 0,
        output_format: AudioFormat = AudioFormat.WAV,
        ffmpeg_path: str | None = None,
        process_priority: ProcessPriority | str | None = None,
        extra_encode_args: list[str] | None = None,
    ) -> None:
        super().__init__(input_file=input_file, output_path=output_path, index=index)
        self._config = config
        self._balcon_path = balcon_path
        # 多格式输出：默认 WAV 保持原行为
        self._output_format = output_format
        self._ffmpeg_path = ffmpeg_path
        self._process_priority = process_priority
        self._extra_encode_args = extra_encode_args

    def _build_args(self) -> list[str]:
        """复制配置并覆盖本任务相关字段，生成 balcon 命令行参数。

        多格式输出时，将 ``w_output`` 指向临时 WAV 路径（同目录下
        ``.<最终文件名>.tmp.wav``），balcon 完成后再由 :meth:`_exec` 转码。
        管道模式使用 :meth:`_build_pipe_args` 构建不同参数。
        """
        task_config = copy.copy(self._config)
        task_config.f_files = [self._input_file]

        if self._output_format.is_wav:
            # WAV 格式：balcon 直接输出到最终路径
            task_config.w_output = self._output_path
        else:
            # 非 WAV 格式：balcon 输出到临时 WAV，再由 ffmpeg 转码
            task_config.w_output = self._temp_wav_path()

        return task_config.to_args()

    def _build_pipe_args(self) -> list[str]:
        """构建管道模式参数（``-o`` 输出到 stdout，无 ``-w`` 输出文件）。

        管道模式下 balcon 通过 stdout 输出 WAV 二进制数据，由 ffmpeg
        通过 stdin 消费，消除临时文件 I/O。
        """
        task_config = copy.copy(self._config)
        task_config.f_files = [self._input_file]
        task_config.o_stdout = True  # 输出到 stdout
        task_config.w_output = None  # 不输出到文件
        return task_config.to_args()

    def _temp_wav_path(self) -> str:
        """生成临时 WAV 文件路径（与最终输出同目录）。

        命名规则：在最终文件名前加 ``.`` 前缀和 ``.tmp.wav`` 后缀，
        如 ``output.mp3`` → ``.output.mp3.tmp.wav``。位于同目录便于
        转码后原子性删除，避免跨盘移动开销。
        """
        directory = os.path.dirname(self._output_path) or "."
        filename = os.path.basename(self._output_path)
        return os.path.join(directory, f".{filename}.tmp.wav")

    def _exec(self, args: list[str]) -> tuple[int, str, str]:
        """执行 balcon 任务，非 WAV 格式优先使用管道流式转码。

        流程：
        1. WAV 格式：直接调用 ``run_balcon`` 输出到文件，无需转码
        2. 非 WAV 格式：优先尝试管道流式转码（``_exec_pipe``）
        3. 管道模式失败（非取消原因）时回退到临时文件模式（``_exec_file``）
        4. 取消导致的失败不回退，直接返回错误

        异常时发射 ``signals.error`` 信号并返回返回码 -1。
        """
        filename = os.path.basename(self._input_file)

        # WAV 格式：无需转码，直接执行 balcon（文件模式）
        if self._output_format.is_wav:
            self.signals.log.emit(
                f"命令行: {build_command_preview(self._balcon_path, args)}"
            )
            return self._exec_balcon_only(args, filename)

        # 非 WAV 格式：优先尝试管道流式转码
        try:
            return self._exec_pipe(filename)
        except Exception as exc:  # noqa: BLE001 - 管道模式任何异常均回退
            # 取消导致的失败不回退
            if self._cancel_event.is_set():
                self.signals.error.emit(filename, str(exc))
                return -1, "", str(exc)
            # 管道模式失败，回退到临时文件模式
            logger.warning("管道模式失败，回退到临时文件模式: %s", exc)
            self.signals.log.emit(f"管道模式失败，使用临时文件模式: {exc}")
            # 清理可能残留的输出文件（管道模式可能创建了不完整的文件）
            if os.path.isfile(self._output_path):
                try:
                    os.remove(self._output_path)
                except OSError:
                    pass
            # 回退到文件模式
            self.signals.log.emit(
                f"命令行: {build_command_preview(self._balcon_path, args)}"
            )
            return self._exec_file(args, filename)

    def _exec_balcon_only(
        self, args: list[str], filename: str
    ) -> tuple[int, str, str]:
        """WAV 格式：直接调用 balcon 输出到文件，不涉及转码。

        Args:
            args: balcon 命令行参数（含 ``-w output.wav``）。
            filename: 输入文件名（用于日志/信号）。

        Returns:
            ``(returncode, stdout, stderr)`` 元组。
        """
        returncode = 0
        stdout = ""
        stderr = ""
        try:
            returncode, stdout, stderr = run_balcon(
                self._balcon_path, args,
                cancel_event=self._cancel_event,
                process_priority=self._process_priority,
            )
        except BalconError as exc:
            self.signals.error.emit(filename, str(exc))
            returncode = -1
        except Exception as exc:  # noqa: BLE001 - 兜底，确保任务不卡死
            logger.exception("balcon 任务发生未预期异常: %s", self._input_file)
            self.signals.error.emit(filename, str(exc))
            returncode = -1
        return returncode, stdout, stderr

    def _exec_file(
        self, args: list[str], filename: str
    ) -> tuple[int, str, str]:
        """文件模式：balcon 输出临时 WAV → ffmpeg 转码 → 删除临时 WAV。

        这是管道模式失败时的回退路径，保持原有两阶段转码逻辑。

        Args:
            args: balcon 命令行参数（含 ``-w tempfile.wav``）。
            filename: 输入文件名（用于日志/信号）。

        Returns:
            ``(returncode, stdout, stderr)`` 元组。
        """
        returncode = 0
        stdout = ""
        stderr = ""
        try:
            returncode, stdout, stderr = run_balcon(
                self._balcon_path, args,
                cancel_event=self._cancel_event,
                process_priority=self._process_priority,
            )
        except BalconError as exc:
            self.signals.error.emit(filename, str(exc))
            returncode = -1
        except Exception as exc:  # noqa: BLE001
            logger.exception("balcon 任务发生未预期异常: %s", self._input_file)
            self.signals.error.emit(filename, str(exc))
            returncode = -1

        # balcon 失败或取消：不进入转码阶段
        if returncode != 0:
            return returncode, stdout, stderr

        # 非 WAV 格式：调用 ffmpeg 转码
        temp_wav = self._temp_wav_path()
        try:
            self._transcode(filename, temp_wav)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "ffmpeg 转码发生未预期异常: %s -> %s",
                temp_wav,
                self._output_path,
            )
            self.signals.error.emit(filename, f"转码失败: {exc}")
            returncode = -1

        return returncode, stdout, stderr

    def _exec_pipe(self, filename: str) -> tuple[int, str, str]:
        """管道流式转码：balcon stdout → ffmpeg stdin。

        消除临时文件 I/O 开销。balcon 通过 ``-o`` 输出 WAV 到 stdout，
        ffmpeg 通过 ``-i pipe:0`` 从 stdin 读取并转码。

        Args:
            filename: 输入文件名（用于日志/信号）。

        Returns:
            ``(returncode, stdout, stderr)`` 元组。

        Raises:
            BalconError: balcon 启动失败。
            EncoderError: ffmpeg 启动失败或被取消。
            Exception: 其他管道相关错误（触发回退）。
        """
        # 构建管道模式参数
        pipe_args = self._build_pipe_args()
        self.signals.log.emit(
            f"管道命令: {build_command_preview(self._balcon_path, pipe_args)}"
        )

        # 1. 启动 balcon（不等待，立即返回）
        balcon_proc, stderr_thread, stderr_chunks = run_balcon_to_stream(
            self._balcon_path, pipe_args,
            process_priority=self._process_priority,
        )

        # 2. 启动 ffmpeg，连接 balcon stdout → ffmpeg stdin
        # encode_audio_from_stream 会关闭 input_stream 并等待 ffmpeg 完成
        enc_rc, enc_stdout, enc_stderr = encode_audio_from_stream(
            input_stream=balcon_proc.stdout,
            dst_path=self._output_path,
            fmt=self._output_format,
            ffmpeg_path=self._ffmpeg_path,
            extra_args=self._extra_encode_args,
            cancel_event=self._cancel_event,
            process_priority=self._process_priority,
        )

        # 3. 等待 balcon 完成（ffmpeg 已消费完 stdout，balcon 应很快退出）
        try:
            balcon_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.warning("balcon 在管道转码后未退出，强制终止")
            terminate_balcon(balcon_proc)
            try:
                balcon_proc.wait(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass

        # 4. 收集 balcon stderr
        stderr_thread.join(timeout=2.0)
        balcon_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        # 5. 检查返回码
        if balcon_proc.returncode != 0:
            self.signals.error.emit(
                filename,
                f"balcon 流式输出失败（返回码 {balcon_proc.returncode}）: "
                f"{balcon_stderr[:200] if balcon_stderr else '无错误输出'}",
            )
            return balcon_proc.returncode or -1, "", balcon_stderr

        if enc_rc != 0:
            self.signals.error.emit(
                filename,
                f"ffmpeg 管道转码失败（返回码 {enc_rc}）: "
                f"{enc_stderr[:200] if enc_stderr else '无错误输出'}",
            )
            return enc_rc, enc_stdout, enc_stderr

        # 成功
        self.signals.log.emit(
            f"已管道转码为 {self._output_format.value.upper()}: {filename}"
        )
        return 0, enc_stdout, enc_stderr

    def _transcode(self, filename: str, temp_wav: str) -> None:
        """调用 ffmpeg 将临时 WAV 转码到最终输出路径。

        转码成功后删除临时 WAV；失败时保留临时文件便于诊断。

        Args:
            filename: 输入文件名（用于日志）。
            temp_wav: 临时 WAV 文件路径。

        Raises:
            EncoderError: ffmpeg 未找到、超时或被取消。
            Exception: ffmpeg 返回非零码（发射 error 信号后重新抛出）。
        """
        # 校验临时 WAV 存在
        if not os.path.isfile(temp_wav):
            self.signals.error.emit(
                filename,
                f"临时 WAV 文件不存在: {temp_wav}（balcon 可能未成功输出）",
            )
            return

        # 构建并预览 ffmpeg 命令行
        encode_args = build_encode_args(
            src_wav=temp_wav,
            dst_path=self._output_path,
            fmt=self._output_format,
            extra_args=self._extra_encode_args,
        )
        # 构建 ffmpeg 路径预览（用于日志，未校验）
        ffmpeg_preview_path = self._ffmpeg_path or "ffmpeg"
        self.signals.log.emit(
            f"转码命令: {build_encode_preview(ffmpeg_preview_path, encode_args)}"
        )

        # 调用 ffmpeg 转码
        enc_returncode, _enc_stdout, enc_stderr = encode_audio(
            src_wav=temp_wav,
            dst_path=self._output_path,
            fmt=self._output_format,
            ffmpeg_path=self._ffmpeg_path,
            extra_args=self._extra_encode_args,
            cancel_event=self._cancel_event,
            process_priority=self._process_priority,
        )

        if enc_returncode != 0:
            self.signals.error.emit(
                filename,
                f"ffmpeg 转码失败（返回码 {enc_returncode}）: "
                f"{enc_stderr[:200] if enc_stderr else '无错误输出'}",
            )
            return

        # 转码成功：删除临时 WAV
        try:
            os.remove(temp_wav)
            self.signals.log.emit(f"已转码为 {self._output_format.value.upper()}: {filename}")
        except OSError as exc:
            logger.warning("删除临时 WAV 失败 %s: %s", temp_wav, exc)


__all__ = ["BalconTask"]
