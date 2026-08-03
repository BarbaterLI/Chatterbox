"""sapi_config 模块单元测试。

验证 :class:`SapiConfig` 的默认值、``to_dict`` / ``from_dict`` 序列化往返、
多余键忽略与缺失键回退，以及模块不依赖 PySide6 的纯核心层约束。
"""
from __future__ import annotations

import inspect
from dataclasses import fields

import pytest

from balcon_batch_tts.core import sapi_config
from balcon_batch_tts.core.sapi_config import SapiConfig


# ---------------------------------------------------------------------------
# create_default
# ---------------------------------------------------------------------------
class TestCreateDefault:
    """``create_default`` 应返回全默认值实例。"""

    def test_create_default_returns_instance(self) -> None:
        config = SapiConfig.create_default()
        assert isinstance(config, SapiConfig)

    def test_create_default_all_fields_match_defaults(self) -> None:
        config = SapiConfig.create_default()
        for f in fields(SapiConfig):
            value = getattr(config, f.name)
            assert value == f.default, (
                f"字段 {f.name} 应为 {f.default!r}，实际为 {value!r}"
            )

    def test_create_default_voice_name_empty(self) -> None:
        assert SapiConfig.create_default().voice_name == ""

    def test_create_default_rate_zero(self) -> None:
        assert SapiConfig.create_default().rate == 0

    def test_create_default_volume_max(self) -> None:
        assert SapiConfig.create_default().volume == 100

    def test_create_default_pitch_zero(self) -> None:
        assert SapiConfig.create_default().pitch == 0

    def test_create_default_input_encoding_utf8(self) -> None:
        assert SapiConfig.create_default().input_encoding == "utf-8"


# ---------------------------------------------------------------------------
# audio_format 字段
# ---------------------------------------------------------------------------
class TestAudioFormat:
    """``audio_format`` 字段的默认值与序列化往返。"""

    def test_audio_format_default(self) -> None:
        """``SapiConfig()`` 默认 ``audio_format == 22``（16kHz/Mono）。"""
        assert SapiConfig().audio_format == 22

    def test_audio_format_to_dict_contains_field(self) -> None:
        """``to_dict`` 结果应包含 ``audio_format`` 键。"""
        data = SapiConfig.create_default().to_dict()
        assert "audio_format" in data
        assert data["audio_format"] == 22

    def test_audio_format_from_dict_restores_field(self) -> None:
        """``from_dict`` 应正确还原非默认 ``audio_format`` 值。"""
        data = {
            "voice_name": "",
            "rate": 0,
            "volume": 100,
            "pitch": 0,
            "input_encoding": "utf-8",
            "audio_format": 31,
        }
        config = SapiConfig.from_dict(data)
        assert config.audio_format == 31


# ---------------------------------------------------------------------------
# max_text_bytes 字段
# ---------------------------------------------------------------------------
class TestMaxTextBytes:
    """``max_text_bytes`` 字段的默认值与序列化往返（Task 16 内存预算）。"""

    def test_max_text_bytes_default(self) -> None:
        """``SapiConfig()`` 默认 ``max_text_bytes == 262144``（256KB）。"""
        assert SapiConfig().max_text_bytes == 262144

    def test_max_text_bytes_to_dict_contains_field(self) -> None:
        """``to_dict`` 结果应包含 ``max_text_bytes`` 键。"""
        data = SapiConfig.create_default().to_dict()
        assert "max_text_bytes" in data
        assert data["max_text_bytes"] == 262144

    def test_max_text_bytes_from_dict_restores_field(self) -> None:
        """``from_dict`` 应正确还原非默认 ``max_text_bytes`` 值。"""
        data = {
            "voice_name": "",
            "rate": 0,
            "volume": 100,
            "pitch": 0,
            "input_encoding": "utf-8",
            "audio_format": 22,
            "max_text_bytes": 524288,
        }
        config = SapiConfig.from_dict(data)
        assert config.max_text_bytes == 524288

    def test_max_text_bytes_missing_key_uses_default(self) -> None:
        """``from_dict`` 缺失 ``max_text_bytes`` 时使用默认值（向后兼容）。"""
        data = {
            "voice_name": "",
            "rate": 0,
            "volume": 100,
            "pitch": 0,
            "input_encoding": "utf-8",
            "audio_format": 22,
        }
        config = SapiConfig.from_dict(data)
        assert config.max_text_bytes == 262144


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------
class TestToDict:
    """``to_dict`` 应返回包含全部 dataclass 字段的字典。"""

    def test_to_dict_contains_all_fields(self) -> None:
        config = SapiConfig.create_default()
        data = config.to_dict()
        for f in fields(SapiConfig):
            assert f.name in data, f"字段 {f.name} 应在 to_dict 结果中"

    def test_to_dict_excludes_classvar(self) -> None:
        """``_FIELD_TO_OPTION`` 与 ``_schema`` 为 ClassVar，不应出现在 to_dict 中。"""
        data = SapiConfig.create_default().to_dict()
        assert "_FIELD_TO_OPTION" not in data
        assert "_schema" not in data

    def test_to_dict_values_match(self) -> None:
        config = SapiConfig(
            voice_name="Anna",
            rate=5,
            volume=80,
            pitch=-3,
            input_encoding="gbk",
        )
        data = config.to_dict()
        assert data["voice_name"] == "Anna"
        assert data["rate"] == 5
        assert data["volume"] == 80
        assert data["pitch"] == -3
        assert data["input_encoding"] == "gbk"

    def test_to_dict_default_values(self) -> None:
        data = SapiConfig.create_default().to_dict()
        assert data == {
            "voice_name": "",
            "rate": 0,
            "volume": 100,
            "pitch": 0,
            "input_encoding": "utf-8",
            "audio_format": 22,
            "max_text_bytes": 262144,
        }


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------
class TestFromDict:
    """``from_dict`` 应正确重建配置实例。"""

    def test_from_dict_reconstructs_all_fields(self) -> None:
        data = {
            "voice_name": "David",
            "rate": 3,
            "volume": 75,
            "pitch": 2,
            "input_encoding": "big5",
        }
        config = SapiConfig.from_dict(data)
        assert config.voice_name == "David"
        assert config.rate == 3
        assert config.volume == 75
        assert config.pitch == 2
        assert config.input_encoding == "big5"

    def test_from_dict_ignores_extra_keys(self) -> None:
        """多余键应被忽略，不引发异常。"""
        config = SapiConfig.from_dict(
            {"voice_name": "Anna", "extra_key": "ignored", "another": 123}
        )
        assert config.voice_name == "Anna"
        assert not hasattr(config, "extra_key")

    def test_from_dict_missing_keys_uses_defaults(self) -> None:
        """缺失键应使用字段默认值。"""
        config = SapiConfig.from_dict({})
        assert config == SapiConfig.create_default()

    def test_from_dict_partial_dict_uses_defaults(self) -> None:
        config = SapiConfig.from_dict({"rate": 5})
        assert config.rate == 5
        assert config.voice_name == ""
        assert config.volume == 100
        assert config.pitch == 0
        assert config.input_encoding == "utf-8"

    def test_from_dict_empty_dict_equals_default(self) -> None:
        assert SapiConfig.from_dict({}) == SapiConfig.create_default()


# ---------------------------------------------------------------------------
# to_dict → from_dict 往返
# ---------------------------------------------------------------------------
class TestRoundTrip:
    """``to_dict`` → ``from_dict`` 往返应保持字段值不变。"""

    def test_roundtrip_default(self) -> None:
        original = SapiConfig.create_default()
        restored = SapiConfig.from_dict(original.to_dict())
        assert restored == original

    def test_roundtrip_custom_values(self) -> None:
        original = SapiConfig(
            voice_name="Microsoft Anna",
            rate=-5,
            volume=50,
            pitch=7,
            input_encoding="gbk",
        )
        restored = SapiConfig.from_dict(original.to_dict())
        assert restored == original

    def test_roundtrip_preserves_all_fields(self) -> None:
        original = SapiConfig(
            voice_name="TestVoice",
            rate=10,
            volume=0,
            pitch=-10,
            input_encoding="latin-1",
        )
        data = original.to_dict()
        restored = SapiConfig.from_dict(data)
        for f in fields(SapiConfig):
            assert getattr(restored, f.name) == getattr(original, f.name)


# ---------------------------------------------------------------------------
# 纯核心层约束：不导入 PySide6
# ---------------------------------------------------------------------------
class TestNoPySide6Import:
    """``sapi_config`` 模块为纯核心层，不应导入 PySide6。"""

    def test_no_pyside6_import_in_source(self) -> None:
        """源码中不应存在 PySide6 的 import 语句。"""
        source = inspect.getsource(sapi_config)
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "PySide6" not in stripped, (
                    f"sapi_config 不应导入 PySide6，发现: {stripped}"
                )

    def test_no_pyside6_in_module_namespace(self) -> None:
        """模块命名空间中不应包含 PySide6 相关名称。"""
        for name in dir(sapi_config):
            assert "PySide6" not in name, (
                f"sapi_config 命名空间不应包含 PySide6: {name}"
            )

    def test_module_is_not_gui_module(self) -> None:
        """模块不应属于 gui 包。"""
        assert "gui" not in sapi_config.__name__
        assert "core" in sapi_config.__name__
