"""tool_type 模块单元测试。

验证 ToolType 枚举的取值、展示名称与字符串行为。
"""
from __future__ import annotations

import enum

import pytest

from balcon_batch_tts.core.tool_type import ToolType


# ---------------------------------------------------------------------------
# 枚举成员与取值
# ---------------------------------------------------------------------------
class TestEnumMembers:
    """ToolType 枚举成员与 value 断言。"""

    def test_enum_has_three_members(self) -> None:
        assert len(list(ToolType)) == 3

    def test_balcon_value(self) -> None:
        assert ToolType.BALCON.value == "balcon"

    def test_blb2txt_value(self) -> None:
        assert ToolType.BLB2TXT.value == "blb2txt"

    def test_sapi_value(self) -> None:
        assert ToolType.SAPI.value == "sapi"

    def test_balcon_is_str_subclass(self) -> None:
        """ToolType 继承 str，BALCON 实例应同时是 str。"""
        assert isinstance(ToolType.BALCON, str)

    def test_blb2txt_is_str_subclass(self) -> None:
        assert isinstance(ToolType.BLB2TXT, str)

    def test_sapi_is_str_subclass(self) -> None:
        assert isinstance(ToolType.SAPI, str)

    def test_balcon_equals_str_value(self) -> None:
        """继承 str 后枚举成员应等于对应字符串。"""
        assert ToolType.BALCON == "balcon"

    def test_blb2txt_equals_str_value(self) -> None:
        assert ToolType.BLB2TXT == "blb2txt"

    def test_sapi_equals_str_value(self) -> None:
        assert ToolType.SAPI == "sapi"

    def test_from_value_returns_member(self) -> None:
        assert ToolType("balcon") is ToolType.BALCON
        assert ToolType("blb2txt") is ToolType.BLB2TXT
        assert ToolType("sapi") is ToolType.SAPI

    def test_from_unknown_value_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            ToolType("unknown")

    def test_is_enum_member(self) -> None:
        assert isinstance(ToolType.BALCON, enum.Enum)
        assert isinstance(ToolType.BLB2TXT, enum.Enum)
        assert isinstance(ToolType.SAPI, enum.Enum)


# ---------------------------------------------------------------------------
# display_name
# ---------------------------------------------------------------------------
class TestDisplayName:
    """ToolType.display_name 属性契约。"""

    def test_balcon_display_name(self) -> None:
        assert ToolType.BALCON.display_name == "balcon TTS"

    def test_blb2txt_display_name(self) -> None:
        assert ToolType.BLB2TXT.display_name == "blb2txt 文本提取"

    def test_all_members_have_non_empty_display_name(self) -> None:
        for member in ToolType:
            assert isinstance(member.display_name, str)
            assert len(member.display_name) > 0
