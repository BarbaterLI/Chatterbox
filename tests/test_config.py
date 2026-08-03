"""config 模块单元测试。

验证 BalconConfig 的默认值、to_args 参数生成、validate 校验、
to_dict / from_dict 序列化往返。
"""
from __future__ import annotations

from dataclasses import MISSING, fields

import pytest

from balcon_batch_tts.core.config import BalconConfig


# ---------------------------------------------------------------------------
# create_default
# ---------------------------------------------------------------------------
class TestCreateDefault:
    """create_default 应返回全默认值实例。"""

    def test_create_default_returns_instance(self) -> None:
        config = BalconConfig.create_default()
        assert isinstance(config, BalconConfig)

    def test_create_default_all_fields_match_default(self) -> None:
        config = BalconConfig.create_default()
        for f in fields(BalconConfig):
            value = getattr(config, f.name)
            if f.default_factory is not MISSING:
                assert value == [], f"list 字段 {f.name} 应为空列表，实际为 {value!r}"
            else:
                assert value == f.default, (
                    f"字段 {f.name} 应为 {f.default!r}，实际为 {value!r}"
                )

    def test_create_default_list_fields_empty(self) -> None:
        config = BalconConfig.create_default()
        assert config.f_files == []
        assert config.fl_files == []
        assert config.t_texts == []
        assert config.ln_lines == []
        assert config.d_dicts == []
        assert config.voice1_langid == []

    def test_create_default_bool_fields_false(self) -> None:
        config = BalconConfig.create_default()
        bool_field_names = [
            "c_clipboard", "i_stdin", "o_stdout", "raw",
            "ignore_length", "delete_file", "sub", "sub_fit", "sub_fit_lib",
            "lrc", "lrc_sent", "lrc_para", "srt",
            "ignore_square_brackets", "ignore_curly_brackets",
            "ignore_angle_brackets", "ignore_round_brackets",
            "ignore_url", "ignore_comments", "voice1_roman", "voice1_digit",
        ]
        for name in bool_field_names:
            assert getattr(config, name) is False, f"{name} 应为 False"

    def test_create_default_none_fields_are_none(self) -> None:
        config = BalconConfig.create_default()
        none_field_names = [
            "encoding", "w_output", "n_voice", "id_langid",
            "s_rate", "p_pitch", "v_volume", "e_sentence_pause",
            "a_paragraph_pause", "b_device_index", "r_device_name",
            "fr_sample_rate", "bt_bit_depth", "ch_channels",
            "silence_begin", "silence_end", "sub_format", "sub_max",
            "lrc_length", "lrc_fname", "lrc_enc", "lrc_offset",
            "lrc_artist", "lrc_album", "lrc_title", "lrc_author",
            "lrc_creator", "srt_length", "srt_fname", "srt_enc",
            "vs_visemes", "voice1_name", "voice1_rate", "voice1_pitch",
            "voice1_volume", "voice1_length",
        ]
        for name in none_field_names:
            assert getattr(config, name) is None, f"{name} 应为 None"


# ---------------------------------------------------------------------------
# to_args
# ---------------------------------------------------------------------------
class TestToArgs:
    """to_args 按 schema 类型生成 balcon 命令行参数列表。"""

    def test_default_config_to_args_returns_empty_list(self) -> None:
        config = BalconConfig.create_default()
        assert config.to_args() == []

    def test_n_voice_to_args(self) -> None:
        config = BalconConfig.create_default()
        config.n_voice = "Emma"
        assert config.to_args() == ["-n", "Emma"]

    def test_s_rate_to_args(self) -> None:
        config = BalconConfig.create_default()
        config.s_rate = 2
        assert config.to_args() == ["-s", "2"]

    def test_lrc_flag_to_args(self) -> None:
        config = BalconConfig.create_default()
        config.lrc = True
        assert config.to_args() == ["-lrc"]

    def test_d_dicts_multiple_to_args(self) -> None:
        config = BalconConfig.create_default()
        config.d_dicts = ["a.bxd", "b.dic"]
        assert config.to_args() == ["-d", "a.bxd", "-d", "b.dic"]

    def test_c_clipboard_false_not_in_args(self) -> None:
        config = BalconConfig.create_default()
        assert "-c" not in config.to_args()

    def test_encoding_none_not_in_args(self) -> None:
        config = BalconConfig.create_default()
        assert "--encoding" not in config.to_args()

    def test_c_clipboard_true_in_args(self) -> None:
        config = BalconConfig.create_default()
        config.c_clipboard = True
        assert config.to_args() == ["-c"]

    def test_encoding_set_in_args(self) -> None:
        config = BalconConfig.create_default()
        config.encoding = "utf8"
        assert config.to_args() == ["--encoding", "utf8"]

    def test_multiple_fields_preserve_order(self) -> None:
        """多个字段同时设置时，输出顺序应与 _FIELD_TO_OPTION 声明顺序一致。"""
        config = BalconConfig.create_default()
        config.n_voice = "Emma"
        config.s_rate = 2
        config.lrc = True
        args = config.to_args()
        assert args == ["-n", "Emma", "-s", "2", "-lrc"]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------
class TestValidate:
    """validate 应根据 schema 的 min/max/choices 检查字段值。"""

    def test_default_config_validate_returns_empty(self) -> None:
        config = BalconConfig.create_default()
        assert config.validate() == []

    def test_s_rate_too_high_returns_error(self) -> None:
        config = BalconConfig.create_default()
        config.s_rate = 20
        errors = config.validate()
        assert len(errors) > 0
        assert any("-s" in e for e in errors)

    def test_s_rate_too_low_returns_error(self) -> None:
        config = BalconConfig.create_default()
        config.s_rate = -20
        errors = config.validate()
        assert len(errors) > 0
        assert any("-s" in e for e in errors)

    def test_v_volume_too_high_returns_error(self) -> None:
        config = BalconConfig.create_default()
        config.v_volume = 200
        errors = config.validate()
        assert len(errors) > 0
        assert any("-v" in e for e in errors)

    def test_fr_sample_rate_invalid_choice_returns_error(self) -> None:
        config = BalconConfig.create_default()
        config.fr_sample_rate = "99"
        errors = config.validate()
        assert len(errors) > 0
        assert any("-fr" in e for e in errors)

    def test_s_rate_valid_no_error(self) -> None:
        config = BalconConfig.create_default()
        config.s_rate = 5
        assert config.validate() == []

    def test_s_rate_boundary_values_no_error(self) -> None:
        config = BalconConfig.create_default()
        config.s_rate = -10
        assert config.validate() == []
        config.s_rate = 10
        assert config.validate() == []

    def test_fr_sample_rate_valid_choice_no_error(self) -> None:
        config = BalconConfig.create_default()
        config.fr_sample_rate = "44"
        assert config.validate() == []


# ---------------------------------------------------------------------------
# to_dict / from_dict 往返
# ---------------------------------------------------------------------------
class TestToFromDict:
    """to_dict / from_dict 应保持配置字段值不变。"""

    def test_roundtrip_preserves_fields(self) -> None:
        config = BalconConfig.create_default()
        config.n_voice = "Emma"
        config.s_rate = 5
        config.lrc = True
        config.d_dicts = ["a.bxd", "b.dic"]
        config.encoding = "utf8"
        config.v_volume = 80

        data = config.to_dict()
        restored = BalconConfig.from_dict(data)

        assert restored.n_voice == "Emma"
        assert restored.s_rate == 5
        assert restored.lrc is True
        assert restored.d_dicts == ["a.bxd", "b.dic"]
        assert restored.encoding == "utf8"
        assert restored.v_volume == 80

    def test_from_dict_ignores_extra_keys(self) -> None:
        config = BalconConfig.from_dict(
            {"n_voice": "Emma", "extra_key": "ignored", "another": 123}
        )
        assert config.n_voice == "Emma"

    def test_from_dict_missing_keys_use_defaults(self) -> None:
        config = BalconConfig.from_dict({})
        assert config == BalconConfig.create_default()

    def test_from_dict_list_none_becomes_empty(self) -> None:
        config = BalconConfig.from_dict(
            {"d_dicts": None, "f_files": None, "voice1_langid": None}
        )
        assert config.d_dicts == []
        assert config.f_files == []
        assert config.voice1_langid == []

    def test_to_dict_excludes_classvar(self) -> None:
        config = BalconConfig.create_default()
        data = config.to_dict()
        assert "_FIELD_TO_OPTION" not in data

    def test_to_dict_contains_all_dataclass_fields(self) -> None:
        config = BalconConfig.create_default()
        data = config.to_dict()
        for f in fields(BalconConfig):
            assert f.name in data

    def test_roundtrip_all_fields(self) -> None:
        """全部字段设置非默认值后往返仍应保持一致。"""
        config = BalconConfig.create_default()
        config.f_files = ["in1.txt", "in2.txt"]
        config.c_clipboard = True
        config.n_voice = "David"
        config.s_rate = 3
        config.v_volume = 75
        config.fr_sample_rate = "44"
        config.d_dicts = ["dict.bxd"]
        config.lrc = True
        config.srt = True
        config.ignore_square_brackets = True
        config.voice1_name = "Secondary"
        config.voice1_roman = True

        data = config.to_dict()
        restored = BalconConfig.from_dict(data)

        assert restored.f_files == ["in1.txt", "in2.txt"]
        assert restored.c_clipboard is True
        assert restored.n_voice == "David"
        assert restored.s_rate == 3
        assert restored.v_volume == 75
        assert restored.fr_sample_rate == "44"
        assert restored.d_dicts == ["dict.bxd"]
        assert restored.lrc is True
        assert restored.srt is True
        assert restored.ignore_square_brackets is True
        assert restored.voice1_name == "Secondary"
        assert restored.voice1_roman is True
