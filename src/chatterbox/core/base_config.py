"""工具配置基类模块。

定义 :class:`BaseToolConfig`，封装通用命令行参数生成、校验与序列化逻辑。
具体工具的配置类（如 :class:`chatterbox.core.config.BalconConfig`）
继承本基类后，仅需声明字段、``_FIELD_TO_OPTION`` 与 ``_schema`` 三个
``ClassVar``，即可复用 :meth:`to_args` / :meth:`validate` / :meth:`to_dict`
/ :meth:`from_dict` / :meth:`create_default` 五个公开方法。

基类依赖子类提供：
    - ``_FIELD_TO_OPTION: ClassVar[dict[str, str]]``：字段名 → 命令行选项名映射。
    - ``_schema: ClassVar[list[ParamSpec]]``：参数声明列表，用于按选项名或别名
      查找 ``ParamSpec``，决定 ``to_args`` / ``validate`` 的行为。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

import logging
from dataclasses import MISSING, asdict, fields
from typing import ClassVar, TypeVar

from chatterbox.core.parameter_schema import ParamKind, ParamSpec

logger = logging.getLogger(__name__)

# 用于让 classmethod 返回子类实例的精确类型（而非基类），
# 确保 BalconConfig.from_dict(...) 的静态返回类型仍是 BalconConfig。
_T = TypeVar("_T", bound="BaseToolConfig")


class BaseToolConfig:
    """工具配置基类。

    子类需以 ``@dataclass`` 装饰，并声明以下两个 ``ClassVar``：

    - ``_FIELD_TO_OPTION``：字段名 → 命令行选项名映射，键的顺序决定
      :meth:`to_args` 的输出顺序。
    - ``_schema``：``ParamSpec`` 列表，作为按选项名或别名查找参数规格的来源。

    子类不应重写 :meth:`to_args` / :meth:`validate` / :meth:`to_dict` /
    :meth:`from_dict` / :meth:`create_default`；如需扩展，应通过调整 ``_schema``
    或新增独立方法实现，以保持公开接口稳定。
    """

    # 子类必须提供以下两个 ClassVar 的实际值。
    _FIELD_TO_OPTION: ClassVar[dict[str, str]]
    _schema: ClassVar[list[ParamSpec]]

    # name/alias → ParamSpec 查找字典，懒加载；子类各自独立缓存。
    # 首次调用 :meth:`_get_param_by_name` 时由 :meth:`_build_param_index`
    # 构建并写入 ``cls._param_index``，后续调用直接走 O(1) 字典查询。
    _param_index: ClassVar[dict[str, ParamSpec] | None] = None

    @classmethod
    def _build_param_index(cls) -> dict[str, ParamSpec]:
        """构建 ``{name: ParamSpec, alias: ParamSpec}`` 查找字典。

        遍历 ``cls._schema``，将每个 ``ParamSpec`` 按主名与别名（若有）
        注册到字典中。子类调用时使用各自的 ``_schema``，与父类互不影响。

        Returns:
            name/alias → ``ParamSpec`` 的字典。
        """
        index: dict[str, ParamSpec] = {}
        for spec in cls._schema:
            index[spec.name] = spec
            if spec.alias is not None:
                index[spec.alias] = spec
        return index

    @classmethod
    def _get_param_by_name(cls, name: str) -> ParamSpec | None:
        """按主选项名或别名在 ``cls._schema`` 中查找 ``ParamSpec``。

        使用懒加载的 ``_param_index`` 字典实现 O(1) 查找；首次调用时
        通过 :meth:`_build_param_index` 构建并缓存到 ``cls._param_index``，
        后续调用直接走字典查询。子类拥有独立的缓存，互不影响。

        Args:
            name: 选项名，可以是主名（如 ``--encoding``）或别名（如 ``-enc``）。

        Returns:
            匹配到的 ``ParamSpec``；未找到时返回 ``None``。
        """
        if not hasattr(cls, '_param_index') or cls._param_index is None:
            cls._param_index = cls._build_param_index()
        return cls._param_index.get(name)

    def to_args(self) -> list[str]:
        """生成命令行参数列表（不含可执行文件路径本身）。

        遍历 ``_FIELD_TO_OPTION``，依据 ``_schema`` 中对应 ``ParamSpec`` 的
        ``kind`` 与 ``multiple`` 属性决定如何输出：

        - ``flag``：值为 ``True`` 时输出 ``[option]``，``False`` 时不输出。
        - ``int``：值不为 ``None`` 时输出 ``[option, str(value)]``。
        - ``str`` / ``file`` / ``choice``：值不为 ``None`` 且非空字符串时
          输出 ``[option, value]``。
        - ``multiple=True`` 的 list 字段：对每个非空元素输出
          ``[option, element]``。

        Returns:
            参数列表，如 ``['-n', 'Emma', '-s', '2', '-lrc']``。
        """
        args: list[str] = []
        for field_name, option_name in self._FIELD_TO_OPTION.items():
            spec = self._get_param_by_name(option_name)
            if spec is None:
                logger.warning(
                    "字段 %r 映射到未知选项 %r，已跳过", field_name, option_name
                )
                continue
            value = getattr(self, field_name)
            if spec.multiple:
                if not value:
                    continue
                for elem in value:
                    if not elem:
                        continue
                    args.append(option_name)
                    args.append(elem if isinstance(elem, str) else str(elem))
            elif spec.kind is ParamKind.flag:
                if value is True:
                    args.append(option_name)
            elif spec.kind is ParamKind.int:
                if value is not None:
                    args.append(option_name)
                    args.append(str(value))
            else:  # str / file / choice
                if value is not None and value != "":
                    args.append(option_name)
                    args.append(value if isinstance(value, str) else str(value))
        return args

    def validate(self) -> list[str]:
        """校验配置值，返回错误信息列表。

        对每个 int 字段检查 ``min_value`` / ``max_value``（从 schema 获取），
        对每个 choice 字段检查值是否在 ``choices`` 中。

        Returns:
            错误信息列表，空列表表示通过。
        """
        errors: list[str] = []
        for field_name, option_name in self._FIELD_TO_OPTION.items():
            spec = self._get_param_by_name(option_name)
            if spec is None or spec.multiple:
                continue
            value = getattr(self, field_name)
            if value is None:
                continue
            if spec.kind is ParamKind.int:
                if spec.min_value is not None and value < spec.min_value:
                    errors.append(
                        f"参数 {option_name} 的值 {value} 超出范围 "
                        f"[{spec.min_value}, {spec.max_value}]"
                    )
                elif spec.max_value is not None and value > spec.max_value:
                    errors.append(
                        f"参数 {option_name} 的值 {value} 超出范围 "
                        f"[{spec.min_value}, {spec.max_value}]"
                    )
            elif spec.kind is ParamKind.choice:
                if spec.choices and str(value) not in spec.choices:
                    errors.append(
                        f"参数 {option_name} 的值 {value} 不在可选值 "
                        f"{spec.choices} 中"
                    )
        return errors

    def to_dict(self) -> dict[str, object]:
        """返回可 JSON 序列化的字典。

        使用 :func:`dataclasses.asdict` 转换。所有字段值应为可序列化基础类型
        （``str`` / ``int`` / ``bool`` / ``list``）。``ClassVar`` 字段
        （如 ``_FIELD_TO_OPTION`` / ``_schema``）不会被包含在结果中。
        """
        return asdict(self)

    @classmethod
    def from_dict(cls: type[_T], data: dict[str, object]) -> _T:
        """从字典重建配置实例。

        - 仅取 dataclass 字段名对应的键，忽略多余键。
        - 缺失键使用默认值。
        - 对 list 字段，若值为 ``None`` 视为空列表。
        """
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            if f.name in data:
                val = data[f.name]
                if val is None and f.default_factory is not MISSING:
                    val = f.default_factory()
                kwargs[f.name] = val
            else:
                if f.default is not MISSING:
                    kwargs[f.name] = f.default
                elif f.default_factory is not MISSING:
                    kwargs[f.name] = f.default_factory()
        return cls(**kwargs)

    @classmethod
    def create_default(cls: type[_T]) -> _T:
        """返回全默认值的配置实例。"""
        return cls()


__all__ = ["BaseToolConfig"]
