"""BaseToolConfig 单元测试。

重点验证 ``_get_param_by_name`` 的 O(1) 字典查找、``_param_index``
的懒加载与子类独立缓存行为。
"""
from __future__ import annotations

import pytest

from balcon_batch_tts.core.base_config import BaseToolConfig
from balcon_batch_tts.core.blb2txt_config import Blb2txtConfig
from balcon_batch_tts.core.config import BalconConfig
from balcon_batch_tts.core.parameter_schema import ParamSpec


@pytest.fixture(autouse=True)
def _reset_param_index() -> None:
    """每个测试前后清空 ``_param_index``，避免测试间相互污染。

    依赖懒加载机制：清空后下次调用 :meth:`_get_param_by_name` 会重建。
    """
    classes = [BaseToolConfig, BalconConfig, Blb2txtConfig]
    for cls in classes:
        cls._param_index = None
    yield
    for cls in classes:
        cls._param_index = None


# ---------------------------------------------------------------------------
# _get_param_by_name / _build_param_index
# ---------------------------------------------------------------------------
class TestGetParamByName:
    """``_get_param_by_name`` 应通过字典查找返回正确的 ``ParamSpec``。"""

    def test_get_param_by_name_o1(self) -> None:
        """查找主名应返回对应 ``ParamSpec``，且与 schema 中对象一致。"""
        spec = BalconConfig._get_param_by_name("-n")
        assert spec is not None
        assert isinstance(spec, ParamSpec)
        assert spec.name == "-n"
        # 与 schema 中实际对象为同一引用
        assert spec in BalconConfig._schema

    def test_get_param_by_name_returns_none_for_unknown(self) -> None:
        """未知选项名应返回 ``None``。"""
        assert BalconConfig._get_param_by_name("--not-exist") is None

    def test_get_param_by_name_after_cached(self) -> None:
        """缓存命中后再次查找仍返回正确结果。"""
        first = BalconConfig._get_param_by_name("-s")
        second = BalconConfig._get_param_by_name("-s")
        assert first is second
        assert first is not None
        assert first.name == "-s"


# ---------------------------------------------------------------------------
# 懒加载
# ---------------------------------------------------------------------------
class TestParamIndexLazyLoad:
    """``_param_index`` 应在首次调用时懒加载构建。"""

    def test_param_index_lazy_load(self) -> None:
        """首次调用前 ``_param_index`` 为 ``None``；调用后变为字典。"""
        assert BalconConfig._param_index is None
        # 触发懒加载
        BalconConfig._get_param_by_name("-n")
        assert BalconConfig._param_index is not None
        assert isinstance(BalconConfig._param_index, dict)

    def test_param_index_built_only_once(self) -> None:
        """多次调用只构建一次（缓存命中）。"""
        BalconConfig._get_param_by_name("-n")
        first_index = BalconConfig._param_index
        assert first_index is not None
        BalconConfig._get_param_by_name("-s")
        BalconConfig._get_param_by_name("--encoding")
        # 同一对象引用，未重建
        assert BalconConfig._param_index is first_index

    def test_build_param_index_returns_dict(self) -> None:
        """``_build_param_index`` 直接返回字典（不依赖缓存）。"""
        index = BalconConfig._build_param_index()
        assert isinstance(index, dict)
        assert len(index) > 0
        # _build_param_index 不应写入 _param_index
        assert BalconConfig._param_index is None


# ---------------------------------------------------------------------------
# 子类独立缓存
# ---------------------------------------------------------------------------
class TestSubclassIndependentIndex:
    """子类应拥有独立的 ``_param_index``，互不影响。"""

    def test_subclass_independent_index(self) -> None:
        """``BalconConfig`` 与 ``Blb2txtConfig`` 的缓存应为不同字典对象。"""
        BalconConfig._get_param_by_name("-n")
        Blb2txtConfig._get_param_by_name("-f")
        assert BalconConfig._param_index is not None
        assert Blb2txtConfig._param_index is not None
        assert BalconConfig._param_index is not Blb2txtConfig._param_index

    def test_subclass_index_uses_own_schema(self) -> None:
        """子类缓存应基于各自的 ``_schema`` 构建。"""
        balcon_index = BalconConfig._build_param_index()
        blb2txt_index = Blb2txtConfig._build_param_index()
        # --lrc-length 仅存在于 balcon 的 schema 中
        assert "--lrc-length" in balcon_index
        assert "--lrc-length" not in blb2txt_index
        # --remove-spaces 仅存在于 blb2txt 的 schema 中
        assert "--remove-spaces" not in balcon_index
        assert "--remove-spaces" in blb2txt_index

    def test_parent_assignment_does_not_leak_to_sibling(self) -> None:
        """为某子类构建缓存不影响另一子类的 ``_param_index``。"""
        BalconConfig._get_param_by_name("-n")
        assert BalconConfig._param_index is not None
        # Blb2txtConfig 未触发懒加载，仍为 None
        assert Blb2txtConfig._param_index is None

    def test_writing_to_subclass_does_not_mutate_base(self) -> None:
        """子类 ``_param_index`` 不会回写到 ``BaseToolConfig``。"""
        BalconConfig._get_param_by_name("-n")
        assert BalconConfig._param_index is not None
        # 父类 ``_param_index`` 仍为初始 ``None``
        assert BaseToolConfig._param_index is None


# ---------------------------------------------------------------------------
# name 与 alias 覆盖
# ---------------------------------------------------------------------------
class TestParamIndexCoversNameAndAlias:
    """``_param_index`` 应同时覆盖 ``name`` 与 ``alias``。"""

    def test_param_index_covers_name_and_alias(self) -> None:
        """通过主名与别名查找应返回同一 ``ParamSpec``。"""
        # --encoding 主名 / -enc 别名
        by_name = BalconConfig._get_param_by_name("--encoding")
        by_alias = BalconConfig._get_param_by_name("-enc")
        assert by_name is not None
        assert by_alias is not None
        assert by_name is by_alias
        assert by_name.name == "--encoding"
        assert by_name.alias == "-enc"

    def test_param_index_covers_all_aliased_specs(self) -> None:
        """所有声明了 alias 的 spec 都应可通过 alias 查到。"""
        BalconConfig._get_param_by_name("-n")  # 触发懒加载
        index = BalconConfig._param_index
        assert index is not None
        for spec in BalconConfig._schema:
            assert spec.name in index
            if spec.alias is not None:
                assert spec.alias in index
                assert index[spec.alias] is spec

    def test_param_index_keys_count(self) -> None:
        """索引键数 = schema 长度 + 别名数量。"""
        BalconConfig._get_param_by_name("-n")
        index = BalconConfig._param_index
        assert index is not None
        alias_count = sum(1 for s in BalconConfig._schema if s.alias is not None)
        assert len(index) == len(BalconConfig._schema) + alias_count
