"""断点续传记录点管理模块。

提供 :class:`CheckpointManager`，将批处理进度持久化到 JSON 文件，支持：
- 任务开始时创建 checkpoint，记录输入文件列表与配置快照
- 每个任务完成时增量更新 checkpoint（成功/失败列表）
- 全部完成时清除 checkpoint（或保留作为历史）
- 程序崩溃后重启时加载 checkpoint，恢复未完成文件列表
- 保存历史转换参数（BalconConfig/Blb2txtConfig 的 dict 快照）

checkpoint 文件位于输出目录下，命名为 ``.balcon_batch_checkpoint.json``，
以 ``.`` 前缀隐藏。文件结构：

.. code-block:: json

    {
      "version": 2,
      "tool_type": "balcon",
      "input_files": ["/path/to/file1.txt", "/path/to/file2.txt"],
      "completed_files": ["/path/to/file1.txt"],
      "failed_files": [],
      "output_dir": "/output",
      "filename_template": "{name}.wav",
      "output_format": "mp3",
      "ffmpeg_path": "",
      "config_snapshot": {"n_voice": "Heather", "s_rate": "22050", ...},
      "created_at": "2026-07-27T12:00:00",
      "updated_at": "2026-07-27T12:05:30"
    }

约束：
- 仅依赖 Python 标准库（json、os、time、threading、logging）
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint 数据结构
# ---------------------------------------------------------------------------
@dataclass
class CheckpointState:
    """断点续传状态数据。

    Attributes:
        version: checkpoint 格式版本，当前为 2。
        tool_type: 工具类型（``"balcon"`` 或 ``"blb2txt"``）。
        input_files: 输入文件完整路径列表（原始顺序）。
        completed_files: 已成功完成的文件路径列表。
        failed_files: 失败的文件路径列表。
        output_dir: 输出目录。
        filename_template: 文件名模板。
        output_format: 输出格式（AudioFormat.value）。
        ffmpeg_path: ffmpeg 路径（仅非 WAV 格式）。
        config_snapshot: 历史转换参数快照（BalconConfig/Blb2txtConfig.to_dict()），
            为空 dict 表示无参数快照。用于崩溃恢复时还原 Tab 配置。
        created_at: ISO 格式创建时间。
        updated_at: ISO 格式最后更新时间。
    """

    version: int = 2
    tool_type: str = "balcon"
    input_files: list[str] = field(default_factory=list)
    completed_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    output_dir: str = ""
    filename_template: str = "{name}.wav"
    output_format: str = "wav"
    ffmpeg_path: str = ""
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化的 dict（含嵌套 dataclass）。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointState:
        """从 dict 反序列化，忽略未知字段。

        对 version 1 的旧格式 checkpoint 向后兼容：``config_snapshot``
        缺失时默认为空 dict。
        """
        known_fields = {
            "version",
            "tool_type",
            "input_files",
            "completed_files",
            "failed_files",
            "output_dir",
            "filename_template",
            "output_format",
            "ffmpeg_path",
            "config_snapshot",
            "created_at",
            "updated_at",
        }
        filtered = {k: v for k, v in data.items() if k in known_fields}
        # version 1 旧格式兼容：config_snapshot 缺失时默认空 dict
        if "config_snapshot" not in filtered:
            filtered["config_snapshot"] = {}
        return cls(**filtered)

    def pending_files(self) -> list[str]:
        """返回未完成的文件列表（保持原始顺序）。

        排除已完成与已失败的文件。
        """
        done = set(self.completed_files) | set(self.failed_files)
        return [f for f in self.input_files if f not in done]

    def progress_percent(self) -> float:
        """返回完成百分比（0-100）。"""
        total = len(self.input_files)
        if total == 0:
            return 100.0
        done = len(self.completed_files) + len(self.failed_files)
        return (done / total) * 100.0

    def has_config_snapshot(self) -> bool:
        """是否包含历史转换参数快照。"""
        return bool(self.config_snapshot)


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------
class CheckpointManager:
    """断点续传记录点管理器。

    线程安全：所有公开方法通过 :attr:`_lock` 互斥，可从工作线程安全调用。

    使用流程：
    1. ``mgr = CheckpointManager(output_dir)`` 创建管理器
    2. ``mgr.create(state)`` 开始批次时创建 checkpoint
    3. ``mgr.mark_completed(file)`` / ``mgr.mark_failed(file)`` 任务完成时更新
    4. ``mgr.clear()`` 全部完成时清除
    5. 重启后 ``state = mgr.load()`` 恢复进度

    Attributes:
        output_dir: 输出目录，checkpoint 文件位于此目录下。
        checkpoint_path: checkpoint 文件完整路径。
    """

    # checkpoint 文件名（以 . 前缀隐藏）
    _CHECKPOINT_FILENAME = ".balcon_batch_checkpoint.json"

    # 原子写入临时文件后缀
    _TEMP_SUFFIX = ".tmp"

    # 追加记录达到此阈值时触发压缩
    _COMPACTION_THRESHOLD = 50

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir or "."
        self.checkpoint_path = os.path.join(
            self.output_dir, self._CHECKPOINT_FILENAME
        )
        self._lock = threading.Lock()
        self._state: CheckpointState | None = None
        self._pending_appends: int = 0

    def exists(self) -> bool:
        """是否存在有效的 checkpoint 文件。"""
        return os.path.isfile(self.checkpoint_path)

    def create(self, state: CheckpointState) -> None:
        """创建新的 checkpoint（覆盖已有）。

        Args:
            state: 初始状态（``input_files`` 应已填充）。
        """
        with self._lock:
            now = self._now_iso()
            state.created_at = now
            state.updated_at = now
            self._state = state
            self._pending_appends = 0
            self._write_atomic(state)

    def load(self) -> CheckpointState | None:
        """加载 checkpoint，返回状态对象。

        支持两种文件格式：

        1. **旧格式**：纯 JSON 文件（单行或格式化的 JSON 对象），
           直接 ``json.loads`` 解析为 :class:`CheckpointState`。
        2. **新格式（JSONL）**：基线 JSON 对象 + 追加 JSONL 记录。
           基线通过 ``JSONDecoder.raw_decode`` 提取，后续每行回放到状态。
           损坏的追加行跳过并记录 warning。

        Returns:
            :class:`CheckpointState` 或 ``None``（文件不存在或解析失败）。
        """
        with self._lock:
            if not os.path.isfile(self.checkpoint_path):
                return None
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except OSError as exc:
                logger.warning("加载 checkpoint 失败: %s", exc)
                return None

            # 策略 1：尝试作为纯 JSON 解析（旧格式或已压缩的基线）
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    state = CheckpointState.from_dict(data)
                    self._state = state
                    self._pending_appends = 0
                    return state
            except json.JSONDecodeError:
                pass  # 非纯 JSON，尝试 JSONL 格式

            # 策略 2：JSONL 格式（基线 JSON + 追加记录）
            try:
                decoder = json.JSONDecoder()
                baseline_data, end_idx = decoder.raw_decode(content)
                if not isinstance(baseline_data, dict):
                    logger.warning("checkpoint 基线不是 JSON 对象")
                    return None
                state = CheckpointState.from_dict(baseline_data)

                # 回放追加记录
                remaining = content[end_idx:]
                for line in remaining.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("跳过损坏的追加记录: %s", exc)
                        continue
                    if not isinstance(record, dict):
                        logger.warning("跳过非对象追加记录: %r", record)
                        continue
                    self._replay_record(state, record)

                self._state = state
                self._pending_appends = 0
                return state
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("加载 checkpoint 失败: %s", exc)
                return None

    @staticmethod
    def _replay_record(state: CheckpointState, record: dict[str, Any]) -> None:
        """将单条追加记录回放到状态对象。"""
        rec_type = record.get("type")
        rec_file = record.get("file")
        if rec_file is None:
            return
        if rec_type == "completed":
            if rec_file not in state.completed_files:
                state.completed_files.append(rec_file)
            if rec_file in state.failed_files:
                state.failed_files.remove(rec_file)
        elif rec_type == "failed":
            if rec_file not in state.failed_files:
                state.failed_files.append(rec_file)
            if rec_file in state.completed_files:
                state.completed_files.remove(rec_file)
        ts = record.get("ts")
        if isinstance(ts, str) and ts:
            state.updated_at = ts

    def mark_completed(self, file_path: str) -> None:
        """标记文件为已完成。

        线程安全，可从工作线程调用。若未调用 :meth:`create` 则 no-op。

        采用"追加日志 + 定期压缩"策略：每次标记追加一行 JSONL 记录，
        达到 :attr:`_COMPACTION_THRESHOLD` 时压缩为基线快照。

        Args:
            file_path: 已完成的文件绝对路径。
        """
        with self._lock:
            if self._state is None:
                return
            if file_path in self._state.completed_files:
                return
            self._state.completed_files.append(file_path)
            # 从 failed_files 移除（若之前失败过）
            if file_path in self._state.failed_files:
                self._state.failed_files.remove(file_path)
            self._state.updated_at = self._now_iso()
            self._append_record({
                "type": "completed",
                "file": file_path,
                "ts": self._state.updated_at,
            })
            self._pending_appends += 1
            if self._pending_appends >= self._COMPACTION_THRESHOLD:
                self._compact()

    def mark_failed(self, file_path: str) -> None:
        """标记文件为已失败。

        线程安全，可从工作线程调用。若未调用 :meth:`create` 则 no-op。

        采用"追加日志 + 定期压缩"策略：每次标记追加一行 JSONL 记录，
        达到 :attr:`_COMPACTION_THRESHOLD` 时压缩为基线快照。

        Args:
            file_path: 失败的文件绝对路径。
        """
        with self._lock:
            if self._state is None:
                return
            if file_path in self._state.failed_files:
                return
            self._state.failed_files.append(file_path)
            # 从 completed_files 移除（若之前标记成功但实际失败）
            if file_path in self._state.completed_files:
                self._state.completed_files.remove(file_path)
            self._state.updated_at = self._now_iso()
            self._append_record({
                "type": "failed",
                "file": file_path,
                "ts": self._state.updated_at,
            })
            self._pending_appends += 1
            if self._pending_appends >= self._COMPACTION_THRESHOLD:
                self._compact()

    def clear(self) -> None:
        """删除 checkpoint 文件（全部完成时调用）。"""
        with self._lock:
            self._state = None
            self._pending_appends = 0
            try:
                if os.path.isfile(self.checkpoint_path):
                    os.remove(self.checkpoint_path)
            except OSError as exc:
                logger.warning("删除 checkpoint 失败: %s", exc)

    def get_state(self) -> CheckpointState | None:
        """返回当前内存中的状态（不读取文件）。"""
        with self._lock:
            return self._state

    def save_snapshot(self) -> None:
        """立即将当前内存状态写入文件（用于崩溃前紧急保存）。

        若 :attr:`_state` 为 ``None`` 则 no-op。
        """
        with self._lock:
            if self._state is None:
                return
            self._state.updated_at = self._now_iso()
            self._write_atomic(self._state)
            self._pending_appends = 0

    # ----------------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------------
    @staticmethod
    def _now_iso() -> str:
        """返回当前时间的 ISO 格式字符串。"""
        return datetime.now().isoformat(timespec="seconds")

    def _write_atomic(self, state: CheckpointState) -> None:
        """原子写入 checkpoint 文件（基线快照）。

        先写入临时文件，再 rename 覆盖，避免崩溃时写入半截文件。
        输出 JSON 中注入 ``_format: "jsonl"`` 键标识新格式；
        :meth:`CheckpointState.from_dict` 会忽略未知字段。

        Args:
            state: 状态对象。
        """
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as exc:
            logger.warning("创建 checkpoint 目录失败 %s: %s", self.output_dir, exc)
            return

        temp_path = self.checkpoint_path + self._TEMP_SUFFIX
        try:
            data = state.to_dict()
            data["_format"] = "jsonl"
            with open(temp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(temp_path, self.checkpoint_path)
        except OSError as exc:
            logger.warning("写入 checkpoint 失败: %s", exc)
            # 清理临时文件
            try:
                if os.path.isfile(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def _append_record(self, record: dict[str, Any]) -> None:
        """以 JSONL 格式追加单行记录到 checkpoint 文件。

        在 :attr:`_lock` 内调用，以追加模式（``"a"``）打开文件，
        写入单行 JSON 后换行。每行一条记录，格式如：

        .. code-block:: json

            {"type": "completed", "file": "/path/to/file", "ts": "2026-07-28T12:00:00"}

        Args:
            record: 单条记录 dict。
        """
        try:
            with open(self.checkpoint_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False))
                fh.write("\n")
        except OSError as exc:
            logger.warning("追加 checkpoint 记录失败: %s", exc)

    def _compact(self) -> None:
        """压缩：将当前内存状态作为新基线写入，清空追加记录。

        - 通过 :meth:`_write_atomic` 写入完整状态（覆盖文件，清除追加行）
        - 重置 :attr:`_pending_appends` 计数器为 0
        """
        if self._state is None:
            self._pending_appends = 0
            return
        self._write_atomic(self._state)
        self._pending_appends = 0


__all__ = ["CheckpointManager", "CheckpointState"]
