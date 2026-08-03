"""音频转码引擎模块。

提供基于 ffmpeg 的音频格式转码能力，将 balcon 输出的 WAV 文件转码为
MP3/OGG/AAC/FLAC/WMA 等格式。纯标准库实现，不依赖任何 GUI 库。

设计要点：
- :class:`AudioFormat` 枚举封装支持的格式，每种格式对应 ffmpeg 的编码器与扩展名
- :func:`find_ffmpeg` 按优先级查找 ffmpeg 可执行文件（环境变量 → PATH → 常见路径）
- :func:`encode_audio` 调用 ffmpeg 转码，支持取消与超时
- 转码失败时抛出 :class:`EncoderError`，由调用方决定错误处理
- 取消时安全终止 ffmpeg 子进程并抛出 :class:`EncoderError`

约束：
- 仅依赖 Python 标准库（subprocess、os、shutil、threading、time）
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from enum import Enum

from chatterbox.core.tool_type import ProcessPriority, priority_creationflags

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------
class EncoderError(Exception):
    """音频转码相关错误基类。"""


class EncoderNotFoundError(EncoderError):
    """ffmpeg 可执行文件未找到。"""


class EncoderExecutionError(EncoderError):
    """ffmpeg 执行失败（返回码非零）。

    携带 returncode / stderr 供调用方诊断。
    """

    def __init__(
        self,
        message: str,
        returncode: int,
        stderr: str,
        stdout: str,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


class EncoderTimeoutError(EncoderError):
    """ffmpeg 执行超时。"""


# ---------------------------------------------------------------------------
# 支持的音频格式
# ---------------------------------------------------------------------------
class AudioFormat(str, Enum):
    """支持的音频输出格式。

    每个枚举值对应：
    - ``extension``：文件扩展名（不含点，如 ``"mp3"``）
    - ``encoder``：ffmpeg 编码器名（如 ``"libmp3lame"``）
    - ``is_wav``：是否为 WAV 格式（无需转码）
    """

    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    AAC = "aac"
    FLAC = "flac"
    WMA = "wma"

    @property
    def extension(self) -> str:
        """文件扩展名（不含点）。"""
        return self.value

    @property
    def encoder(self) -> str:
        """ffmpeg 编码器名。

        WAV 使用 ``pcm_s16le``（与 balcon 默认输出一致），
        其他格式使用对应的标准编码器。
        """
        _ENCODERS: dict[str, str] = {
            "wav": "pcm_s16le",
            "mp3": "libmp3lame",
            "ogg": "libvorbis",
            "aac": "aac",
            "flac": "flac",
            "wma": "wmav2",
        }
        return _ENCODERS[self.value]

    def best_encoder(self, available_encoders: set[str] | None = None) -> str:
        """按优先级选择最佳可用编码器。

        当 ``available_encoders`` 为 ``None`` 时回退到默认编码器
        （:attr:`encoder`）。否则按 :data:`_ENCODER_PRIORITY` 中的
        优先级顺序查找首个可用的高性能编码器。

        例如 AAC 格式优先使用 ``libfdk_aac``（高质量），回退到 ``aac``
        （内置）；MP3 优先使用 ``libmp3lame``（标准），回退到 ``mp3_mf``
        （Media Foundation）。

        Args:
            available_encoders: ffmpeg 编译时包含的编码器名称集合，
                为 ``None`` 时直接返回默认编码器。

        Returns:
            最佳可用编码器名称。无匹配时回退到 :attr:`encoder`。
        """
        if available_encoders is None:
            return self.encoder
        for enc in _ENCODER_PRIORITY.get(self.value, [self.encoder]):
            if enc in available_encoders:
                return enc
        return self.encoder

    @property
    def is_wav(self) -> bool:
        """是否为 WAV 格式（无需转码）。"""
        return self is AudioFormat.WAV

    @property
    def needs_ffmpeg(self) -> bool:
        """是否需要 ffmpeg 转码（非 WAV 格式）。"""
        return not self.is_wav

    @property
    def is_lossless(self) -> bool:
        """是否为无损格式（WAV/FLAC，无需指定比特率）。"""
        return self in (AudioFormat.WAV, AudioFormat.FLAC)

    @property
    def is_lossy(self) -> bool:
        """是否为有损格式（MP3/OGG/AAC/WMA，需要指定比特率保证音质）。"""
        return not self.is_lossless

    @property
    def default_extra_args(self) -> list[str]:
        """各格式的默认质量参数，保证音质不低于 320kbps 等效质量。

        - WAV/FLAC：无损，无需参数
        - MP3：``-b:a 320k``（CBR 320kbps，MP3 最高比特率）
        - AAC：``-b:a 320k``（AAC 320kbps，接近透明）
        - WMA：``-b:a 320k``（WMA 320kbps）
        - OGG：``-q:a 10``（Vorbis 质量 10，约 500kbps，远超 320kbps）
        """
        if self.is_lossless:
            return []
        if self is AudioFormat.OGG:
            # Vorbis 质量等级 10 约为 500kbps，远超 320kbps
            return ["-q:a", "10"]
        # MP3/AAC/WMA 使用 320kbps CBR
        return ["-b:a", "320k"]

    @classmethod
    def from_extension(cls, ext: str) -> AudioFormat:
        """根据文件扩展名推断格式。

        Args:
            ext: 扩展名（含点或不含点，大小写不敏感，如 ``".mp3"`` 或 ``"mp3"``）。

        Returns:
            对应的 :class:`AudioFormat`，未知扩展名返回 :attr:`AudioFormat.WAV`。
        """
        normalized = ext.lstrip(".").lower()
        for fmt in cls:
            if fmt.extension == normalized:
                return fmt
        return cls.WAV


# 编码器优先级：每种格式按质量/性能从高到低排列
# best_encoder() 按此顺序在 ffmpeg 可用编码器集合中查找首个匹配
_ENCODER_PRIORITY: dict[str, list[str]] = {
    "wav": ["pcm_s16le"],
    "mp3": ["libmp3lame", "mp3_mf", "mp3float"],
    "ogg": ["libvorbis", "vorbis"],
    "aac": ["libfdk_aac", "aac", "libfaac"],
    "flac": ["flac"],
    "wma": ["wmav2", "wmav1"],
}


# ---------------------------------------------------------------------------
# ffmpeg 查找
# ---------------------------------------------------------------------------
# 环境变量名：用户可通过它指定 ffmpeg 路径
FFMPEG_ENV_VAR = "BALCON_BATCH_FFMPEG_PATH"

# Windows 下常见的 ffmpeg 安装路径（按优先级排序）
_WINDOWS_FFMPEG_CANDIDATES: list[str] = [
    # 用户配置目录
    os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffmpeg.exe"),
    # Program Files
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    # Chocolatey 默认安装路径
    r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
]

# ffmpeg 子进程默认超时（秒），None 表示无超时
_DEFAULT_TIMEOUT: float | None = None

# ffmpeg 路径校验缓存：{输入路径: 校验结果(abs path) or None(未找到)}
# 避免每次转码重复 os.path.isfile + abspath 调用
_ffmpeg_path_cache: dict[str, str | None] = {}


def find_ffmpeg() -> str | None:
    """查找 ffmpeg 可执行文件路径。

    查找优先级：
    1. 环境变量 :data:`FFMPEG_ENV_VAR` 指定的路径
    2. ``shutil.which("ffmpeg")`` 在 PATH 中查找
    3. Windows 下常见安装路径（:data:`_WINDOWS_FFMPEG_CANDIDATES`）

    Returns:
        ffmpeg 可执行文件的绝对路径，未找到返回 ``None``。
    """
    # 1. 环境变量
    env_path = os.environ.get(FFMPEG_ENV_VAR, "").strip()
    if env_path and os.path.isfile(env_path):
        return os.path.abspath(env_path)

    # 2. PATH 中查找
    which_path = shutil.which("ffmpeg")
    if which_path:
        return os.path.abspath(which_path)

    # 3. Windows 常见路径
    if os.name == "nt":
        for candidate in _WINDOWS_FFMPEG_CANDIDATES:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

    return None


def validate_ffmpeg(ffmpeg_path: str | None) -> str:
    """校验 ffmpeg 路径有效，返回规范化的绝对路径。

    结果按输入路径缓存到 :data:`_ffmpeg_path_cache`，避免每次转码
    重复 ``os.path.isfile`` + ``os.path.abspath`` 调用。缓存可通过
    :func:`clear_ffmpeg_cache` 清除（批次结束或 ffmpeg 路径变更时）。

    Args:
        ffmpeg_path: ffmpeg 可执行文件路径，为 ``None`` 时调用 :func:`find_ffmpeg`。

    Returns:
        规范化的绝对路径。

    Raises:
        EncoderNotFoundError: 路径无效或未找到 ffmpeg。
    """
    cache_key = ffmpeg_path or ""
    if cache_key in _ffmpeg_path_cache:
        cached = _ffmpeg_path_cache[cache_key]
        if cached is None:
            raise EncoderNotFoundError(
                "未找到 ffmpeg 可执行文件。请通过环境变量 "
                f"{FFMPEG_ENV_VAR} 指定路径，或将 ffmpeg 添加到 PATH。"
            )
        return cached

    # 未缓存，执行校验
    if ffmpeg_path is None or not ffmpeg_path.strip():
        found = find_ffmpeg()
        if found is None:
            _ffmpeg_path_cache[cache_key] = None
            raise EncoderNotFoundError(
                "未找到 ffmpeg 可执行文件。请通过环境变量 "
                f"{FFMPEG_ENV_VAR} 指定路径，或将 ffmpeg 添加到 PATH。"
            )
        _ffmpeg_path_cache[cache_key] = found
        return found

    if not os.path.isfile(ffmpeg_path):
        _ffmpeg_path_cache[cache_key] = None
        raise EncoderNotFoundError(f"ffmpeg 路径无效或不是文件: {ffmpeg_path}")
    resolved = os.path.abspath(ffmpeg_path)
    _ffmpeg_path_cache[cache_key] = resolved
    return resolved


def clear_ffmpeg_cache() -> None:
    """清除 ffmpeg 路径缓存和编码器检测缓存。

    应在以下场景调用：
    - 批次结束时（避免长时间运行后缓存过期）
    - ffmpeg 路径变更时（用户切换了 ffmpeg 路径）
    - 测试间隔离（避免缓存污染）
    """
    _ffmpeg_path_cache.clear()
    EncoderDetector.clear_cache()


# ---------------------------------------------------------------------------
# 编码器检测
# ---------------------------------------------------------------------------
class EncoderDetector:
    """检测 ffmpeg 编译时包含的可用编码器。

    执行 ``ffmpeg -hide_banner -encoders`` 解析输出文本，提取可用编码器
    名称集合。结果按 ffmpeg 路径缓存，避免重复调用。

    用于 :meth:`AudioFormat.best_encoder` 按优先级选择高性能编码器
    （如 ``libfdk_aac`` 优于内置 ``aac``）。
    """

    _cache: dict[str, set[str]] = {}

    @classmethod
    def detect(cls, ffmpeg_path: str) -> set[str]:
        """检测指定 ffmpeg 可执行文件的可用编码器集合。

        Args:
            ffmpeg_path: ffmpeg 可执行文件绝对路径。

        Returns:
            可用编码器名称集合（如 ``{"libmp3lame", "aac", "libfdk_aac"}``）。
            检测失败返回空集合（回退到默认编码器）。
        """
        if ffmpeg_path in cls._cache:
            return cls._cache[ffmpeg_path]

        encoders: set[str] = set()
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
                creationflags=_creationflags(),
            )
            # ffmpeg -encoders 输出格式示例：
            # " A..... libmp3lame         MP3 (MPEG audio layer 3)"
            # " V..... libx264            H.264 / AVC ..."
            # 第一个字符是类型（V=视频, A=音频, S=字幕），后续是标志位
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if len(stripped) < 8:
                    continue
                # 编码器行格式：类型标志 编码器名 描述
                # 如 "A..... libmp3lame  MP3 (MPEG audio layer 3)"
                if stripped[0] in ("V", "A", "S"):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        encoders.add(parts[1])
        except Exception as exc:  # noqa: BLE001
            logger.debug("编码器检测失败 %s: %s", ffmpeg_path, exc)

        cls._cache[ffmpeg_path] = encoders
        return encoders

    @classmethod
    def clear_cache(cls) -> None:
        """清除所有 ffmpeg 路径的编码器检测缓存。"""
        cls._cache.clear()


def _creationflags() -> int:
    """返回 Windows 下抑制控制台窗口的 creationflags，非 Windows 返回 0。"""
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _read_pipe(pipe, buffer: list, encoding: str = "utf-8") -> None:
    """在守护线程中持续读取管道内容，累积到 ``buffer`` 列表。

    当 ``pipe.read()`` 返回空（EOF）时退出，捕获 ``OSError`` / ``ValueError``
    以处理管道已被关闭的情况。避免子进程输出超过 64KB 管道缓冲区时死锁。
    """
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            buffer.append(chunk)
    except (OSError, ValueError):
        pass  # 管道已关闭


def _close_pipes(process: subprocess.Popen) -> None:
    """关闭子进程的 stdout/stderr 管道，确保读取线程能退出。"""
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 转码执行
# ---------------------------------------------------------------------------
def build_encode_args(
    src_wav: str,
    dst_path: str,
    fmt: AudioFormat,
    extra_args: list[str] | None = None,
    encoder: str | None = None,
) -> list[str]:
    """构建 ffmpeg 转码命令行参数（不含 ffmpeg 可执行文件路径本身）。

    音质保障：当 ``extra_args`` 为 ``None`` 时，自动应用 ``fmt.default_extra_args``
    （有损格式默认 320kbps 或等效质量，避免音质极差问题）。显式传入
    ``extra_args``（包括空列表 ``[]``）时使用用户指定的参数。

    参数注入防护：在输出路径前插入 ``--`` 分隔符，告诉 ffmpeg 后续参数
    均为位置参数（非选项）。若 ``src_wav`` 或 ``dst_path`` 以 ``-`` 开头
    （如恶意文件名 ``-loglevel``），ffmpeg 会将其误解析为选项而非文件路径，
    可能导致任意参数注入。``-i src_wav`` 中的 ``src_wav`` 已作为 ``-i``
    的值传递（安全），但 ``dst_path`` 作为裸位置参数需要 ``--`` 保护。

    Args:
        src_wav: 源 WAV 文件路径。
        dst_path: 目标文件路径。
        fmt: 目标音频格式。
        extra_args: 额外的 ffmpeg 参数（如比特率 ``["-b:a", "192k"]``），
            插入在编码器指定之前。为 ``None`` 时自动应用默认质量参数
            （有损格式 320kbps 等效）。
        encoder: 编码器名称，为 ``None`` 时使用 ``fmt.encoder``。
            传入 :meth:`AudioFormat.best_encoder` 的结果可选择高性能编码器。

    Returns:
        ffmpeg 参数列表，如 ``["-y", "-i", "src.wav", "-b:a", "320k",
        "-c:a", "libmp3lame", "--", "dst.mp3"]``。
    """
    args: list[str] = ["-y", "-i", src_wav]
    # 音质保障：未指定 extra_args 时使用默认质量参数（不低于 320kbps）
    effective_args = extra_args if extra_args is not None else fmt.default_extra_args
    if effective_args:
        args.extend(effective_args)
    effective_encoder = encoder if encoder is not None else fmt.encoder
    args.extend(["-c:a", effective_encoder])
    # -- 分隔符：阻止 dst_path 被解析为选项（参数注入防护）
    args.append("--")
    args.append(dst_path)
    return args


def build_encode_stream_args(
    dst_path: str,
    fmt: AudioFormat,
    extra_args: list[str] | None = None,
    encoder: str | None = None,
) -> list[str]:
    """构建 ffmpeg 从 stdin 读取 WAV 流的转码参数。

    与 :func:`build_encode_args` 类似，但使用 ``pipe:0`` 作为输入源
    （ffmpeg 从 stdin 读取二进制 WAV 流），用于管道流式转码。

    参数注入防护：在输出路径前插入 ``--`` 分隔符，防止 ``dst_path``
    以 ``-`` 开头时被 ffmpeg 误解析为选项。详见 :func:`build_encode_args`。

    Args:
        dst_path: 目标文件路径。
        fmt: 目标音频格式。
        extra_args: 额外的 ffmpeg 参数，为 ``None`` 时自动应用默认质量参数。
        encoder: 编码器名称，为 ``None`` 时使用 ``fmt.encoder``。

    Returns:
        ffmpeg 参数列表，如 ``["-y", "-i", "pipe:0", "-b:a", "320k",
        "-c:a", "libmp3lame", "--", "dst.mp3"]``。
    """
    args: list[str] = ["-y", "-i", "pipe:0"]
    effective_args = extra_args if extra_args is not None else fmt.default_extra_args
    if effective_args:
        args.extend(effective_args)
    effective_encoder = encoder if encoder is not None else fmt.encoder
    args.extend(["-c:a", effective_encoder])
    # -- 分隔符：阻止 dst_path 被解析为选项（参数注入防护）
    args.append("--")
    args.append(dst_path)
    return args


def build_encode_preview(
    ffmpeg_path: str, args: list[str]
) -> str:
    """构建可读的 ffmpeg 命令行字符串，路径或参数含空格时加双引号。"""
    parts: list[str] = []
    if " " in ffmpeg_path:
        parts.append(f'"{ffmpeg_path}"')
    else:
        parts.append(ffmpeg_path)
    for arg in args:
        if " " in arg:
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
    return " ".join(parts)


def terminate_ffmpeg(process: subprocess.Popen) -> None:
    """安全终止 ffmpeg 子进程：先 terminate，等待 1 秒仍存活则 kill。

    三段式取消清理：``terminate()`` → ``wait(1.0)`` → ``kill()``。
    捕获并记录所有异常（进程已结束等情况），不向调用方抛出。
    """
    try:
        process.terminate()
    except Exception as exc:  # noqa: BLE001
        logger.debug("terminate ffmpeg 进程时异常: %s", exc)

    try:
        process.wait(timeout=1.0)
        return
    except subprocess.TimeoutExpired:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("等待 ffmpeg 进程终止时异常: %s", exc)
        return

    try:
        process.kill()
    except Exception as exc:  # noqa: BLE001
        logger.debug("kill ffmpeg 进程时异常: %s", exc)

    try:
        process.wait(timeout=2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffmpeg 进程 kill 后仍未结束: pid=%s, 异常=%s", process.pid, exc)


def encode_audio(
    src_wav: str,
    dst_path: str,
    fmt: AudioFormat,
    ffmpeg_path: str | None = None,
    extra_args: list[str] | None = None,
    timeout: float | None = _DEFAULT_TIMEOUT,
    cancel_event: threading.Event | None = None,
    process_priority: ProcessPriority | str | None = None,
) -> tuple[int, str, str]:
    """调用 ffmpeg 将 WAV 文件转码为目标格式。

    Args:
        src_wav: 源 WAV 文件路径。
        dst_path: 目标文件路径（扩展名应与 ``fmt`` 匹配）。
        fmt: 目标音频格式（WAV 时直接调用 ffmpeg 重编码，通常无必要）。
        ffmpeg_path: ffmpeg 可执行文件路径，为 ``None`` 时自动查找。
        extra_args: 额外的 ffmpeg 参数（如比特率）。
        timeout: 超时秒数，``None`` 表示无超时。
        cancel_event: 取消事件，设置时安全终止 ffmpeg 并抛出 :class:`EncoderError`。
        process_priority: ffmpeg 子进程优先级，``None`` 时使用默认（正常）。

    Returns:
        ``(returncode, stdout, stderr)`` 元组。返回码非零不抛异常，仅记录 warning，
        由调用方决定如何处理。

    Raises:
        EncoderNotFoundError: ffmpeg 未找到。
        EncoderTimeoutError: 执行超时。
        EncoderError: 任务被取消。
    """
    resolved_path = validate_ffmpeg(ffmpeg_path)
    available_encoders = EncoderDetector.detect(resolved_path)
    selected_encoder = fmt.best_encoder(available_encoders)
    args = build_encode_args(src_wav, dst_path, fmt, extra_args, encoder=selected_encoder)

    logger.debug(
        "ffmpeg 转码: %s -> %s (%s, encoder=%s)",
        src_wav,
        dst_path,
        fmt.value,
        selected_encoder,
    )

    process = subprocess.Popen(
        [resolved_path] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=priority_creationflags(process_priority),
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    start_time = time.monotonic()
    try:
        while True:
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_event is not None and cancel_event.is_set():
                raise EncoderError("转码任务已取消")
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                raise EncoderTimeoutError(f"ffmpeg 执行超时: {timeout}秒")
    except Exception:
        terminate_ffmpeg(process)
        _close_pipes(process)
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        raise

    # 进程已退出，join 读取线程以获取完整输出
    stdout_thread.join(timeout=2.0)
    stderr_thread.join(timeout=2.0)

    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)

    if process.returncode != 0:
        logger.warning(
            "ffmpeg 转码返回非零码: returncode=%s, src=%s, dst=%s, stderr=%s",
            process.returncode,
            src_wav,
            dst_path,
            stderr,
        )
    return process.returncode, stdout, stderr


def encode_audio_from_stream(
    input_stream,
    dst_path: str,
    fmt: AudioFormat,
    ffmpeg_path: str | None = None,
    extra_args: list[str] | None = None,
    timeout: float | None = _DEFAULT_TIMEOUT,
    cancel_event: threading.Event | None = None,
    process_priority: ProcessPriority | str | None = None,
) -> tuple[int, str, str]:
    """调用 ffmpeg 从输入流（stdin）读取 WAV 数据并转码为目标格式。

    用于管道流式转码：balcon 的 stdout 直接连接到 ffmpeg 的 stdin，
    消除临时文件 I/O 开销。``input_stream`` 必须是二进制模式（如
    :func:`run_balcon_to_stream` 返回的 ``process.stdout``）。

    本函数在启动 ffmpeg 后会立即关闭 ``input_stream`` 的父进程引用——
    ffmpeg 子进程已有自己的文件描述符副本，关闭父进程引用后 ffmpeg
    仍能正常读取。这确保当上游（balcon）关闭写端时 ffmpeg 能检测到 EOF。

    Args:
        input_stream: 二进制输入流（如 balcon 进程的 stdout），必须是
            二进制模式。本函数会在启动 ffmpeg 后关闭此流。
        dst_path: 目标文件路径（扩展名应与 ``fmt`` 匹配）。
        fmt: 目标音频格式。
        ffmpeg_path: ffmpeg 可执行文件路径，为 ``None`` 时自动查找。
        extra_args: 额外的 ffmpeg 参数（如比特率）。
        timeout: 超时秒数，``None`` 表示无超时。
        cancel_event: 取消事件，设置时安全终止 ffmpeg 并抛出
            :class:`EncoderError`。
        process_priority: ffmpeg 子进程优先级，``None`` 时使用默认（正常）。

    Returns:
        ``(returncode, stdout, stderr)`` 元组。返回码非零不抛异常，仅记录
        warning，由调用方决定如何处理。

    Raises:
        EncoderNotFoundError: ffmpeg 未找到。
        EncoderTimeoutError: 执行超时。
        EncoderError: 任务被取消。
    """
    resolved_path = validate_ffmpeg(ffmpeg_path)
    available_encoders = EncoderDetector.detect(resolved_path)
    selected_encoder = fmt.best_encoder(available_encoders)
    args = build_encode_stream_args(dst_path, fmt, extra_args, encoder=selected_encoder)

    logger.debug(
        "ffmpeg 管道转码: stdin -> %s (%s, encoder=%s)",
        dst_path,
        fmt.value,
        selected_encoder,
    )

    # ffmpeg stdout/stderr 用 text 模式（进度/错误信息），stdin 为二进制
    # subprocess.Popen 传入 stdin=file_object 时，text=True 只影响 stdout/stderr
    process = subprocess.Popen(
        [resolved_path] + args,
        stdin=input_stream,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=priority_creationflags(process_priority),
    )

    # 关闭父进程对 input_stream 的引用，使 ffmpeg 成为唯一读取者
    # 这样上游关闭写端时 ffmpeg 能检测到 EOF
    # 注意：ffmpeg 子进程已有独立的文件描述符副本，不受此关闭影响
    try:
        input_stream.close()
    except (OSError, ValueError):
        pass

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    start_time = time.monotonic()
    try:
        while True:
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_event is not None and cancel_event.is_set():
                raise EncoderError("管道转码任务已取消")
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                raise EncoderTimeoutError(f"ffmpeg 管道转码超时: {timeout}秒")
    except Exception:
        terminate_ffmpeg(process)
        _close_pipes(process)
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        raise

    # 进程已退出，join 读取线程以获取完整输出
    stdout_thread.join(timeout=2.0)
    stderr_thread.join(timeout=2.0)

    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)

    if process.returncode != 0:
        logger.warning(
            "ffmpeg 管道转码返回非零码: returncode=%s, dst=%s, stderr=%s",
            process.returncode,
            dst_path,
            stderr,
        )
    return process.returncode, stdout, stderr


__all__ = [
    "AudioFormat",
    "EncoderDetector",
    "EncoderError",
    "EncoderNotFoundError",
    "EncoderExecutionError",
    "EncoderTimeoutError",
    "FFMPEG_ENV_VAR",
    "build_encode_args",
    "build_encode_stream_args",
    "build_encode_preview",
    "clear_ffmpeg_cache",
    "encode_audio",
    "encode_audio_from_stream",
    "find_ffmpeg",
    "terminate_ffmpeg",
    "validate_ffmpeg",
]
