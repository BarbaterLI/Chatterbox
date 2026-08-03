"""blb2txt_runner 模块单元测试。

使用 unittest.mock 模拟 subprocess.Popen，验证路径校验、命令执行与取消、
命令预览等行为。不依赖真实 blb2txt.exe。
"""
from __future__ import annotations

import io
import os.path
import subprocess
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from balcon_batch_tts.core.blb2txt_runner import (
    Blb2txtError,
    Blb2txtExecutionError,
    Blb2txtNotFoundError,
    Blb2txtTimeoutError,
    build_blb2txt_command_preview,
    run_blb2txt,
    validate_blb2txt_path,
)


# ---------------------------------------------------------------------------
# FakeProcess: 模拟 subprocess.Popen 子进程（与 test_balcon_runner 相同模式）
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
# validate_blb2txt_path
# ---------------------------------------------------------------------------
class TestValidateBlb2txtPath:
    """validate_blb2txt_path 应校验路径存在性。"""

    def test_path_not_exists_raises_not_found(self) -> None:
        with pytest.raises(Blb2txtNotFoundError):
            validate_blb2txt_path("nonexistent/path/blb2txt.exe")

    def test_path_is_directory_raises_not_found(self, tmp_path: pytest.TempPathFactory) -> None:
        with pytest.raises(Blb2txtNotFoundError):
            validate_blb2txt_path(str(tmp_path))

    def test_path_exists_returns_absolute(self, tmp_path: pytest.TempPathFactory) -> None:
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")
        result = validate_blb2txt_path(str(fake_blb2txt))
        assert os.path.isabs(result)
        assert os.path.isfile(result)

    def test_path_exists_normalized(self, tmp_path: pytest.TempPathFactory) -> None:
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")
        result = validate_blb2txt_path(str(fake_blb2txt))
        assert os.path.normpath(result) == result

    def test_sys_executable_is_valid_path(self) -> None:
        """sys.executable 必然存在，可作为有效路径。"""
        result = validate_blb2txt_path(sys.executable)
        assert os.path.isabs(result)
        assert os.path.isfile(result)


# ---------------------------------------------------------------------------
# 异常类继承关系
# ---------------------------------------------------------------------------
class TestExceptionHierarchy:
    """blb2txt 异常类应自成体系，便于调用方按工具类型捕获。"""

    def test_not_found_is_subclass_of_blb2txt_error(self) -> None:
        assert issubclass(Blb2txtNotFoundError, Blb2txtError)

    def test_execution_error_is_subclass_of_blb2txt_error(self) -> None:
        assert issubclass(Blb2txtExecutionError, Blb2txtError)

    def test_timeout_error_is_subclass_of_blb2txt_error(self) -> None:
        assert issubclass(Blb2txtTimeoutError, Blb2txtError)

    def test_not_found_not_subclass_of_balcon_error(self) -> None:
        """blb2txt 异常应独立于 BalconError，便于按工具类型捕获。"""
        from balcon_batch_tts.core.balcon_runner import BalconError

        assert not issubclass(Blb2txtError, BalconError)
        assert not issubclass(Blb2txtNotFoundError, BalconError)

    def test_execution_error_carries_returncode_stdout_stderr(self) -> None:
        err = Blb2txtExecutionError(
            "fail", returncode=2, stderr="err", stdout="out"
        )
        assert err.returncode == 2
        assert err.stderr == "err"
        assert err.stdout == "out"


# ---------------------------------------------------------------------------
# run_blb2txt
# ---------------------------------------------------------------------------
class TestRunBlb2txt:
    """run_blb2txt 应通过 Popen 启动 blb2txt 并返回 (returncode, stdout, stderr)。"""

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_success(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(returncode=0, stdout="ok", stderr="")
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_blb2txt(
            str(fake_blb2txt), ["-f", "book.pdf", "-v", "out/"]
        )
        assert returncode == 0
        assert stdout == "ok"
        assert stderr == ""

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_nonzero_returncode_does_not_raise(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """返回码非零不抛异常，由调用方决定如何处理。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(
            returncode=1, stdout="output", stderr="some error"
        )
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_blb2txt(
            str(fake_blb2txt), ["-f", "book.pdf"]
        )
        assert returncode == 1
        assert stdout == "output"
        assert stderr == "some error"

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_cancel_event_raises(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """cancel_event 被设置时应抛 Blb2txtError。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(never_exit=True)
        mock_popen.return_value = mock_process

        cancel_event = threading.Event()
        cancel_event.set()

        with pytest.raises(Blb2txtError, match="取消"):
            run_blb2txt(
                str(fake_blb2txt),
                ["-f", "book.pdf"],
                cancel_event=cancel_event,
            )

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_timeout_raises_timeout_error(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """超过 timeout 应抛 Blb2txtTimeoutError 并终止进程。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(never_exit=True)
        mock_popen.return_value = mock_process

        with pytest.raises(Blb2txtTimeoutError):
            run_blb2txt(
                str(fake_blb2txt),
                ["-f", "book.pdf"],
                timeout=0.0,  # 立即超时
            )

        # 应调用 terminate_balcon 终止进程
        assert mock_process._terminated

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_cancel_terminates_process(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """取消时应调用 terminate_balcon 终止进程。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(never_exit=True)
        mock_popen.return_value = mock_process

        cancel_event = threading.Event()
        cancel_event.set()

        with pytest.raises(Blb2txtError):
            run_blb2txt(
                str(fake_blb2txt),
                ["-f", "book.pdf"],
                cancel_event=cancel_event,
            )

        assert mock_process._terminated

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_passes_args_to_popen(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """应将路径与参数列表拼接后传给 Popen。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(returncode=0)
        mock_popen.return_value = mock_process

        run_blb2txt(str(fake_blb2txt), ["-f", "book.pdf", "-v", "out/"])

        expected_cmd = [str(fake_blb2txt), "-f", "book.pdf", "-v", "out/"]
        actual_cmd = mock_popen.call_args[0][0] if mock_popen.call_args[0] else mock_popen.call_args[1].get("args")
        # 路径可能被规范化为绝对路径，只校验参数部分
        assert actual_cmd[1:] == expected_cmd[1:]

    @patch("balcon_batch_tts.core.blb2txt_runner.subprocess.Popen")
    def test_run_blb2txt_uses_creationflags(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Popen 应使用 balcon_runner._creationflags() 的返回值。"""
        fake_blb2txt = tmp_path / "blb2txt.exe"
        fake_blb2txt.write_text("fake")

        mock_process = _FakeProcess(returncode=0)
        mock_popen.return_value = mock_process

        run_blb2txt(str(fake_blb2txt), ["-f", "book.pdf"])

        kwargs = mock_popen.call_args[1]
        if os.name == "nt":
            assert kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW
        else:
            assert kwargs.get("creationflags") == 0


# ---------------------------------------------------------------------------
# build_blb2txt_command_preview
# ---------------------------------------------------------------------------
class TestBuildBlb2txtCommandPreview:
    """build_blb2txt_command_preview 应对含空格的路径/参数加双引号。"""

    def test_normal_path_no_spaces(self) -> None:
        result = build_blb2txt_command_preview(
            "C:/path/blb2txt.exe",
            ["-f", "book.pdf", "-v", "out/"],
        )
        assert result == "C:/path/blb2txt.exe -f book.pdf -v out/"

    def test_path_with_spaces_quoted(self) -> None:
        result = build_blb2txt_command_preview(
            "C:/path with space/blb2txt.exe",
            ["-f", "book.pdf", "-v", "out/"],
        )
        assert result == '"C:/path with space/blb2txt.exe" -f book.pdf -v out/'

    def test_arg_with_spaces_quoted(self) -> None:
        result = build_blb2txt_command_preview(
            "C:/path/blb2txt.exe",
            ["-f", "book with space.pdf", "-v", "out/"],
        )
        assert result == 'C:/path/blb2txt.exe -f "book with space.pdf" -v out/'

    def test_path_and_arg_both_with_spaces(self) -> None:
        result = build_blb2txt_command_preview(
            "C:/path with space/blb2txt.exe",
            ["-f", "book with space.pdf", "-v", "out/"],
        )
        assert (
            result
            == '"C:/path with space/blb2txt.exe" -f "book with space.pdf" -v out/'
        )

    def test_empty_args_returns_path_only(self) -> None:
        result = build_blb2txt_command_preview("C:/path/blb2txt.exe", [])
        assert result == "C:/path/blb2txt.exe"

    def test_empty_args_with_spaces_in_path(self) -> None:
        result = build_blb2txt_command_preview("C:/path with space/blb2txt.exe", [])
        assert result == '"C:/path with space/blb2txt.exe"'

    def test_multiple_args_with_spaces(self) -> None:
        result = build_blb2txt_command_preview(
            "C:/path with space/blb2txt.exe",
            ["-f", "book one.pdf", "-v", "C:/Output dir/"],
        )
        assert (
            result
            == '"C:/path with space/blb2txt.exe" -f "book one.pdf" -v "C:/Output dir/"'
        )

    def test_no_args_no_spaces(self) -> None:
        result = build_blb2txt_command_preview("blb2txt.exe", [])
        assert result == "blb2txt.exe"
