"""parameter_schema 模块单元测试。

验证 balcon 全部 63 个命令行参数的声明式 schema 结构、分组聚合、
别名查找与 ParamSpec 构造校验。
"""
from __future__ import annotations

import pytest

from balcon_batch_tts.core.parameter_schema import (
    ALL_GROUP_NAMES,
    GROUP_TITLES,
    PARAMS_BY_GROUP,
    PARAMETER_SCHEMA,
    ParamKind,
    ParamSpec,
    get_param,
)


# ---------------------------------------------------------------------------
# Schema 整体结构
# ---------------------------------------------------------------------------
class TestSchemaStructure:
    """Schema 顶层结构断言。"""

    def test_parameter_schema_length(self) -> None:
        assert len(PARAMETER_SCHEMA) == 63

    def test_all_group_names_length(self) -> None:
        assert len(ALL_GROUP_NAMES) == 13

    def test_params_by_group_keys_match_all_group_names(self) -> None:
        assert set(PARAMS_BY_GROUP.keys()) == set(ALL_GROUP_NAMES)

    def test_params_by_group_preserves_group_order(self) -> None:
        assert list(PARAMS_BY_GROUP.keys()) == ALL_GROUP_NAMES

    def test_total_param_count_matches_schema_length(self) -> None:
        total = sum(len(params) for params in PARAMS_BY_GROUP.values())
        assert total == len(PARAMETER_SCHEMA) == 63


# ---------------------------------------------------------------------------
# 各 group 参数数量
# ---------------------------------------------------------------------------
class TestGroupParamCounts:
    """验证每个分组的参数数量与设计文档一致。"""

    @pytest.mark.parametrize(
        "group_name,expected_count",
        [
            ("Input", 7),
            ("Output", 5),
            ("Voice", 7),
            ("Device", 2),
            ("AudioFormat", 3),
            ("Silence", 2),
            ("Dictionary", 1),
            ("Subtitles", 5),
            ("LRC", 12),
            ("SRT", 4),
            ("Visemes", 1),
            ("TextFilter", 6),
            ("MultiVoice", 8),
        ],
    )
    def test_group_param_count(self, group_name: str, expected_count: int) -> None:
        assert len(PARAMS_BY_GROUP[group_name]) == expected_count


# ---------------------------------------------------------------------------
# get_param 查找
# ---------------------------------------------------------------------------
class TestGetParam:
    """get_param 主名/别名查找与边界情况。"""

    def test_get_param_s_returns_not_none(self) -> None:
        spec = get_param("-s")
        assert spec is not None

    def test_get_param_s_min_max_values(self) -> None:
        spec = get_param("-s")
        assert spec is not None
        assert spec.min_value == -10
        assert spec.max_value == 10

    def test_get_param_by_alias_returns_same_spec(self) -> None:
        """主名 --encoding 与别名 -enc 应返回同一个 ParamSpec 对象。"""
        spec_main = get_param("--encoding")
        spec_alias = get_param("-enc")
        assert spec_main is not None
        assert spec_alias is not None
        assert spec_main is spec_alias

    def test_get_param_nonexistent_returns_none(self) -> None:
        assert get_param("--nonexistent") is None


# ---------------------------------------------------------------------------
# ParamSpec 构造校验
# ---------------------------------------------------------------------------
class TestParamSpecValidation:
    """ParamSpec.__post_init__ 的契约校验。"""

    def test_choice_without_choices_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="choice"):
            ParamSpec(
                name="--test-choice",
                kind=ParamKind.choice,
                group="Test",
            )

    def test_choice_with_empty_choices_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(
                name="--test-choice",
                kind=ParamKind.choice,
                group="Test",
                choices=[],
            )

    def test_flag_with_non_bool_default_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="flag"):
            ParamSpec(
                name="--test-flag",
                kind=ParamKind.flag,
                group="Test",
                default="not a bool",
            )

    def test_flag_with_int_default_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            ParamSpec(
                name="--test-flag",
                kind=ParamKind.flag,
                group="Test",
                default=1,
            )

    def test_flag_with_none_default_is_ok(self) -> None:
        spec = ParamSpec(
            name="--test-flag",
            kind=ParamKind.flag,
            group="Test",
        )
        assert spec.default is None

    def test_flag_with_bool_default_is_ok(self) -> None:
        spec = ParamSpec(
            name="--test-flag",
            kind=ParamKind.flag,
            group="Test",
            default=True,
        )
        assert spec.default is True

    def test_choice_with_choices_is_ok(self) -> None:
        spec = ParamSpec(
            name="--test-choice",
            kind=ParamKind.choice,
            group="Test",
            choices=["a", "b"],
        )
        assert spec.choices == ["a", "b"]

    def test_int_kind_does_not_require_choices(self) -> None:
        spec = ParamSpec(
            name="--test-int",
            kind=ParamKind.int,
            group="Test",
            min_value=0,
            max_value=100,
        )
        assert spec.kind is ParamKind.int


# ---------------------------------------------------------------------------
# GROUP_TITLES 中文标题
# ---------------------------------------------------------------------------
class TestGroupTitles:
    """GROUP_TITLES 应包含全部 13 个分组的中文标题。"""

    def test_group_titles_length(self) -> None:
        assert len(GROUP_TITLES) == 13

    def test_group_titles_keys_match_all_group_names(self) -> None:
        assert set(GROUP_TITLES.keys()) == set(ALL_GROUP_NAMES)

    def test_group_titles_are_non_empty_strings(self) -> None:
        for key, title in GROUP_TITLES.items():
            assert isinstance(title, str), f"{key} 标题应为 str"
            assert len(title) > 0, f"{key} 标题不应为空"

    def test_group_titles_contain_chinese(self) -> None:
        """每个标题应至少含一个非 ASCII 字符（中文）。"""
        for key, title in GROUP_TITLES.items():
            has_chinese = any(ord(c) > 127 for c in title)
            assert has_chinese, f"{key} 标题 {title!r} 应含中文"
