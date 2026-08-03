"""blb2txt 任务工作单元。

定义 :class:`Blb2txtTask`，封装单个 blb2txt.exe 任务的执行逻辑，继承自
:class:`chatterbox.core.base_worker.BaseToolTask`，可由
:class:`PySide6.QtCore.QThreadPool` 调度到子线程运行。任务通过
:class:`chatterbox.utils.signals.TaskSignals` 向主线程报告状态
（开始/结束/日志/错误），并支持通过 :meth:`Blb2txtTask.cancel` 安全取消
运行中的 blb2txt 子进程。
"""

from __future__ import annotations

import copy
import logging
import os

from chatterbox.core.base_worker import BaseToolTask
from chatterbox.core.blb2txt_config import Blb2txtConfig
from chatterbox.core.blb2txt_runner import (
    Blb2txtError,
    Blb2txtExecutionError,
    Blb2txtNotFoundError,
    Blb2txtTimeoutError,
    build_blb2txt_command_preview,
    run_blb2txt,
)

logger = logging.getLogger(__name__)


class Blb2txtTask(BaseToolTask):
    """单个 blb2txt 任务的 QRunnable 工作单元。

    在子线程中调用 :func:`run_blb2txt` 执行文档转文本，通过 ``signals`` 报告
    进度与结果。可通过 :meth:`cancel` 取消运行中的子进程。

    Attributes:
        input_file: 输入文件路径。
        config: blb2txt 配置（会在 :meth:`_build_args` 中深拷贝，非 stdin
            模式下 ``f_files`` 覆盖为本任务输入文件）。
        output_path: 输出文件路径。
        blb2txt_path: blb2txt.exe 路径。
        index: 任务在批次中的序号（便于外部追踪）。
        signals: 任务信号对象。
    """

    def __init__(
        self,
        input_file: str,
        config: Blb2txtConfig,
        output_path: str | None,
        blb2txt_path: str,
        index: int = 0,
    ) -> None:
        super().__init__(input_file=input_file, output_path=output_path, index=index)
        self._config = config
        self._blb2txt_path = blb2txt_path

    def _build_args(self) -> list[str]:
        """深拷贝配置并按本任务输入覆盖 ``f_files``，生成 blb2txt 命令行参数。

        - 非 stdin 模式（``i_stdin`` 为 False）：将 ``f_files`` 覆盖为
          ``[self._input_file]``，确保每个任务只处理自己的输入文件。
        - stdin 模式（``i_stdin`` 为 True）：保持原 ``f_files`` 不变，输入
          由标准流提供，文件列表参数不应被本任务覆盖。

        使用 :func:`copy.deepcopy` 复制配置，避免本任务对 ``f_files`` 的覆盖
        影响到共享的原始配置对象。

        Returns:
            参数列表（不含可执行文件路径本身）。
        """
        cfg = copy.deepcopy(self._config)
        if not cfg.i_stdin:
            cfg.f_files = [self._input_file]
        return cfg.to_args()

    def _exec(self, args: list[str]) -> tuple[int, str, str]:
        """调用 :func:`run_blb2txt` 执行 blb2txt 任务。

        发射命令行预览日志，捕获 :class:`Blb2txtError` 及其子类（未找到、
        执行失败、超时、取消）与其它未预期异常，异常时发射 ``signals.error``
        信号并返回非零返回码，确保基类 :meth:`run` 模板流程不被打断。

        Args:
            args: 由 :meth:`_build_args` 生成的参数列表。

        Returns:
            ``(returncode, stdout, stderr)`` 元组。执行失败时返回码为非零。
        """
        filename = os.path.basename(self._input_file)
        self.signals.log.emit(
            f"命令行: {build_blb2txt_command_preview(self._blb2txt_path, args)}"
        )

        returncode = 0
        stdout = ""
        stderr = ""
        try:
            returncode, stdout, stderr = run_blb2txt(
                self._blb2txt_path, args, cancel_event=self._cancel_event
            )
        except (
            Blb2txtNotFoundError,
            Blb2txtExecutionError,
            Blb2txtTimeoutError,
            Blb2txtError,
        ) as exc:
            # Blb2txtError 兜底覆盖取消等其他 blb2txt 错误；
            # 前三者已显式列出于元组中仅为说明预期异常类型。
            self.signals.error.emit(filename, str(exc))
            returncode = 1
        except Exception as exc:  # noqa: BLE001 - 兜底，确保任务不卡死
            logger.exception("blb2txt 任务发生未预期异常: %s", self._input_file)
            self.signals.error.emit(filename, str(exc))
            returncode = 1
        return returncode, stdout, stderr


__all__ = ["Blb2txtTask"]
