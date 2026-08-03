"""blb2txt_config 模块单元测试。

验证 Blb2txtConfig 的默认值、to_args 参数生成、validate 校验、
to_dict / from_dict 序列化往返。
"""
from __future__ import annotations

from dataclasses import MISSING, fields

import pytest

from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.blb2txt_schema import BLB2TXT_PARAMETER_SCHEMA
from balcon_batch_tts.core.parameter_schema import ParamKind


# ---------------------------------------------------------------------------
# create_default
# ---------------------------------------------------------------------------
class TestCreateDefault:
    """create_default 应返回全默认值实例。"""

    def test_create_default_returns_instance(self) -> None:
        config = Blb2txtConfig.create_default()
        assert isinstance(config, Blb2txtConfig)

    def test_create_default_field_count(self) -> None:
        """dataclass 字段总数应与 schema 参数总数一致（72）。"""
        dataclass_fields = [f for f in fields(Blb2txtConfig)]
        assert len(dataclass_fields) == len(BLB2TXT_PARAMETER_SCHEMA) == 72

    def test_create_default_all_fields_match_default(self) -> None:
        config = Blb2txtConfig.create_default()
        for f in fields(Blb2txtConfig):
            value = getattr(config, f.name)
            if f.default_factory is not MISSING:
                assert value == [], (
                    f"list 字段 {f.name} 应为空列表，实际为 {value!r}"
                )
            else:
                assert value == f.default, (
                    f"字段 {f.name} 应为 {f.default!r}，实际为 {value!r}"
                )

    def test_create_default_list_fields_empty(self) -> None:
        config = Blb2txtConfig.create_default()
        assert config.f_files == []

    def test_create_default_bool_fields_false(self) -> None:
        config = Blb2txtConfig.create_default()
        bool_field_names = [
            "i_stdin", "s_recursive", "x_relative",
            "o_overwrite", "u_subdir", "b_backup", "a_append",
            "t_topic", "r_recursive", "w_subdir", "toc", "j_join", "hh_html",
            "remove_spaces", "remove_hyphens", "remove_lines",
            "remove_multiple", "remove_paragraphs",
            "remove_square_brackets", "remove_curly_brackets",
            "remove_angle_brackets", "remove_round_brackets",
            "remove_comments", "remove_page_numbers",
            "ocr_correction", "lowercase", "ascii_pure",
            "skip_notes",
            "csv_comma", "csv_semicolon", "csv_space", "csv_tab",
            "csv_double_quote", "csv_single_quote",
            "eml_save", "eml_att", "eml_cc", "eml_org", "eml_rt",
            "dne_no_empty", "g_images", "cvr_cover", "dp_no_prompt",
        ]
        for name in bool_field_names:
            assert getattr(config, name) is False, f"{name} 应为 False"

    def test_create_default_none_fields_are_none(self) -> None:
        config = Blb2txtConfig.create_default()
        none_field_names = [
            "fl_file_list", "if_encoding", "pwd_password",
            "v_output", "p_prefix", "ext_extension", "out_file",
            "n_naming", "e_encoding", "cf_console_file", "cft_console_type",
            "k_keywords", "l_level", "c_chars", "m_min_length",
            "d_dict",
            "extract_summary", "include_notes",
            "insert_note_begin", "insert_note_end",
            "extract_tables",
            "eml_date", "eml_from", "eml_subj", "eml_to",
            "dll_path", "dex_exclude",
            "cfg_file",
        ]
        for name in none_field_names:
            assert getattr(config, name) is None, f"{name} 应为 None"


# ---------------------------------------------------------------------------
# to_args
# ---------------------------------------------------------------------------
class TestToArgs:
    """to_args 按 schema 类型生成 blb2txt 命令行参数列表。"""

    def test_default_config_to_args_returns_empty_list(self) -> None:
        config = Blb2txtConfig.create_default()
        assert config.to_args() == []

    def test_f_files_multiple_to_args(self) -> None:
        """spec 验收：设置 cfg.f_files=["book.pdf"] 后 to_args 包含 -f book.pdf。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf"]
        args = config.to_args()
        assert "-f" in args
        idx = args.index("-f")
        assert args[idx + 1] == "book.pdf"

    def test_f_files_multiple_files_to_args(self) -> None:
        """multiple=True 的 -f 应对每个文件输出 -f <path>。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf", "doc.epub"]
        assert config.to_args() == ["-f", "book.pdf", "-f", "doc.epub"]

    def test_v_output_to_args(self) -> None:
        """spec 验收：设置 v_output 后 to_args 包含 -v <path>。"""
        config = Blb2txtConfig.create_default()
        config.v_output = "out/"
        args = config.to_args()
        assert "-v" in args
        idx = args.index("-v")
        assert args[idx + 1] == "out/"

    def test_f_files_and_v_output_to_args(self) -> None:
        """spec 验收：设置 f_files 与 v_output 后 to_args 包含两者，顺序符合 _FIELD_TO_OPTION。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf"]
        config.v_output = "out/"
        args = config.to_args()
        assert args == ["-f", "book.pdf", "-v", "out/"]

    def test_n_naming_int_to_args(self) -> None:
        config = Blb2txtConfig.create_default()
        config.n_naming = 1
        assert config.to_args() == ["-n", "1"]

    def test_e_encoding_str_to_args(self) -> None:
        config = Blb2txtConfig.create_default()
        config.e_encoding = "utf8"
        assert config.to_args() == ["-e", "utf8"]

    def test_ext_extension_to_args(self) -> None:
        config = Blb2txtConfig.create_default()
        config.ext_extension = "txt"
        assert config.to_args() == ["-ext", "txt"]

    def test_remove_spaces_flag_to_args(self) -> None:
        """flag 字段设置为 True 时输出选项名本身。"""
        config = Blb2txtConfig.create_default()
        config.remove_spaces = True
        assert config.to_args() == ["--remove-spaces"]

    def test_csv_comma_flag_to_args(self) -> None:
        config = Blb2txtConfig.create_default()
        config.csv_comma = True
        assert config.to_args() == ["--csv-comma"]

    def test_toc_flag_single_dash_to_args(self) -> None:
        config = Blb2txtConfig.create_default()
        config.toc = True
        assert config.to_args() == ["-toc"]

    def test_flag_false_not_in_args(self) -> None:
        config = Blb2txtConfig.create_default()
        assert "--remove-spaces" not in config.to_args()
        assert "-toc" not in config.to_args()

    def test_str_none_not_in_args(self) -> None:
        config = Blb2txtConfig.create_default()
        assert "-e" not in config.to_args()
        assert "-ext" not in config.to_args()
        assert "--eml-date" not in config.to_args()

    def test_int_none_not_in_args(self) -> None:
        config = Blb2txtConfig.create_default()
        assert "-n" not in config.to_args()
        assert "-l" not in config.to_args()
        assert "--extract-summary" not in config.to_args()

    def test_empty_list_not_in_args(self) -> None:
        config = Blb2txtConfig.create_default()
        assert "-f" not in config.to_args()

    def test_multiple_fields_preserve_order(self) -> None:
        """多个字段同时设置时，输出顺序应与 _FIELD_TO_OPTION 声明顺序一致。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf"]
        config.v_output = "out/"
        config.n_naming = 2
        config.remove_spaces = True
        args = config.to_args()
        assert args == [
            "-f", "book.pdf",
            "-v", "out/",
            "-n", "2",
            "--remove-spaces",
        ]

    def test_all_field_to_option_keys_are_valid_dataclass_fields(self) -> None:
        """_FIELD_TO_OPTION 的每个键都应是 dataclass 字段。"""
        field_names = {f.name for f in fields(Blb2txtConfig)}
        for key in Blb2txtConfig._FIELD_TO_OPTION:
            assert key in field_names, f"_FIELD_TO_OPTION 键 {key!r} 不是字段"

    def test_all_schema_params_have_field_mapping(self) -> None:
        """schema 中每个 ParamSpec.name 都应在 _FIELD_TO_OPTION 的值中。"""
        option_names = set(Blb2txtConfig._FIELD_TO_OPTION.values())
        for spec in BLB2TXT_PARAMETER_SCHEMA:
            assert spec.name in option_names, (
                f"schema 参数 {spec.name!r} 未在 _FIELD_TO_OPTION 中映射"
            )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------
class TestValidate:
    """validate 应根据 schema 的 min/max/choices 检查字段值。

    blb2txt schema 中所有参数均无 min_value / max_value / choices，
    且 ParamKind 不含 choice 类型，因此 :meth:`validate` 始终返回空列表。
    这些测试文档化该行为，确保与 BalconConfig.validate 的语义一致
    （基类仅检查 choice 与带 min/max 的 int 字段）。
    """

    def test_default_config_validate_returns_empty(self) -> None:
        config = Blb2txtConfig.create_default()
        assert config.validate() == []

    def test_validate_invalid_encoding_returns_no_error(self) -> None:
        """-e 字段为 str 类型（非 choice），validate 不会校验枚举值。

        参考 BalconConfig.validate 行为：基类仅对 ParamKind.choice
        与带 min_value/max_value 的 ParamKind.int 字段做范围/枚举校验。
        blb2txt schema 中 -e 声明为 str 类型，故非法编码值不会触发错误。
        """
        config = Blb2txtConfig.create_default()
        config.e_encoding = "invalid_encoding"
        assert config.validate() == []

    def test_validate_invalid_cf_value_returns_no_error(self) -> None:
        """-cf 字段为 str 类型，validate 不会校验 YES/NO/STOP 枚举。"""
        config = Blb2txtConfig.create_default()
        config.cf_console_file = "MAYBE"
        assert config.validate() == []

    def test_validate_invalid_cft_value_returns_no_error(self) -> None:
        """-cft 字段为 str 类型，validate 不会校验 txt/html 枚举。"""
        config = Blb2txtConfig.create_default()
        config.cft_console_type = "pdf"
        assert config.validate() == []

    def test_validate_negative_int_returns_no_error(self) -> None:
        """int 字段在无 min_value 声明时不做范围校验。"""
        config = Blb2txtConfig.create_default()
        config.n_naming = -100
        config.m_min_length = -1
        assert config.validate() == []

    def test_validate_with_many_fields_set_returns_empty(self) -> None:
        """设置多个字段后 validate 仍应返回空（schema 无约束）。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf"]
        config.v_output = "out/"
        config.n_naming = 3
        config.e_encoding = "utf8"
        config.remove_spaces = True
        config.extract_tables = 1
        assert config.validate() == []


# ---------------------------------------------------------------------------
# to_dict / from_dict 往返
# ---------------------------------------------------------------------------
class TestToFromDict:
    """to_dict / from_dict 应保持配置字段值不变。"""

    def test_roundtrip_preserves_fields(self) -> None:
        config = Blb2txtConfig.create_default()
        config.f_files = ["book.pdf", "doc.epub"]
        config.v_output = "out/"
        config.n_naming = 2
        config.e_encoding = "utf8"
        config.remove_spaces = True
        config.extract_tables = 1

        data = config.to_dict()
        restored = Blb2txtConfig.from_dict(data)

        assert restored.f_files == ["book.pdf", "doc.epub"]
        assert restored.v_output == "out/"
        assert restored.n_naming == 2
        assert restored.e_encoding == "utf8"
        assert restored.remove_spaces is True
        assert restored.extract_tables == 1

    def test_from_dict_ignores_extra_keys(self) -> None:
        config = Blb2txtConfig.from_dict(
            {"v_output": "out/", "extra_key": "ignored", "another": 123}
        )
        assert config.v_output == "out/"

    def test_from_dict_missing_keys_use_defaults(self) -> None:
        config = Blb2txtConfig.from_dict({})
        assert config == Blb2txtConfig.create_default()

    def test_from_dict_list_none_becomes_empty(self) -> None:
        config = Blb2txtConfig.from_dict({"f_files": None})
        assert config.f_files == []

    def test_to_dict_excludes_classvar(self) -> None:
        config = Blb2txtConfig.create_default()
        data = config.to_dict()
        assert "_FIELD_TO_OPTION" not in data
        assert "_schema" not in data

    def test_to_dict_contains_all_dataclass_fields(self) -> None:
        config = Blb2txtConfig.create_default()
        data = config.to_dict()
        for f in fields(Blb2txtConfig):
            assert f.name in data

    def test_roundtrip_all_field_types(self) -> None:
        """覆盖各类字段类型的往返测试：list / str / int / bool / None。"""
        config = Blb2txtConfig.create_default()
        config.f_files = ["a.pdf", "b.epub"]
        config.fl_file_list = "list.txt"
        config.i_stdin = True
        config.if_encoding = "utf-8"
        config.v_output = "output/"
        config.ext_extension = "md"
        config.n_naming = 3
        config.e_encoding = "utf16"
        config.cf_console_file = "NO"
        config.cft_console_type = "html"
        config.t_topic = True
        config.k_keywords = "chapter;section"
        config.l_level = 2
        config.c_chars = 1000
        config.m_min_length = 256
        config.remove_spaces = True
        config.remove_square_brackets = True
        config.lowercase = True
        config.d_dict = "dict.txt"
        config.extract_summary = 1
        config.include_notes = 0
        config.insert_note_begin = "[["
        config.insert_note_end = "]]"
        config.extract_tables = 0
        config.csv_comma = True
        config.csv_double_quote = True
        config.eml_save = True
        config.eml_date = "%Y-%m-%d"
        config.eml_from = "Sender <sender@example.com>"
        config.dll_path = "unrar.dll"
        config.dex_exclude = ".exe;.dll"
        config.dne_no_empty = True
        config.g_images = True
        config.cvr_cover = True
        config.dp_no_prompt = True
        config.cfg_file = "config.ini"

        data = config.to_dict()
        restored = Blb2txtConfig.from_dict(data)

        # 抽样校验各类字段
        assert restored.f_files == ["a.pdf", "b.epub"]
        assert restored.fl_file_list == "list.txt"
        assert restored.i_stdin is True
        assert restored.if_encoding == "utf-8"
        assert restored.v_output == "output/"
        assert restored.ext_extension == "md"
        assert restored.n_naming == 3
        assert restored.e_encoding == "utf16"
        assert restored.cf_console_file == "NO"
        assert restored.cft_console_type == "html"
        assert restored.t_topic is True
        assert restored.k_keywords == "chapter;section"
        assert restored.l_level == 2
        assert restored.c_chars == 1000
        assert restored.m_min_length == 256
        assert restored.remove_spaces is True
        assert restored.remove_square_brackets is True
        assert restored.lowercase is True
        assert restored.d_dict == "dict.txt"
        assert restored.extract_summary == 1
        assert restored.include_notes == 0
        assert restored.insert_note_begin == "[["
        assert restored.insert_note_end == "]]"
        assert restored.extract_tables == 0
        assert restored.csv_comma is True
        assert restored.csv_double_quote is True
        assert restored.eml_save is True
        assert restored.eml_date == "%Y-%m-%d"
        assert restored.eml_from == "Sender <sender@example.com>"
        assert restored.dll_path == "unrar.dll"
        assert restored.dex_exclude == ".exe;.dll"
        assert restored.dne_no_empty is True
        assert restored.g_images is True
        assert restored.cvr_cover is True
        assert restored.dp_no_prompt is True
        assert restored.cfg_file == "config.ini"

    def test_roundtrip_default_config(self) -> None:
        """默认配置往返后应与默认实例相等。"""
        config = Blb2txtConfig.create_default()
        data = config.to_dict()
        restored = Blb2txtConfig.from_dict(data)
        assert restored == Blb2txtConfig.create_default()
