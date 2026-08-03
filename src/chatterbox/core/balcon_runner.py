"""balcon.exe 子进程封装模块。

提供 balcon.exe 的路径校验、语音/设备列举、命令执行与安全终止等能力。
纯标准库实现，不依赖任何 GUI 库，可在无界面环境下独立测试。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time

from chatterbox.core.tool_type import ProcessPriority, priority_creationflags

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------
class BalconError(Exception):
    """balcon 相关错误基类。"""


class BalconNotFoundError(BalconError):
    """balcon.exe 未找到。"""


class BalconExecutionError(BalconError):
    """balcon 执行失败（返回码非零）。

    携带 returncode / stdout / stderr 供调用方诊断。
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


class BalconTimeoutError(BalconError):
    """balcon 执行超时。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _validate_balcon_path(balcon_path: str) -> str:
    """校验 balcon.exe 路径存在且是有效的 Win32 可执行文件，返回规范化的绝对路径。

    除了检查文件存在外，还读取前 2 字节验证 MZ 魔数（0x4D 0x5A），
    这是所有 Windows PE 可执行文件的起始签名。以此拒绝 .lnk 快捷方式、
    文本文件、DLL 等无法直接执行的文件，避免后续 subprocess 调用抛出
    WinError 193（"不是有效的 Win32 应用程序"）。
    """
    if not os.path.isfile(balcon_path):
        raise BalconNotFoundError(f"balcon.exe 未找到: {balcon_path}")
    abs_path = os.path.abspath(balcon_path)
    try:
        with open(abs_path, "rb") as f:
            magic = f.read(2)
    except OSError as exc:
        raise BalconNotFoundError(f"balcon.exe 无法读取: {abs_path}: {exc}") from exc
    if magic != b"MZ":
        raise BalconNotFoundError(
            f"balcon.exe 不是有效的 Win32 可执行文件（缺少 MZ 头）: {abs_path}"
        )
    return abs_path


def _creationflags() -> int:
    """返回 Windows 下抑制控制台窗口的 creationflags，非 Windows 返回 0。"""
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _wrap_subprocess_error(exc: OSError, path: str) -> BalconError:
    """将 subprocess 启动时的 OSError 转换为更清晰的 BalconError。

    WinError 193 (ERROR_BAD_EXE_FORMAT) 表示文件虽有 MZ 头但不是有效的
    Win32 应用程序——常见于 16 位 DOS 程序、架构不匹配（如 ARM exe 在
    x64 系统上无仿真层）、或文件损坏。给出明确提示而非原始系统错误。
    """
    winerror = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    if winerror == 193:
        return BalconError(
            f"无法启动 balcon.exe——不是有效的 Win32 应用程序（架构不匹配或文件损坏）: {path}"
        )
    return BalconError(f"启动 balcon.exe 失败: {path}: {exc}")


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
# 列举语音 / 设备
# ---------------------------------------------------------------------------
def list_voices(balcon_path: str, timeout: float = 30.0) -> list[str]:
    """调用 ``balcon.exe -l`` 列举可用语音名。"""
    path = _validate_balcon_path(balcon_path)
    try:
        result = subprocess.run(
            [path, "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_creationflags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise BalconTimeoutError(f"balcon -l 执行超时: {timeout}秒") from exc
    except OSError as exc:
        raise _wrap_subprocess_error(exc, path) from exc

    if result.returncode != 0:
        raise BalconExecutionError(
            f"balcon -l 执行失败，返回码: {result.returncode}",
            returncode=result.returncode,
            stderr=result.stderr,
            stdout=result.stdout,
        )

    voices: list[str] = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if name:
            voices.append(name)
    return voices


_DEVICE_RE = re.compile(r"^(\d+)\s*[:：]\s*(.+)$")


def list_devices(balcon_path: str, timeout: float = 30.0) -> list[tuple[int, str]]:
    """调用 ``balcon.exe -g`` 列举输出设备，返回 ``(index, name)`` 列表。"""
    path = _validate_balcon_path(balcon_path)
    try:
        result = subprocess.run(
            [path, "-g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_creationflags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise BalconTimeoutError(f"balcon -g 执行超时: {timeout}秒") from exc
    except OSError as exc:
        raise _wrap_subprocess_error(exc, path) from exc

    if result.returncode != 0:
        raise BalconExecutionError(
            f"balcon -g 执行失败，返回码: {result.returncode}",
            returncode=result.returncode,
            stderr=result.stderr,
            stdout=result.stdout,
        )

    devices: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        match = _DEVICE_RE.match(line.strip())
        if match:
            devices.append((int(match.group(1)), match.group(2).strip()))
    return devices


# ---------------------------------------------------------------------------
# 通用执行
# ---------------------------------------------------------------------------
def run_balcon(
    balcon_path: str,
    args: list[str],
    timeout: float | None = None,
    cancel_event: threading.Event | None = None,
    process_priority: ProcessPriority | str | None = None,
) -> tuple[int, str, str]:
    """启动 balcon.exe 并轮询其状态，支持取消与超时。

    返回 ``(returncode, stdout, stderr)``。返回码非零不抛异常，仅记录 warning，
    由调用方决定如何处理。取消时抛 :class:`BalconError`，超时抛
    :class:`BalconTimeoutError`。

    使用守护线程读取 stdout/stderr 管道，避免子进程输出超过 64KB
    管道缓冲区时死锁。主循环以 ``process.wait(timeout=0.1)`` 轮询，
    在 timeout 异常时检查 ``cancel_event`` 与超时条件。

    Args:
        balcon_path: balcon.exe 路径。
        args: balcon 命令行参数。
        timeout: 超时秒数，``None`` 表示无超时。
        cancel_event: 取消事件，设置时安全终止 balcon 并抛异常。
        process_priority: 子进程优先级，``None`` 时使用默认（正常）。
    """
    path = _validate_balcon_path(balcon_path)
    try:
        process = subprocess.Popen(
            [path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=priority_creationflags(process_priority),
        )
    except OSError as exc:
        raise _wrap_subprocess_error(exc, path) from exc

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
                raise BalconError("任务已取消")
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                raise BalconTimeoutError(f"balcon 执行超时: {timeout}秒")
    except Exception:
        terminate_balcon(process)
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
            "balcon 执行返回非零码: returncode=%s, args=%s, stderr=%s",
            process.returncode,
            args,
            stderr,
        )
    return process.returncode, stdout, stderr


def _read_pipe_binary(pipe, buffer: list[bytes]) -> None:
    """在守护线程中持续读取二进制管道内容，累积到 ``buffer`` 列表。

    与 :func:`_read_pipe` 类似，但显式处理 bytes 类型。用于 balcon stdout
    输出 WAV 二进制数据时避免 text 模式破坏数据。
    """
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            buffer.append(chunk)
    except (OSError, ValueError):
        pass  # 管道已关闭


def run_balcon_to_stream(
    balcon_path: str,
    args: list[str],
    process_priority: ProcessPriority | str | None = None,
) -> tuple[subprocess.Popen, threading.Thread, list[bytes]]:
    """启动 balcon.exe 输出 WAV 到 stdout，立即返回供管道连接。

    与 :func:`run_balcon` 不同，本函数**不等待** balcon 退出——因为
    stdout 数据需要由下游 ffmpeg 持续消费，否则 balcon 会在 OS 管道
    缓冲区（通常 64KB）满时阻塞，造成死锁。

    stdout 以二进制模式打开（WAV 是二进制数据，text 模式会破坏）。
    stderr 由守护线程读取并累积到返回的 ``stderr_chunks`` 列表中，
    调用方在 ``process.wait()`` 后 join 线程并解码。

    调用方典型用法::

        proc, stderr_thread, stderr_chunks = run_balcon_to_stream(path, args)
        # 将 proc.stdout 传给 ffmpeg 的 stdin
        encode_audio_from_stream(proc.stdout, dst, fmt, ...)
        # 等待 balcon 退出
        proc.wait(timeout=5.0)
        stderr_thread.join(timeout=2.0)
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

    调用方需在 ``args`` 中包含 ``-o -`` 选项（balcon 输出到 stdout）。

    Args:
        balcon_path: balcon.exe 路径。
        args: balcon 命令行参数（应包含 ``-o -`` 选项）。
        process_priority: 子进程优先级，``None`` 时使用默认（正常）。

    Returns:
        ``(process, stderr_thread, stderr_chunks)`` 元组：
        - ``process``: 已启动但可能未退出的 :class:`subprocess.Popen`
        - ``stderr_thread``: 正在读取 stderr 的守护线程
        - ``stderr_chunks``: 累积 stderr 二进制块的列表，join 线程后
          ``b"".join(chunks).decode("utf-8", errors="replace")`` 获取文本
    """
    path = _validate_balcon_path(balcon_path)
    # stdout 二进制模式（WAV 数据），stderr 也以二进制读取后手动解码
    try:
        process = subprocess.Popen(
            [path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=priority_creationflags(process_priority),
        )
    except OSError as exc:
        raise _wrap_subprocess_error(exc, path) from exc

    stderr_chunks: list[bytes] = []
    stderr_thread = threading.Thread(
        target=_read_pipe_binary,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stderr_thread.start()

    return process, stderr_thread, stderr_chunks


def terminate_balcon(process: subprocess.Popen) -> None:
    """安全终止 balcon 子进程：先 terminate，等待 1 秒仍存活则 kill。

    三段式取消清理：``terminate()`` → ``wait(1.0)`` → ``kill()``。
    捕获并记录所有异常（进程已结束等情况），不向调用方抛出。
    """
    try:
        process.terminate()
    except Exception as exc:  # noqa: BLE001 - 进程已结束等情况
        logger.debug("terminate balcon 进程时异常: %s", exc)

    try:
        process.wait(timeout=1.0)
        return
    except subprocess.TimeoutExpired:
        # 仍未结束，升级为 kill
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("等待 balcon 进程终止时异常: %s", exc)
        return

    try:
        process.kill()
    except Exception as exc:  # noqa: BLE001
        logger.debug("kill balcon 进程时异常: %s", exc)

    try:
        process.wait(timeout=2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("balcon 进程 kill 后仍未结束: pid=%s, 异常=%s", process.pid, exc)


# ---------------------------------------------------------------------------
# 命令预览
# ---------------------------------------------------------------------------
# 敏感选项集合：其后的参数值在预览时脱敏为 ***，避免明文密码或用户文本
# 写入日志文件或显示在 GUI 日志面板。仅影响预览字符串，不影响实际命令行。
_REDACT_OPTIONS: frozenset[str] = frozenset({"-pwd", "-t"})


def build_command_preview(balcon_path: str, args: list[str]) -> str:
    """构建可读的命令行字符串，路径或参数含空格时加双引号。

    敏感选项（``-pwd``、``-t``）的值脱敏为 ``***``，避免明文密码或用户
    文本内容写入日志文件或显示在 GUI 日志面板。仅影响预览字符串，
    不影响实际传递给子进程的 ``args``。
    """
    parts: list[str] = []
    if " " in balcon_path:
        parts.append(f'"{balcon_path}"')
    else:
        parts.append(balcon_path)
    i = 0
    while i < len(args):
        arg = args[i]
        # 当前 token 是敏感选项且存在后续值 → 输出选项 + ***
        if arg in _REDACT_OPTIONS and i + 1 < len(args):
            parts.append(arg)
            parts.append("***")
            i += 2
            continue
        if " " in arg:
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
        i += 1
    return " ".join(parts)
