"""blb2txt.exe 子进程封装模块。

提供 blb2txt.exe 的路径校验、命令执行与安全终止等能力。
纯标准库实现，不依赖任何 GUI 库，可在无界面环境下独立测试。

子进程创建、cancel 轮询、超时处理与终止流程与 balcon_runner 保持一致，
复用 ``balcon_runner._creationflags`` 与 ``terminate_balcon`` 以避免重复实现。
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

from chatterbox.core.balcon_runner import (
    _REDACT_OPTIONS,
    _close_pipes,
    _creationflags,
    _read_pipe,
    terminate_balcon,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------
class Blb2txtError(Exception):
    """blb2txt 相关错误基类。"""


class Blb2txtNotFoundError(Blb2txtError):
    """blb2txt.exe 未找到。"""


class Blb2txtExecutionError(Blb2txtError):
    """blb2txt 执行失败（返回码非零）。

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


class Blb2txtTimeoutError(Blb2txtError):
    """blb2txt 执行超时。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def validate_blb2txt_path(blb2txt_path: str) -> str:
    """校验 blb2txt.exe 路径存在且是文件，返回规范化的绝对路径。"""
    if not os.path.isfile(blb2txt_path):
        raise Blb2txtNotFoundError(f"blb2txt.exe 未找到: {blb2txt_path}")
    return os.path.abspath(blb2txt_path)


# ---------------------------------------------------------------------------
# 通用执行
# ---------------------------------------------------------------------------
def run_blb2txt(
    blb2txt_path: str,
    args: list[str],
    timeout: float | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[int, str, str]:
    """启动 blb2txt.exe 并轮询其状态，支持取消与超时。

    返回 ``(returncode, stdout, stderr)``。返回码非零不抛异常，仅记录 warning，
    由调用方决定如何处理。取消时抛 :class:`Blb2txtError`，超时抛
    :class:`Blb2txtTimeoutError`。

    使用守护线程读取 stdout/stderr 管道，避免子进程输出超过 64KB
    管道缓冲区时死锁（与 :func:`balcon_runner.run_balcon` 相同的模式）。
    主循环以 ``process.wait(timeout=0.1)`` 轮询，在 timeout 异常时
    检查 ``cancel_event`` 与超时条件。
    """
    path = validate_blb2txt_path(blb2txt_path)
    process = subprocess.Popen(
        [path] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creationflags(),
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
                raise Blb2txtError("任务已取消")
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                raise Blb2txtTimeoutError(f"blb2txt 执行超时: {timeout}秒")
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
            "blb2txt 执行返回非零码: returncode=%s, args=%s, stderr=%s",
            process.returncode,
            args,
            stderr,
        )
    return process.returncode, stdout, stderr


# ---------------------------------------------------------------------------
# 命令预览
# ---------------------------------------------------------------------------
def build_blb2txt_command_preview(blb2txt_path: str, args: list[str]) -> str:
    """构建可读的命令行字符串，路径或参数含空格时加双引号。

    敏感选项（``-pwd``、``-t``）的值脱敏为 ``***``，避免明文密码或用户
    文本内容写入日志文件或显示在 GUI 日志面板。仅影响预览字符串，
    不影响实际传递给子进程的 ``args``。
    """
    parts: list[str] = []
    if " " in blb2txt_path:
        parts.append(f'"{blb2txt_path}"')
    else:
        parts.append(blb2txt_path)
    i = 0
    while i < len(args):
        arg = args[i]
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
