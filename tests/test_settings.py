"""settings 模块单元测试。

验证 :class:`AppSettings` 默认值、blb2txt 路径辅助函数、序列化往返
与旧 settings.json（无 blb2txt 字段）的向后兼容性。
"""
from __future__ import annotations

import os.path

from balcon_batch_tts.persistence.settings import (
    AppSettings,
    get_default_balcon_path,
    get_default_blb2txt_lite_path,
    get_default_blb2txt_path,
)


# ---------------------------------------------------------------------------
# 默认路径辅助函数
# ---------------------------------------------------------------------------
class TestDefaultPaths:
    """``get_default_blb2txt_path`` / ``get_default_blb2txt_lite_path`` 行为。"""

    def test_get_default_blb2txt_path_is_absolute(self) -> None:
        path = get_default_blb2txt_path()
        assert os.path.isabs(path), f"{path!r} 应为绝对路径"

    def test_get_default_blb2txt_path_ends_with_blb2txt_exe(self) -> None:
        path = get_default_blb2txt_path()
        assert path.endswith(os.path.join("blb2txt", "blb2txt.exe")), (
            f"{path!r} 应以 blb2txt/blb2txt.exe 结尾"
        )

    def test_get_default_blb2txt_lite_path_is_absolute(self) -> None:
        path = get_default_blb2txt_lite_path()
        assert os.path.isabs(path), f"{path!r} 应为绝对路径"

    def test_get_default_blb2txt_lite_path_ends_with_without_pdf(self) -> None:
        path = get_default_blb2txt_lite_path()
        expected_suffix = os.path.join("blb2txt", "Without PDF", "blb2txt.exe")
        assert path.endswith(expected_suffix), (
            f"{path!r} 应以 blb2txt/Without PDF/blb2txt.exe 结尾"
        )

    def test_blb2txt_path_differs_from_lite_path(self) -> None:
        """完整版与精简版默认路径不应相同。"""
        assert get_default_blb2txt_path() != get_default_blb2txt_lite_path()

    def test_blb2txt_path_differs_from_balcon_path(self) -> None:
        assert get_default_blb2txt_path() != get_default_balcon_path()


# ---------------------------------------------------------------------------
# AppSettings 默认实例
# ---------------------------------------------------------------------------
class TestAppSettingsDefaults:
    """``AppSettings`` 默认实例应包含 blb2txt 相关字段。"""

    def test_default_instance_has_blb2txt_path(self) -> None:
        settings = AppSettings()
        assert hasattr(settings, "blb2txt_path")
        assert isinstance(settings.blb2txt_path, str)
        assert settings.blb2txt_path == get_default_blb2txt_path()

    def test_default_instance_has_blb2txt_lite_path(self) -> None:
        settings = AppSettings()
        assert hasattr(settings, "blb2txt_lite_path")
        assert isinstance(settings.blb2txt_lite_path, str)
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()

    def test_default_instance_balcon_path_unchanged(self) -> None:
        """既有 balcon_path 字段默认值不应被破坏。"""
        settings = AppSettings()
        assert settings.balcon_path == get_default_balcon_path()

    def test_default_instance_other_fields_unchanged(self) -> None:
        """既有非路径字段默认值不应被破坏。"""
        settings = AppSettings()
        assert settings.max_concurrency == 2
        assert settings.last_output_dir == ""
        assert settings.window_geometry == ""
        assert settings.last_preset_dir == ""
        assert settings.filename_template == "{name}.wav"

    def test_default_instance_new_fields_defaults(self) -> None:
        """新增字段应有正确的默认值。"""
        settings = AppSettings()
        assert settings.theme == "auto"
        assert settings.density == "comfortable"
        assert settings.font_scale == 1.0
        assert settings.collapsed_groups == {}
        assert settings.recent_files == []
        assert settings.recent_presets == []
        # 容器字段应为独立实例（default_factory 防止共享）
        assert settings.collapsed_groups is not AppSettings().collapsed_groups
        assert settings.recent_files is not AppSettings().recent_files
        assert settings.recent_presets is not AppSettings().recent_presets


# ---------------------------------------------------------------------------
# 向后兼容：旧 settings.json 无 blb2txt 字段
# ---------------------------------------------------------------------------
class TestBackwardCompatibility:
    """旧 settings.json（无 blb2txt_path / blb2txt_lite_path）应使用默认值。"""

    def test_from_dict_old_format_uses_defaults(self) -> None:
        """旧格式 dict 仅含 balcon 时代字段，缺失 blb2txt 字段时使用默认值。"""
        old_data = {
            "balcon_path": "C:/custom/balcon.exe",
            "max_concurrency": 4,
            "last_output_dir": "D:/output",
            "window_geometry": "100x100+50+50",
            "last_preset_dir": "E:/presets",
            "filename_template": "{name}_{voice}.wav",
        }
        settings = AppSettings.from_dict(old_data)
        # 既有字段应保留 dict 中的值
        assert settings.balcon_path == "C:/custom/balcon.exe"
        assert settings.max_concurrency == 4
        assert settings.last_output_dir == "D:/output"
        assert settings.window_geometry == "100x100+50+50"
        assert settings.last_preset_dir == "E:/presets"
        assert settings.filename_template == "{name}_{voice}.wav"
        # 缺失字段应使用 default_factory
        assert settings.blb2txt_path == get_default_blb2txt_path()
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()

    def test_from_dict_partial_blb2txt_fields(self) -> None:
        """仅含 blb2txt_path 但缺失 blb2txt_lite_path 时正确处理。"""
        partial_data = {
            "blb2txt_path": "C:/custom/blb2txt.exe",
        }
        settings = AppSettings.from_dict(partial_data)
        assert settings.blb2txt_path == "C:/custom/blb2txt.exe"
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()
        # 其他字段也应使用默认值
        assert settings.balcon_path == get_default_balcon_path()
        assert settings.max_concurrency == 2

    def test_from_dict_empty_dict_uses_all_defaults(self) -> None:
        settings = AppSettings.from_dict({})
        assert settings.balcon_path == get_default_balcon_path()
        assert settings.blb2txt_path == get_default_blb2txt_path()
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()

    def test_from_dict_ignores_unknown_keys(self) -> None:
        """未知键（未来字段或拼写错误）不应导致异常。"""
        data = {
            "balcon_path": "C:/balcon.exe",
            "unknown_future_field": "some_value",
            "blb2txt_path": "C:/blb2txt.exe",
        }
        settings = AppSettings.from_dict(data)
        assert settings.balcon_path == "C:/balcon.exe"
        assert settings.blb2txt_path == "C:/blb2txt.exe"
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()

    def test_from_dict_old_format_without_new_fields_uses_defaults(self) -> None:
        """旧 JSON（不含 theme/density/font_scale/collapsed_groups/recent_files/recent_presets）应使用默认值。"""
        old_data = {
            "balcon_path": "C:/balcon/balcon.exe",
            "max_concurrency": 4,
            "output_format": "mp3",
            "ffmpeg_path": "C:/ffmpeg.exe",
        }
        settings = AppSettings.from_dict(old_data)
        # 既有字段保留
        assert settings.balcon_path == "C:/balcon/balcon.exe"
        assert settings.max_concurrency == 4
        assert settings.output_format == "mp3"
        assert settings.ffmpeg_path == "C:/ffmpeg.exe"
        # 新字段使用默认值
        assert settings.theme == "auto"
        assert settings.density == "comfortable"
        assert settings.font_scale == 1.0
        assert settings.collapsed_groups == {}
        assert settings.recent_files == []
        assert settings.recent_presets == []


# ---------------------------------------------------------------------------
# 序列化往返
# ---------------------------------------------------------------------------
class TestSerializationRoundtrip:
    """``to_dict`` → ``from_dict`` 往返一致性。"""

    def test_roundtrip_preserves_all_fields(self) -> None:
        original = AppSettings(
            balcon_path="C:/balcon/balcon.exe",
            blb2txt_path="C:/blb2txt/blb2txt.exe",
            blb2txt_lite_path="C:/blb2txt/Without PDF/blb2txt.exe",
            max_concurrency=8,
            last_output_dir="D:/out",
            window_geometry="200x200",
            last_preset_dir="E:/presets",
            filename_template="{name}_{index}.wav",
        )
        data = original.to_dict()
        restored = AppSettings.from_dict(data)
        assert restored == original

    def test_to_dict_contains_blb2txt_fields(self) -> None:
        """to_dict 输出必须包含 blb2txt_path 与 blb2txt_lite_path 键。"""
        settings = AppSettings()
        data = settings.to_dict()
        assert "blb2txt_path" in data
        assert "blb2txt_lite_path" in data
        assert data["blb2txt_path"] == settings.blb2txt_path
        assert data["blb2txt_lite_path"] == settings.blb2txt_lite_path

    def test_to_dict_contains_balcon_path(self) -> None:
        """既有 balcon_path 字段不应丢失。"""
        settings = AppSettings()
        data = settings.to_dict()
        assert "balcon_path" in data

    def test_roundtrip_default_instance(self) -> None:
        """默认实例往返后应保持相等。"""
        original = AppSettings()
        restored = AppSettings.from_dict(original.to_dict())
        assert restored == original

    def test_roundtrip_with_custom_blb2txt_paths(self) -> None:
        """自定义 blb2txt 路径往返后应保持。"""
        original = AppSettings(
            blb2txt_path="D:/tools/blb2txt.exe",
            blb2txt_lite_path="D:/tools/lite/blb2txt.exe",
        )
        data = original.to_dict()
        restored = AppSettings.from_dict(data)
        assert restored.blb2txt_path == "D:/tools/blb2txt.exe"
        assert restored.blb2txt_lite_path == "D:/tools/lite/blb2txt.exe"
        assert restored == original

    def test_roundtrip_new_fields(self) -> None:
        """新字段序列化/反序列化往返一致性。"""
        original = AppSettings(
            theme="dark",
            density="compact",
            font_scale=1.25,
            collapsed_groups={
                "balcon": ["语音音频", "字幕与同步"],
                "blb2txt": ["字幕与同步"],
            },
            recent_files=["C:/a.txt", "C:/b.txt", "C:/c.txt"],
            recent_presets=["C:/p1.json", "C:/p2.json"],
        )
        data = original.to_dict()
        restored = AppSettings.from_dict(data)
        assert restored == original
        # 逐字段验证，避免 dataclass __eq__ 在嵌套结构失败时定位困难
        assert restored.theme == "dark"
        assert restored.density == "compact"
        assert restored.font_scale == 1.25
        assert restored.collapsed_groups == {
            "balcon": ["语音音频", "字幕与同步"],
            "blb2txt": ["字幕与同步"],
        }
        assert restored.recent_files == ["C:/a.txt", "C:/b.txt", "C:/c.txt"]
        assert restored.recent_presets == ["C:/p1.json", "C:/p2.json"]

    def test_to_dict_serializes_collapsed_groups_nested_dict(self) -> None:
        """``collapsed_groups`` 嵌套 dict 应能被正确序列化。"""
        settings = AppSettings(
            collapsed_groups={"balcon": ["语音音频", "字幕与同步"]}
        )
        data = settings.to_dict()
        assert data["collapsed_groups"] == {"balcon": ["语音音频", "字幕与同步"]}
        # 确保是真正的 dict/list 结构（而非引用原对象），可被 json.dumps 序列化
        import json

        serialized = json.dumps(data, ensure_ascii=False)
        assert "语音音频" in serialized
        restored = AppSettings.from_dict(json.loads(serialized))
        assert restored.collapsed_groups == {"balcon": ["语音音频", "字幕与同步"]}

    def test_to_dict_serializes_recent_files_list(self) -> None:
        """``recent_files`` list 应能被正确序列化。"""
        files = [f"C:/path/file{i}.txt" for i in range(5)]
        settings = AppSettings(recent_files=files)
        data = settings.to_dict()
        assert data["recent_files"] == files
        assert isinstance(data["recent_files"], list)
        # 确保可被 json.dumps 序列化
        import json

        restored = AppSettings.from_dict(json.loads(json.dumps(data)))
        assert restored.recent_files == files

    def test_to_dict_contains_new_fields_keys(self) -> None:
        """``to_dict`` 输出必须包含所有新字段键。"""
        settings = AppSettings()
        data = settings.to_dict()
        for key in (
            "theme",
            "density",
            "font_scale",
            "collapsed_groups",
            "recent_files",
            "recent_presets",
        ):
            assert key in data, f"to_dict 缺少键 {key!r}"


# ---------------------------------------------------------------------------
# JSON 持久化
# ---------------------------------------------------------------------------
class TestJsonPersistence:
    """``save`` → ``load`` 文件持久化往返（tmp_path fixture）。"""

    def test_save_load_roundtrip(self, tmp_path) -> None:
        settings_path = tmp_path / "settings.json"
        original = AppSettings(
            balcon_path="C:/balcon.exe",
            blb2txt_path="C:/blb2txt.exe",
            blb2txt_lite_path="C:/lite/blb2txt.exe",
            max_concurrency=4,
        )
        original.save(str(settings_path))
        assert settings_path.exists()
        restored = AppSettings.load(str(settings_path))
        assert restored == original

    def test_load_missing_file_returns_defaults(self, tmp_path) -> None:
        """文件不存在时返回默认实例。"""
        missing = tmp_path / "nonexistent.json"
        settings = AppSettings.load(str(missing))
        assert settings.balcon_path == get_default_balcon_path()
        assert settings.blb2txt_path == get_default_blb2txt_path()
        assert settings.blb2txt_lite_path == get_default_blb2txt_lite_path()

    def test_saved_json_contains_blb2txt_fields(self, tmp_path) -> None:
        """保存的 JSON 文件应包含 blb2txt 字段。"""
        import json

        settings_path = tmp_path / "settings.json"
        settings = AppSettings()
        settings.save(str(settings_path))
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "blb2txt_path" in data
        assert "blb2txt_lite_path" in data
        assert data["blb2txt_path"] == settings.blb2txt_path
        assert data["blb2txt_lite_path"] == settings.blb2txt_lite_path
