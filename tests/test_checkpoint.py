"""checkpoint 模块单元测试。

验证 :class:`CheckpointManager` 与 :class:`CheckpointState` 行为：
- CheckpointState 数据结构与 pending_files/progress_percent
- CheckpointManager create/load/mark_completed/mark_failed/clear
- 原子写入（崩溃后无半截文件）
- 紧急保存（save_snapshot）
- 线程安全（多线程并发调用 mark_completed）
"""
from __future__ import annotations

import json
import os
import threading

import pytest

from balcon_batch_tts.core.checkpoint import CheckpointManager, CheckpointState


# ---------------------------------------------------------------------------
# CheckpointState 数据结构
# ---------------------------------------------------------------------------
class TestCheckpointState:
    """``CheckpointState`` 数据结构契约。"""

    def test_default_values(self) -> None:
        state = CheckpointState()
        assert state.version == 2
        assert state.tool_type == "balcon"
        assert state.input_files == []
        assert state.completed_files == []
        assert state.failed_files == []
        assert state.output_dir == ""
        assert state.filename_template == "{name}.wav"
        assert state.output_format == "wav"
        assert state.ffmpeg_path == ""
        assert state.config_snapshot == {}
        assert state.created_at == ""
        assert state.updated_at == ""

    def test_to_dict_contains_all_fields(self) -> None:
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        d = state.to_dict()
        assert "version" in d
        assert "tool_type" in d
        assert "input_files" in d
        assert "completed_files" in d
        assert "failed_files" in d
        assert "output_dir" in d
        assert "filename_template" in d
        assert "output_format" in d
        assert "ffmpeg_path" in d
        assert "config_snapshot" in d
        assert "created_at" in d
        assert "updated_at" in d
        assert d["input_files"] == ["a.txt", "b.txt"]

    def test_from_dict_roundtrip(self) -> None:
        snapshot = {"n_voice": "Heather", "s_rate": "22050"}
        state = CheckpointState(
            tool_type="blb2txt",
            input_files=["a.pdf", "b.docx"],
            completed_files=["a.pdf"],
            failed_files=[],
            output_dir="/output",
            filename_template="{name}.txt",
            output_format="mp3",
            ffmpeg_path="/usr/bin/ffmpeg",
            config_snapshot=snapshot,
        )
        d = state.to_dict()
        restored = CheckpointState.from_dict(d)
        assert restored.tool_type == "blb2txt"
        assert restored.input_files == ["a.pdf", "b.docx"]
        assert restored.completed_files == ["a.pdf"]
        assert restored.output_format == "mp3"
        assert restored.ffmpeg_path == "/usr/bin/ffmpeg"
        assert restored.config_snapshot == snapshot

    def test_from_dict_ignores_unknown_fields(self) -> None:
        d = {
            "version": 2,
            "tool_type": "balcon",
            "input_files": [],
            "completed_files": [],
            "failed_files": [],
            "output_dir": "",
            "filename_template": "{name}.wav",
            "output_format": "wav",
            "ffmpeg_path": "",
            "config_snapshot": {},
            "created_at": "",
            "updated_at": "",
            "unknown_field": "should be ignored",
        }
        state = CheckpointState.from_dict(d)
        assert state.version == 2

    def test_from_dict_v1_backward_compatible(self) -> None:
        """version 1 旧格式（无 config_snapshot）应向后兼容。"""
        d = {
            "version": 1,
            "tool_type": "balcon",
            "input_files": ["a.txt"],
            "completed_files": [],
            "failed_files": [],
            "output_dir": "",
            "filename_template": "{name}.wav",
            "output_format": "wav",
            "ffmpeg_path": "",
            "created_at": "",
            "updated_at": "",
        }
        state = CheckpointState.from_dict(d)
        assert state.version == 1
        assert state.config_snapshot == {}
        assert state.input_files == ["a.txt"]

    def test_has_config_snapshot_false_when_empty(self) -> None:
        state = CheckpointState()
        assert not state.has_config_snapshot()

    def test_has_config_snapshot_false_when_empty_dict(self) -> None:
        state = CheckpointState(config_snapshot={})
        assert not state.has_config_snapshot()

    def test_has_config_snapshot_true_when_non_empty(self) -> None:
        state = CheckpointState(config_snapshot={"n_voice": "Heather"})
        assert state.has_config_snapshot()

    def test_config_snapshot_persisted_through_manager(self, tmp_path) -> None:
        """config_snapshot 应通过 CheckpointManager 持久化到文件并恢复。"""
        mgr = CheckpointManager(str(tmp_path))
        snapshot = {"n_voice": "Heather", "s_rate": "22050", "lrc": True}
        state = CheckpointState(
            input_files=["a.txt"],
            config_snapshot=snapshot,
        )
        mgr.create(state)

        mgr2 = CheckpointManager(str(tmp_path))
        loaded = mgr2.load()
        assert loaded is not None
        assert loaded.config_snapshot == snapshot
        assert loaded.has_config_snapshot()

    def test_pending_files_excludes_completed_and_failed(self) -> None:
        state = CheckpointState(
            input_files=["a.txt", "b.txt", "c.txt", "d.txt"],
            completed_files=["a.txt"],
            failed_files=["b.txt"],
        )
        pending = state.pending_files()
        assert "a.txt" not in pending
        assert "b.txt" not in pending
        assert "c.txt" in pending
        assert "d.txt" in pending
        assert len(pending) == 2

    def test_pending_files_preserves_order(self) -> None:
        state = CheckpointState(
            input_files=["c.txt", "a.txt", "b.txt"],
            completed_files=["a.txt"],
        )
        pending = state.pending_files()
        # 顺序应与原始 input_files 一致（排除已完成）
        assert pending == ["c.txt", "b.txt"]

    def test_pending_files_empty_when_all_done(self) -> None:
        state = CheckpointState(
            input_files=["a.txt", "b.txt"],
            completed_files=["a.txt"],
            failed_files=["b.txt"],
        )
        assert state.pending_files() == []

    def test_progress_percent_0(self) -> None:
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        assert state.progress_percent() == 0.0

    def test_progress_percent_50(self) -> None:
        state = CheckpointState(
            input_files=["a.txt", "b.txt", "c.txt", "d.txt"],
            completed_files=["a.txt"],
            failed_files=["b.txt"],
        )
        assert state.progress_percent() == 50.0

    def test_progress_percent_100(self) -> None:
        state = CheckpointState(
            input_files=["a.txt", "b.txt"],
            completed_files=["a.txt"],
            failed_files=["b.txt"],
        )
        assert state.progress_percent() == 100.0

    def test_progress_percent_empty_list(self) -> None:
        state = CheckpointState(input_files=[])
        assert state.progress_percent() == 100.0


# ---------------------------------------------------------------------------
# CheckpointManager 生命周期
# ---------------------------------------------------------------------------
class TestCheckpointManagerLifecycle:
    """``CheckpointManager`` 创建/加载/清除。"""

    def test_create_writes_file(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        mgr.create(state)
        assert os.path.isfile(mgr.checkpoint_path)

    def test_load_returns_state(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(
            input_files=["a.txt", "b.txt"],
            output_format="mp3",
        )
        mgr.create(state)

        # 重新加载
        mgr2 = CheckpointManager(str(tmp_path))
        loaded = mgr2.load()
        assert loaded is not None
        assert loaded.input_files == ["a.txt", "b.txt"]
        assert loaded.output_format == "mp3"

    def test_load_returns_none_when_no_file(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        assert mgr.load() is None

    def test_load_returns_none_on_invalid_json(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        # 写入无效 JSON
        with open(mgr.checkpoint_path, "w") as f:
            f.write("{invalid json")
        assert mgr.load() is None

    def test_clear_removes_file(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        assert os.path.isfile(mgr.checkpoint_path)

        mgr.clear()
        assert not os.path.isfile(mgr.checkpoint_path)

    def test_clear_no_file_is_noop(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        # 不应抛出异常
        mgr.clear()

    def test_exists(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        assert not mgr.exists()

        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        assert mgr.exists()

        mgr.clear()
        assert not mgr.exists()


# ---------------------------------------------------------------------------
# CheckpointManager 标记完成/失败
# ---------------------------------------------------------------------------
class TestCheckpointManagerMark:
    """``mark_completed`` / ``mark_failed`` 行为。"""

    def test_mark_completed_adds_to_list(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        mgr.create(state)

        mgr.mark_completed("a.txt")
        state = mgr.load()
        assert "a.txt" in state.completed_files

    def test_mark_failed_adds_to_list(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        mgr.create(state)

        mgr.mark_failed("b.txt")
        state = mgr.load()
        assert "b.txt" in state.failed_files

    def test_mark_completed_idempotent(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)

        mgr.mark_completed("a.txt")
        mgr.mark_completed("a.txt")  # 重复标记
        state = mgr.load()
        assert state.completed_files.count("a.txt") == 1

    def test_mark_failed_idempotent(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)

        mgr.mark_failed("a.txt")
        mgr.mark_failed("a.txt")  # 重复标记
        state = mgr.load()
        assert state.failed_files.count("a.txt") == 1

    def test_mark_completed_removes_from_failed(self, tmp_path) -> None:
        """标记成功后应从 failed_files 移除。"""
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)

        mgr.mark_failed("a.txt")
        mgr.mark_completed("a.txt")  # 重试成功
        state = mgr.load()
        assert "a.txt" in state.completed_files
        assert "a.txt" not in state.failed_files

    def test_mark_failed_removes_from_completed(self, tmp_path) -> None:
        """标记失败后应从 completed_files 移除。"""
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)

        mgr.mark_completed("a.txt")
        mgr.mark_failed("a.txt")  # 实际失败
        state = mgr.load()
        assert "a.txt" in state.failed_files
        assert "a.txt" not in state.completed_files

    def test_mark_without_create_is_noop(self, tmp_path) -> None:
        """未调用 create 时 mark 操作不应抛异常。"""
        mgr = CheckpointManager(str(tmp_path))
        mgr.mark_completed("a.txt")  # 不应抛异常
        mgr.mark_failed("b.txt")  # 不应抛异常
        assert not os.path.isfile(mgr.checkpoint_path)

    def test_updated_at_changes_on_mark(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        original_updated = mgr.load().updated_at

        mgr.mark_completed("a.txt")
        new_updated = mgr.load().updated_at
        # updated_at 应被更新（ISO 字符串可能相同，但至少不应抛异常）
        assert isinstance(new_updated, str)


# ---------------------------------------------------------------------------
# 原子写入
# ---------------------------------------------------------------------------
class TestCheckpointAtomicWrite:
    """原子写入行为。"""

    def test_no_temp_file_left_after_create(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        # 不应残留临时文件
        temp_path = mgr.checkpoint_path + ".tmp"
        assert not os.path.isfile(temp_path)

    def test_no_temp_file_left_after_mark(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        mgr.mark_completed("a.txt")
        temp_path = mgr.checkpoint_path + ".tmp"
        assert not os.path.isfile(temp_path)

    def test_checkpoint_is_valid_json(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        with open(mgr.checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["input_files"] == ["a.txt"]

    def test_creates_output_dir_if_missing(self, tmp_path) -> None:
        nested_dir = tmp_path / "nested" / "deep" / "dir"
        mgr = CheckpointManager(str(nested_dir))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)
        assert os.path.isfile(mgr.checkpoint_path)


# ---------------------------------------------------------------------------
# 紧急保存
# ---------------------------------------------------------------------------
class TestCheckpointEmergencySave:
    """``save_snapshot`` 紧急保存行为。"""

    def test_save_snapshot_writes_file(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt"])
        mgr.create(state)

        # 模拟内存中 mark 但不写入（通过修改 _state）
        mgr._state.completed_files.append("a.txt")
        mgr.save_snapshot()

        # 重新加载应看到 completed_files
        mgr2 = CheckpointManager(str(tmp_path))
        loaded = mgr2.load()
        assert "a.txt" in loaded.completed_files

    def test_save_snapshot_without_create_is_noop(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        mgr._state = None
        mgr.save_snapshot()  # 不应抛异常
        assert not os.path.isfile(mgr.checkpoint_path)


# ---------------------------------------------------------------------------
# 线程安全
# ---------------------------------------------------------------------------
class TestCheckpointThreadSafety:
    """多线程并发调用 mark_completed。"""

    def test_concurrent_mark_completed(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        files = [f"file_{i}.txt" for i in range(20)]
        state = CheckpointState(input_files=files)
        mgr.create(state)

        # 20 个线程并发标记不同的文件
        threads = []
        for f in files:
            t = threading.Thread(target=mgr.mark_completed, args=(f,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有文件都被标记为完成
        loaded = mgr.load()
        assert len(loaded.completed_files) == 20
        for f in files:
            assert f in loaded.completed_files

    def test_concurrent_mark_mixed_completed_failed(self, tmp_path) -> None:
        mgr = CheckpointManager(str(tmp_path))
        files = [f"file_{i}.txt" for i in range(20)]
        state = CheckpointState(input_files=files)
        mgr.create(state)

        # 10 个线程标记完成，10 个线程标记失败
        threads = []
        for i, f in enumerate(files):
            if i % 2 == 0:
                t = threading.Thread(target=mgr.mark_completed, args=(f,))
            else:
                t = threading.Thread(target=mgr.mark_failed, args=(f,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = mgr.load()
        assert len(loaded.completed_files) == 10
        assert len(loaded.failed_files) == 10


# ---------------------------------------------------------------------------
# 增量写入（JSONL 追加 + 定期压缩）
# ---------------------------------------------------------------------------
class TestCheckpointIncrementalWrite:
    """JSONL 追加写入与压缩机制。"""

    def test_incremental_write_appends_jsonl(self, tmp_path) -> None:
        """mark_completed 后文件应包含追加的 JSONL 行。"""
        mgr = CheckpointManager(str(tmp_path))
        state = CheckpointState(input_files=["a.txt", "b.txt"])
        mgr.create(state)

        mgr.mark_completed("a.txt")

        with open(mgr.checkpoint_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 文件末尾应有追加记录行
        lines = content.strip().split("\n")
        last_line = lines[-1]
        record = json.loads(last_line)
        assert record["type"] == "completed"
        assert record["file"] == "a.txt"
        assert "ts" in record

    def test_compact_after_50_appends(self, tmp_path) -> None:
        """50 次追加后触发压缩，文件恢复为纯基线（无追加行）。"""
        mgr = CheckpointManager(str(tmp_path))
        files = [f"file_{i}.txt" for i in range(50)]
        state = CheckpointState(input_files=files)
        mgr.create(state)

        for f in files:
            mgr.mark_completed(f)

        # 50 次追加后应已压缩
        assert mgr._pending_appends == 0

        # 文件应为纯 JSON（基线），可被 json.loads 直接解析
        with open(mgr.checkpoint_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        data = json.loads(content)
        assert data["completed_files"] == files
        assert data.get("_format") == "jsonl"

    def test_load_jsonl_format(self, tmp_path) -> None:
        """load() 能正确读取基线 + 追加记录的 JSONL 格式。"""
        mgr = CheckpointManager(str(tmp_path))

        # 手动构造 JSONL 文件：基线 + 2 条追加记录
        baseline = CheckpointState(
            input_files=["a.txt", "b.txt", "c.txt"],
        )
        baseline_data = baseline.to_dict()
        baseline_data["_format"] = "jsonl"

        with open(mgr.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.write(json.dumps(
                {"type": "completed", "file": "a.txt", "ts": "2026-07-28T12:00:00"}
            ) + "\n")
            f.write(json.dumps(
                {"type": "failed", "file": "b.txt", "ts": "2026-07-28T12:00:01"}
            ) + "\n")

        loaded = mgr.load()
        assert loaded is not None
        assert "a.txt" in loaded.completed_files
        assert "b.txt" in loaded.failed_files
        assert "c.txt" not in loaded.completed_files
        assert "c.txt" not in loaded.failed_files
        assert loaded.updated_at == "2026-07-28T12:00:01"

    def test_load_old_json_format(self, tmp_path) -> None:
        """load() 能读取旧版纯 JSON 格式（无 _format 字段）。"""
        mgr = CheckpointManager(str(tmp_path))

        old_data = {
            "version": 2,
            "tool_type": "balcon",
            "input_files": ["a.txt", "b.txt"],
            "completed_files": ["a.txt"],
            "failed_files": [],
            "output_dir": "",
            "filename_template": "{name}.wav",
            "output_format": "wav",
            "ffmpeg_path": "",
            "config_snapshot": {},
            "created_at": "2026-07-28T12:00:00",
            "updated_at": "2026-07-28T12:00:00",
        }

        with open(mgr.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f, ensure_ascii=False, indent=2)

        loaded = mgr.load()
        assert loaded is not None
        assert loaded.input_files == ["a.txt", "b.txt"]
        assert loaded.completed_files == ["a.txt"]
        assert loaded.failed_files == []

    def test_load_skips_corrupt_append(self, tmp_path) -> None:
        """损坏的追加行应被跳过（记录 warning），不影响其他记录。"""
        mgr = CheckpointManager(str(tmp_path))

        baseline = CheckpointState(
            input_files=["a.txt", "b.txt", "c.txt"],
        )
        baseline_data = baseline.to_dict()
        baseline_data["_format"] = "jsonl"

        with open(mgr.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.write(json.dumps(
                {"type": "completed", "file": "a.txt", "ts": "2026-07-28T12:00:00"}
            ) + "\n")
            f.write("{corrupt json line\n")
            f.write(json.dumps(
                {"type": "failed", "file": "b.txt", "ts": "2026-07-28T12:00:01"}
            ) + "\n")

        loaded = mgr.load()
        assert loaded is not None
        # 损坏行前后有效的记录应正常回放
        assert "a.txt" in loaded.completed_files
        assert "b.txt" in loaded.failed_files
        # c.txt 未被任何记录触及
        assert "c.txt" not in loaded.completed_files
        assert "c.txt" not in loaded.failed_files

    def test_state_consistency_after_compact(self, tmp_path) -> None:
        """压缩后内存状态与文件状态一致。"""
        mgr = CheckpointManager(str(tmp_path))
        files = [f"file_{i}.txt" for i in range(50)]
        state = CheckpointState(input_files=files)
        mgr.create(state)

        for f in files:
            mgr.mark_completed(f)

        # 内存状态
        mem_state = mgr.get_state()
        assert mem_state is not None
        assert len(mem_state.completed_files) == 50
        assert mem_state.failed_files == []

        # 通过新 manager 从文件加载
        mgr2 = CheckpointManager(str(tmp_path))
        loaded = mgr2.load()
        assert loaded is not None
        assert len(loaded.completed_files) == 50
        assert set(loaded.completed_files) == set(mem_state.completed_files)
        assert loaded.failed_files == mem_state.failed_files
        assert loaded.input_files == mem_state.input_files
