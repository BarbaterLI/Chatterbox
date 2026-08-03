"""blb2txt_worker 模块单元测试。

验证 :class:`Blb2txtTask` 的构造、取消、信号访问与 ``_build_args`` 在
stdin / 非 stdin 模式下的行为。不启动真实 blb2txt.exe，``_exec`` 的子进程
调用由 ``test_blb2txt_runner.py`` 覆盖，本测试聚焦任务封装层逻辑。
"""
from __future__ import annotations

import copy

import pytest

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.blb2txt_worker import Blb2txtTask


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------
@pytest.fixture
def default_config() -> Blb2txtConfig:
    """返回全默认值的 Blb2txtConfig（``f_files`` 为空，``i_stdin`` 为 False）。"""
    return Blb2txtConfig.create_default()


@pytest.fixture
def task(default_config: Blb2txtConfig) -> Blb2txtTask:
    """返回典型的 Blb2txtTask 实例（非 stdin 模式）。"""
    return Blb2txtTask(
        input_file="books/sample.pdf",
        config=default_config,
        output_path="out/sample.txt",
        blb2txt_path="tools/blb2txt.exe",
        index=3,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------
class TestInit:
    """``Blb2txtTask.__init__`` 应正确保存全部参数。"""

    def test_input_file_saved(self, task: Blb2txtTask) -> None:
        assert task.input_file == "books/sample.pdf"

    def test_output_path_saved(self, task: Blb2txtTask) -> None:
        assert task.output_path == "out/sample.txt"

    def test_index_saved(self, task: Blb2txtTask) -> None:
        assert task.index == 3

    def test_index_default_zero(self, default_config: Blb2txtConfig) -> None:
        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        assert t.index == 0

    def test_output_path_can_be_none(self, default_config: Blb2txtConfig) -> None:
        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        assert t.output_path is None

    def test_config_reference_saved(self, default_config: Blb2txtConfig) -> None:
        """构造时不深拷贝配置（深拷贝发生在 _build_args），保存原引用。"""
        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        # 内部保存的应为传入的同一对象（_build_args 时才复制）
        assert t._config is default_config

    def test_blb2txt_path_saved(self, task: Blb2txtTask) -> None:
        assert task._blb2txt_path == "tools/blb2txt.exe"


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------
class TestCancel:
    """``cancel()`` 应可安全调用且不抛异常。"""

    def test_cancel_does_not_raise(self, task: Blb2txtTask) -> None:
        task.cancel()  # 不应抛异常

    def test_cancel_is_idempotent(self, task: Blb2txtTask) -> None:
        task.cancel()
        task.cancel()  # 重复调用应安全

    def test_cancel_sets_internal_event(self, task: Blb2txtTask) -> None:
        task.cancel()
        assert task._cancel_event.is_set()


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------
class TestSignals:
    """``signals`` 属性应可访问且具备预期信号。"""

    def test_signals_attribute_exists(self, task: Blb2txtTask) -> None:
        assert task.signals is not None

    def test_signals_has_expected_members(self, task: Blb2txtTask) -> None:
        """TaskSignals 应暴露 started/finished/log/progress/error 信号。"""
        from balcon_batch_tts.utils.signals import TaskSignals

        assert isinstance(task.signals, TaskSignals)
        for name in ("started", "finished", "log", "progress", "error"):
            assert hasattr(task.signals, name), f"缺少信号: {name}"


# ---------------------------------------------------------------------------
# _build_args
# ---------------------------------------------------------------------------
class TestBuildArgs:
    """``_build_args`` 应按 stdin 模式决定是否覆盖 ``f_files``。"""

    def test_non_stdin_overrides_f_files_with_input(
        self, default_config: Blb2txtConfig
    ) -> None:
        """非 stdin 模式下 ``f_files`` 应被覆盖为 ``[input_file]``。"""
        default_config.f_files = ["other.pdf"]  # 预置干扰项
        assert default_config.i_stdin is False

        t = Blb2txtTask(
            input_file="books/sample.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        args = t._build_args()

        # input_file 应出现在参数中（-f 选项），other.pdf 不应出现
        assert "books/sample.pdf" in args
        assert "other.pdf" not in args
        # -f 选项应紧邻 input_file
        idx = args.index("books/sample.pdf")
        assert idx > 0 and args[idx - 1] == "-f"

    def test_stdin_mode_keeps_original_f_files(
        self, default_config: Blb2txtConfig
    ) -> None:
        """stdin 模式（``i_stdin=True``）下不应覆盖 ``f_files``。"""
        default_config.f_files = ["original.pdf"]
        default_config.i_stdin = True

        t = Blb2txtTask(
            input_file="books/sample.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        args = t._build_args()

        # 原始 f_files 保留，input_file 不应被注入
        assert "original.pdf" in args
        assert "books/sample.pdf" not in args
        # -i 标志应出现（i_stdin 为 True）
        assert "-i" in args

    def test_stdin_mode_empty_f_files_not_injected(
        self, default_config: Blb2txtConfig
    ) -> None:
        """stdin 模式下即使 ``f_files`` 为空也不注入 input_file。"""
        default_config.i_stdin = True
        # f_files 保持默认空列表

        t = Blb2txtTask(
            input_file="books/sample.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        args = t._build_args()

        assert "books/sample.pdf" not in args
        assert "-i" in args

    def test_build_args_does_not_mutate_original_config(
        self, default_config: Blb2txtConfig
    ) -> None:
        """``_build_args`` 应深拷贝配置，不修改原始 ``f_files``。"""
        default_config.f_files = ["keep.pdf"]
        original_snapshot = copy.deepcopy(default_config)

        t = Blb2txtTask(
            input_file="books/sample.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        t._build_args()  # 触发覆盖

        # 原配置应保持不变
        assert default_config.f_files == ["keep.pdf"]
        assert default_config == original_snapshot

    def test_build_args_returns_list_of_strings(
        self, default_config: Blb2txtConfig
    ) -> None:
        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        args = t._build_args()
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)

    def test_repeated_build_args_is_stable(
        self, default_config: Blb2txtConfig
    ) -> None:
        """多次调用 ``_build_args`` 应返回相同结果（深拷贝不污染状态）。"""
        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        first = t._build_args()
        second = t._build_args()
        assert first == second


# ---------------------------------------------------------------------------
# _exec（异常分支，不启动真实进程）
# ---------------------------------------------------------------------------
class TestExecErrorHandling:
    """``_exec`` 应捕获 blb2txt 异常并返回非零返回码（不启动真实进程）。"""

    def test_exec_not_found_emits_error_and_returns_nonzero(
        self, default_config: Blb2txtConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from balcon_batch_tts.core import blb2txt_worker

        def _raise(*args, **kwargs):  # noqa: ANN202
            raise blb2txt_worker.Blb2txtNotFoundError("missing")

        monkeypatch.setattr(blb2txt_worker, "run_blb2txt", _raise)

        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        returncode, _stdout, _stderr = t._exec(["-f", "a.pdf"])
        assert returncode != 0

    def test_exec_unexpected_exception_returns_nonzero(
        self, default_config: Blb2txtConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from balcon_batch_tts.core import blb2txt_worker

        def _raise(*args, **kwargs):  # noqa: ANN202
            raise RuntimeError("unexpected")

        monkeypatch.setattr(blb2txt_worker, "run_blb2txt", _raise)

        t = Blb2txtTask(
            input_file="a.pdf",
            config=default_config,
            output_path=None,
            blb2txt_path="blb2txt.exe",
        )
        returncode, _stdout, _stderr = t._exec(["-f", "a.pdf"])
        assert returncode != 0
