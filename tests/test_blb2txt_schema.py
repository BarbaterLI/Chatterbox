"""blb2txt_schema 模块单元测试。

验证 blb2txt 全部 72 个命令行参数的声明式 schema 结构、分组聚合、
别名查找与 ParamSpec 构造契约。
"""
from __future__ import annotations

import pytest

from balcon_batch_tts.core.blb2txt_schema import (
    BLB2TXT_ALL_GROUP_NAMES,
    BLB2TXT_GROUP_TITLES,
    BLB2TXT_PARAMS_BY_GROUP,
    BLB2TXT_PARAMETER_SCHEMA,
    get_blb2txt_param,
)
from balcon_batch_tts.core.parameter_schema import ParamKind, ParamSpec


# ---------------------------------------------------------------------------
# Schema 整体结构
# ---------------------------------------------------------------------------
class TestSchemaStructure:
    """Schema 顶层结构断言。"""

    def test_parameter_schema_length_at_least_70(self) -> None:
        assert len(BLB2TXT_PARAMETER_SCHEMA) >= 70

    def test_parameter_schema_exact_length(self) -> None:
        assert len(BLB2TXT_PARAMETER_SCHEMA) == 72

    def test_all_group_names_length(self) -> None:
        assert len(BLB2TXT_ALL_GROUP_NAMES) == 12

    def test_params_by_group_keys_match_all_group_names(self) -> None:
        assert set(BLB2TXT_PARAMS_BY_GROUP.keys()) == set(BLB2TXT_ALL_GROUP_NAMES)

    def test_params_by_group_preserves_group_order(self) -> None:
        assert list(BLB2TXT_PARAMS_BY_GROUP.keys()) == BLB2TXT_ALL_GROUP_NAMES

    def test_total_param_count_matches_schema_length(self) -> None:
        total = sum(len(params) for params in BLB2TXT_PARAMS_BY_GROUP.values())
        assert total == len(BLB2TXT_PARAMETER_SCHEMA) == 72

    def test_all_group_names_covers_12_expected_groups(self) -> None:
        expected = {
            "Input",
            "Output",
            "Split",
            "TextProcessing",
            "Dictionary",
            "Notes",
            "Tables",
            "CSV",
            "EML",
            "Archives",
            "Images",
            "Misc",
        }
        assert set(BLB2TXT_ALL_GROUP_NAMES) == expected

    def test_no_duplicate_param_names(self) -> None:
        names = [spec.name for spec in BLB2TXT_PARAMETER_SCHEMA]
        assert len(names) == len(set(names))

    def test_no_duplicate_param_aliases(self) -> None:
        aliases = [
            spec.alias for spec in BLB2TXT_PARAMETER_SCHEMA if spec.alias is not None
        ]
        assert len(aliases) == len(set(aliases))

    def test_all_specs_are_param_spec_instances(self) -> None:
        for spec in BLB2TXT_PARAMETER_SCHEMA:
            assert isinstance(spec, ParamSpec)


# ---------------------------------------------------------------------------
# 各 group 参数数量
# ---------------------------------------------------------------------------
class TestGroupParamCounts:
    """验证每个分组的参数数量与设计文档一致。"""

    @pytest.mark.parametrize(
        "group_name,expected_count",
        [
            ("Input", 7),
            ("Output", 12),
            ("Split", 10),
            ("TextProcessing", 14),
            ("Dictionary", 1),
            ("Notes", 5),
            ("Tables", 1),
            ("CSV", 6),
            ("EML", 9),
            ("Archives", 3),
            ("Images", 2),
            ("Misc", 2),
        ],
    )
    def test_group_param_count(self, group_name: str, expected_count: int) -> None:
        assert len(BLB2TXT_PARAMS_BY_GROUP[group_name]) == expected_count

    def test_every_group_has_at_least_one_param(self) -> None:
        for group_name, params in BLB2TXT_PARAMS_BY_GROUP.items():
            assert len(params) > 0, f"分组 {group_name} 不应为空"


# ---------------------------------------------------------------------------
# get_blb2txt_param 查找
# ---------------------------------------------------------------------------
class TestGetBlb2txtParam:
    """get_blb2txt_param 主名/别名查找与边界情况。"""

    def test_get_param_by_alias_rs_returns_remove_spaces(self) -> None:
        """别名 -rs 应解析为主名 --remove-spaces 的 ParamSpec。"""
        spec = get_blb2txt_param("-rs")
        assert spec is not None
        assert spec.name == "--remove-spaces"

    def test_get_param_by_main_name_remove_spaces(self) -> None:
        spec = get_blb2txt_param("--remove-spaces")
        assert spec is not None
        assert spec.name == "--remove-spaces"

    def test_get_param_by_alias_returns_same_spec_as_main_name(self) -> None:
        """主名与别名应返回同一个 ParamSpec 对象。"""
        spec_main = get_blb2txt_param("--remove-spaces")
        spec_alias = get_blb2txt_param("-rs")
        assert spec_main is not None
        assert spec_alias is not None
        assert spec_main is spec_alias

    def test_get_param_f_returns_file_kind_with_multiple(self) -> None:
        spec = get_blb2txt_param("-f")
        assert spec is not None
        assert spec.kind is ParamKind.file
        assert spec.multiple is True

    def test_get_param_nonexistent_returns_none(self) -> None:
        assert get_blb2txt_param("--nonexistent") is None

    def test_get_param_empty_string_returns_none(self) -> None:
        assert get_blb2txt_param("") is None

    @pytest.mark.parametrize(
        "alias,expected_name",
        [
            ("-rs", "--remove-spaces"),
            ("-rh", "--remove-hyphens"),
            ("-rl", "--remove-lines"),
            ("-rm", "--remove-multiple"),
            ("-rp", "--remove-paragraphs"),
            ("-rsb", "--remove-square-brackets"),
            ("-rcb", "--remove-curly-brackets"),
            ("-rab", "--remove-angle-brackets"),
            ("-rrb", "--remove-round-brackets"),
            ("-rc", "--remove-comments"),
            ("-rpn", "--remove-page-numbers"),
            ("-ocr", "--ocr-correction"),
            ("-ls", "--lowercase"),
            ("-ap", "--ascii-pure"),
            ("-es", "--extract-summary"),
            ("-sn", "--skip-notes"),
            ("-in", "--include-notes"),
            ("-inb", "--insert-note-begin"),
            ("-ine", "--insert-note-end"),
            ("-et", "--extract-tables"),
        ],
    )
    def test_all_aliases_resolve_to_correct_main_name(
        self, alias: str, expected_name: str
    ) -> None:
        spec = get_blb2txt_param(alias)
        assert spec is not None, f"别名 {alias!r} 未找到对应 ParamSpec"
        assert spec.name == expected_name
        assert spec.alias == alias


# ---------------------------------------------------------------------------
# 分组归属与关键参数校验
# ---------------------------------------------------------------------------
class TestParamGroupMembership:
    """验证关键参数的分组归属与属性。"""

    def test_input_group_contains_expected_params(self) -> None:
        names = {spec.name for spec in BLB2TXT_PARAMS_BY_GROUP["Input"]}
        assert names == {"-f", "-fl", "-i", "-s", "-x", "-if", "-pwd"}

    def test_output_group_contains_expected_params(self) -> None:
        names = {spec.name for spec in BLB2TXT_PARAMS_BY_GROUP["Output"]}
        assert names == {
            "-v",
            "-p",
            "-ext",
            "-out",
            "-o",
            "-u",
            "-b",
            "-a",
            "-n",
            "-e",
            "-cf",
            "-cft",
        }

    def test_split_group_contains_expected_params(self) -> None:
        names = {spec.name for spec in BLB2TXT_PARAMS_BY_GROUP["Split"]}
        assert names == {
            "-t",
            "-k",
            "-r",
            "-w",
            "-l",
            "-c",
            "-toc",
            "-m",
            "-j",
            "-hh",
        }

    def test_text_processing_group_has_14_flags(self) -> None:
        params = BLB2TXT_PARAMS_BY_GROUP["TextProcessing"]
        assert len(params) == 14
        for spec in params:
            assert spec.kind is ParamKind.flag

    def test_csv_group_has_6_flags(self) -> None:
        params = BLB2TXT_PARAMS_BY_GROUP["CSV"]
        assert len(params) == 6
        for spec in params:
            assert spec.kind is ParamKind.flag

    def test_dictionary_group_contains_only_d(self) -> None:
        params = BLB2TXT_PARAMS_BY_GROUP["Dictionary"]
        assert len(params) == 1
        assert params[0].name == "-d"
        assert params[0].kind is ParamKind.file

    def test_eml_group_contains_expected_params(self) -> None:
        names = {spec.name for spec in BLB2TXT_PARAMS_BY_GROUP["EML"]}
        assert names == {
            "--eml-save",
            "--eml-att",
            "--eml-cc",
            "--eml-date",
            "--eml-from",
            "--eml-org",
            "--eml-rt",
            "--eml-subj",
            "--eml-to",
        }

    def test_misc_group_contains_dp_and_cfg(self) -> None:
        names = {spec.name for spec in BLB2TXT_PARAMS_BY_GROUP["Misc"]}
        assert names == {"-dp", "-cfg"}

    def test_every_param_group_matches_one_of_all_group_names(self) -> None:
        for spec in BLB2TXT_PARAMETER_SCHEMA:
            assert spec.group in BLB2TXT_ALL_GROUP_NAMES, (
                f"参数 {spec.name!r} 的分组 {spec.group!r} 不在 "
                f"BLB2TXT_ALL_GROUP_NAMES 中"
            )


# ---------------------------------------------------------------------------
# 关键参数属性校验
# ---------------------------------------------------------------------------
class TestKeyParamAttributes:
    """验证关键参数的属性（kind/default/multiple 等）。"""

    def test_f_param_is_file_with_multiple(self) -> None:
        spec = get_blb2txt_param("-f")
        assert spec is not None
        assert spec.kind is ParamKind.file
        assert spec.multiple is True
        assert spec.group == "Input"

    def test_if_param_default_is_ansi(self) -> None:
        spec = get_blb2txt_param("-if")
        assert spec is not None
        assert spec.kind is ParamKind.str
        assert spec.default == "ansi"

    def test_ext_param_default_is_txt(self) -> None:
        spec = get_blb2txt_param("-ext")
        assert spec is not None
        assert spec.kind is ParamKind.str
        assert spec.default == "txt"

    def test_n_param_default_is_1(self) -> None:
        spec = get_blb2txt_param("-n")
        assert spec is not None
        assert spec.kind is ParamKind.int
        assert spec.default == 1

    def test_e_param_default_is_ansi(self) -> None:
        spec = get_blb2txt_param("-e")
        assert spec is not None
        assert spec.kind is ParamKind.str
        assert spec.default == "ansi"

    def test_cf_param_default_is_yes(self) -> None:
        spec = get_blb2txt_param("-cf")
        assert spec is not None
        assert spec.kind is ParamKind.str
        assert spec.default == "YES"

    def test_cft_param_default_is_txt(self) -> None:
        spec = get_blb2txt_param("-cft")
        assert spec is not None
        assert spec.kind is ParamKind.str
        assert spec.default == "txt"

    def test_l_param_default_is_1(self) -> None:
        spec = get_blb2txt_param("-l")
        assert spec is not None
        assert spec.kind is ParamKind.int
        assert spec.default == 1

    def test_m_param_default_is_512(self) -> None:
        spec = get_blb2txt_param("-m")
        assert spec is not None
        assert spec.kind is ParamKind.int
        assert spec.default == 512

    def test_es_param_default_is_0(self) -> None:
        spec = get_blb2txt_param("-es")
        assert spec is not None
        assert spec.name == "--extract-summary"
        assert spec.kind is ParamKind.int
        assert spec.default == 0

    def test_in_param_default_is_1(self) -> None:
        spec = get_blb2txt_param("-in")
        assert spec is not None
        assert spec.name == "--include-notes"
        assert spec.kind is ParamKind.int
        assert spec.default == 1

    def test_et_param_default_is_1(self) -> None:
        spec = get_blb2txt_param("-et")
        assert spec is not None
        assert spec.name == "--extract-tables"
        assert spec.kind is ParamKind.int
        assert spec.default == 1

    def test_i_param_is_flag(self) -> None:
        spec = get_blb2txt_param("-i")
        assert spec is not None
        assert spec.kind is ParamKind.flag

    def test_d_param_is_file_kind(self) -> None:
        spec = get_blb2txt_param("-d")
        assert spec is not None
        assert spec.kind is ParamKind.file


# ---------------------------------------------------------------------------
# GROUP_TITLES 中文标题
# ---------------------------------------------------------------------------
class TestGroupTitles:
    """BLB2TXT_GROUP_TITLES 应包含全部 12 个分组的中文标题。"""

    def test_group_titles_length(self) -> None:
        assert len(BLB2TXT_GROUP_TITLES) == 12

    def test_group_titles_keys_match_all_group_names(self) -> None:
        assert set(BLB2TXT_GROUP_TITLES.keys()) == set(BLB2TXT_ALL_GROUP_NAMES)

    def test_group_titles_are_non_empty_strings(self) -> None:
        for key, title in BLB2TXT_GROUP_TITLES.items():
            assert isinstance(title, str), f"{key} 标题应为 str"
            assert len(title) > 0, f"{key} 标题不应为空"

    def test_group_titles_contain_chinese(self) -> None:
        """每个标题应至少含一个非 ASCII 字符（中文）。"""
        for key, title in BLB2TXT_GROUP_TITLES.items():
            has_chinese = any(ord(c) > 127 for c in title)
            assert has_chinese, f"{key} 标题 {title!r} 应含中文"


# ---------------------------------------------------------------------------
# 别名完整性校验
# ---------------------------------------------------------------------------
class TestAliasCompleteness:
    """验证带别名的参数数量符合预期。"""

    def test_text_processing_params_all_have_aliases(self) -> None:
        """TextProcessing 组 14 个参数都应有别名。"""
        for spec in BLB2TXT_PARAMS_BY_GROUP["TextProcessing"]:
            assert spec.alias is not None, (
                f"TextProcessing 参数 {spec.name!r} 应有别名"
            )

    def test_notes_params_all_have_aliases(self) -> None:
        for spec in BLB2TXT_PARAMS_BY_GROUP["Notes"]:
            assert spec.alias is not None, f"Notes 参数 {spec.name!r} 应有别名"

    def test_tables_param_has_alias(self) -> None:
        spec = get_blb2txt_param("--extract-tables")
        assert spec is not None
        assert spec.alias == "-et"

    def test_total_alias_count(self) -> None:
        aliases = [
            spec.alias for spec in BLB2TXT_PARAMETER_SCHEMA if spec.alias is not None
        ]
        # TextProcessing(14) + Notes(5) + Tables(1) = 20
        assert len(aliases) == 20

    def test_csv_params_have_no_aliases(self) -> None:
        """CSV 组参数按设计无别名（主名即唯一标识）。"""
        for spec in BLB2TXT_PARAMS_BY_GROUP["CSV"]:
            assert spec.alias is None, f"CSV 参数 {spec.name!r} 不应有别名"

    def test_eml_params_have_no_aliases(self) -> None:
        for spec in BLB2TXT_PARAMS_BY_GROUP["EML"]:
            assert spec.alias is None, f"EML 参数 {spec.name!r} 不应有别名"
