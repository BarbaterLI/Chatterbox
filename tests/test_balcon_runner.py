"""balcon_runner 模块单元测试。

使用 unittest.mock 模拟 subprocess.run / subprocess.Popen，验证
路径校验、语音/设备列举、命令执行与取消、命令预览等行为。
不依赖真实 balcon.exe。
"""
from __future__ import annotations

import io
import os.path
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from balcon_batch_tts.core.balcon_runner import (
    BalconError,
    BalconExecutionError,
    BalconNotFoundError,
    _validate_balcon_path,
    build_command_preview,
    list_devices,
    list_voices,
    run_balcon,
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
# _validate_balcon_path
# ---------------------------------------------------------------------------
class TestValidateBalconPath:
    """_validate_balcon_path 应校验路径存在性。"""

    def test_path_not_exists_raises_not_found(self) -> None:
        with pytest.raises(BalconNotFoundError):
            _validate_balcon_path("nonexistent/path/balcon.exe")

    def test_path_is_directory_raises_not_found(self, tmp_path: pytest.TempPathFactory) -> None:
        with pytest.raises(BalconNotFoundError):
            _validate_balcon_path(str(tmp_path))

    def test_path_exists_returns_absolute(self, tmp_path: pytest.TempPathFactory) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")
        result = _validate_balcon_path(str(fake_balcon))
        assert os.path.isabs(result)
        assert os.path.isfile(result)

    def test_path_exists_normalized(self, tmp_path: pytest.TempPathFactory) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")
        result = _validate_balcon_path(str(fake_balcon))
        assert os.path.normpath(result) == result

    def test_path_not_pe_raises_not_found(self, tmp_path: pytest.TempPathFactory) -> None:
        """缺少 MZ 头的文件（如 .lnk 快捷方式、文本文件）应被拒绝。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_text("not an executable")
        with pytest.raises(BalconNotFoundError, match="不是有效的 Win32 可执行文件"):
            _validate_balcon_path(str(fake_balcon))

    def test_path_dll_has_mz_passes_validation(self, tmp_path: pytest.TempPathFactory) -> None:
        """DLL 也有 MZ 头，路径校验通过（但后续 subprocess 会失败）。"""
        fake_balcon = tmp_path / "balcon.dll"
        fake_balcon.write_bytes(b"MZ\x90\x00")
        result = _validate_balcon_path(str(fake_balcon))
        assert os.path.isfile(result)


# ---------------------------------------------------------------------------
# list_voices
# ---------------------------------------------------------------------------
class TestListVoices:
    """list_voices 应解析 balcon -l 输出为语音名列表。"""

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_voices_success(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Microsoft Anna\nMicrosoft David\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        voices = list_voices(str(fake_balcon))
        assert voices == ["Microsoft Anna", "Microsoft David"]

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_voices_failure_raises_execution_error(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        with pytest.raises(BalconExecutionError):
            list_voices(str(fake_balcon))

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_voices_empty_output(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        assert list_voices(str(fake_balcon)) == []

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_voices_strips_whitespace(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  Voice A  \n  Voice B  \n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        voices = list_voices(str(fake_balcon))
        assert voices == ["Voice A", "Voice B"]

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_voices_skips_blank_lines(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Voice A\n\nVoice B\n   \n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        voices = list_voices(str(fake_balcon))
        assert voices == ["Voice A", "Voice B"]


# ---------------------------------------------------------------------------
# list_devices
# ---------------------------------------------------------------------------
class TestListDevices:
    """list_devices 应解析 balcon -g 输出为 (index, name) 列表。"""

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_devices_success(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0: Default Device\n1: Speakers\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        devices = list_devices(str(fake_balcon))
        assert devices == [(0, "Default Device"), (1, "Speakers")]

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_devices_empty_output(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        assert list_devices(str(fake_balcon)) == []

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_devices_ignores_non_matching_lines(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0: Device A\ninvalid line\n1: Device B\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        devices = list_devices(str(fake_balcon))
        assert devices == [(0, "Device A"), (1, "Device B")]

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.run")
    def test_list_devices_failure_raises_execution_error(
        self, mock_run: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        with pytest.raises(BalconExecutionError):
            list_devices(str(fake_balcon))


# ---------------------------------------------------------------------------
# run_balcon
# ---------------------------------------------------------------------------
class TestRunBalcon:
    """run_balcon 应通过 Popen 启动 balcon 并返回 (returncode, stdout, stderr)。"""

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_success(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """正常完成时返回返回码和输出。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_process = _FakeProcess(returncode=0, stdout="ok", stderr="")
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_balcon(
            str(fake_balcon), ["-t", "hello"]
        )
        assert returncode == 0
        assert stdout == "ok"
        assert stderr == ""

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_nonzero_returncode_does_not_raise(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """返回码非零不抛异常，由调用方决定如何处理。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_process = _FakeProcess(
            returncode=1, stdout="output", stderr="some error"
        )
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_balcon(
            str(fake_balcon), ["-t", "hello"]
        )
        assert returncode == 1
        assert stdout == "output"
        assert stderr == "some error"

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_cancel_event_raises(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """cancel_event 被设置时应抛 BalconError 并终止进程。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_process = _FakeProcess(never_exit=True)
        mock_popen.return_value = mock_process

        cancel_event = threading.Event()
        cancel_event.set()

        with pytest.raises(BalconError, match="取消"):
            run_balcon(
                str(fake_balcon),
                ["-t", "hello"],
                cancel_event=cancel_event,
            )
        # 验证进程被 terminate
        assert mock_process._terminated

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_passes_args_to_popen(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """应将路径与参数列表拼接后传给 Popen。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        mock_process = _FakeProcess(returncode=0)
        mock_popen.return_value = mock_process

        run_balcon(str(fake_balcon), ["-n", "Emma", "-s", "2"])

        expected_cmd = [str(fake_balcon), "-n", "Emma", "-s", "2"]
        # Popen 第一个位置参数是命令列表
        actual_cmd = mock_popen.call_args[0][0] if mock_popen.call_args[0] else mock_popen.call_args[1].get("args")
        # 路径可能被规范化为绝对路径，只校验参数部分
        assert actual_cmd[1:] == expected_cmd[1:]

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_large_stderr_no_deadlock(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """子进程产生大量 stderr（>64KB）时不应死锁。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        large_stderr = "x" * (64 * 1024 + 100)  # 超过 64KB 管道缓冲区
        mock_process = _FakeProcess(
            returncode=0, stdout="", stderr=large_stderr
        )
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_balcon(
            str(fake_balcon), ["-t", "hello"]
        )
        assert returncode == 0
        assert len(stderr) == len(large_stderr)
        assert stderr == large_stderr

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_stdout_stderr_accumulation(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """验证返回的 stdout/stderr 内容完整。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        stdout_content = "line1\nline2\nline3\n"
        stderr_content = "warning\nerror\n"
        mock_process = _FakeProcess(
            returncode=0,
            stdout=stdout_content,
            stderr=stderr_content,
        )
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_balcon(
            str(fake_balcon), ["-t", "hello"]
        )
        assert returncode == 0
        assert stdout == stdout_content
        assert stderr == stderr_content

    @patch("balcon_batch_tts.core.balcon_runner.subprocess.Popen")
    def test_run_balcon_large_stdout_no_deadlock(
        self, mock_popen: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """子进程产生大量 stdout（>64KB）时不应死锁。"""
        fake_balcon = tmp_path / "balcon.exe"
        fake_balcon.write_bytes(b"MZ")

        large_stdout = "y" * (64 * 1024 + 200)
        mock_process = _FakeProcess(
            returncode=0, stdout=large_stdout, stderr=""
        )
        mock_popen.return_value = mock_process

        returncode, stdout, stderr = run_balcon(
            str(fake_balcon), ["-t", "hello"]
        )
        assert returncode == 0
        assert stdout == large_stdout
        assert stderr == ""


# ---------------------------------------------------------------------------
# build_command_preview
# ---------------------------------------------------------------------------
class TestBuildCommandPreview:
    """build_command_preview 应对含空格的路径/参数加双引号。"""

    def test_path_with_spaces_quoted(self) -> None:
        result = build_command_preview(
            "C:/Program Files/balcon.exe",
            ["-n", "Emma"],
        )
        assert result == '"C:/Program Files/balcon.exe" -n Emma'

    def test_arg_with_spaces_quoted(self) -> None:
        result = build_command_preview(
            "balcon.exe",
            ["-n", "Emma Watson", "-s", "2"],
        )
        assert result == 'balcon.exe -n "Emma Watson" -s 2'

    def test_no_spaces_no_quotes(self) -> None:
        result = build_command_preview(
            "balcon.exe",
            ["-n", "Emma", "-s", "2"],
        )
        assert result == "balcon.exe -n Emma -s 2"

    def test_multiple_args_with_spaces(self) -> None:
        result = build_command_preview(
            "C:/Program Files/balcon.exe",
            ["-n", "Emma Watson", "-w", "C:/Output dir/out.wav"],
        )
        assert (
            result
            == '"C:/Program Files/balcon.exe" -n "Emma Watson" -w "C:/Output dir/out.wav"'
        )

    def test_empty_args(self) -> None:
        result = build_command_preview("balcon.exe", [])
        assert result == "balcon.exe"

    def test_path_and_arg_both_with_spaces(self) -> None:
        result = build_command_preview(
            "C:/My Tools/balcon.exe",
            ["-n", "Voice One", "-t", "Hello World"],
        )
        # -t 是敏感选项，其值 "Hello World" 脱敏为 ***
        assert (
            result
            == '"C:/My Tools/balcon.exe" -n "Voice One" -t ***'
        )
