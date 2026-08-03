"""GUI 选项卡抽象基类模块。

定义 :class:`AbstractTab` 供 :mod:`chatterbox.gui.tabs` 包内的
TabRegistry 自动发现的具体 Tab 继承，并提供 :class:`AbstractParamTab`
作为基于 schema 的通用辅助基类，减少具体 Tab 的重复代码。

约束：
- 使用 PySide6（QWidget、Signal）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from chatterbox.core.base_config import BaseToolConfig
from chatterbox.core.config import BalconConfig
from chatterbox.core.tool_type import ToolType

if TYPE_CHECKING:
    from PySide6.QtWidgets import QSpinBox

logger = logging.getLogger(__name__)


class _AbstractTabMeta(type(QWidget), abc.ABCMeta):
    """合并 QWidget 的元类与 ABCMeta，避免多重继承元类冲突。

    Shiboken.ObjectType.__new__ 不会调用 ABCMeta.__new__，导致
    ``__abstractmethods__`` 不会被自动计算。此处手动复刻 ABCMeta
    的抽象方法收集逻辑，以恢复 abc 的实例化拦截语义。
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        # Shiboken.ObjectType.__new__ 未调用 ABCMeta.__new__，
        # 手动计算 __abstractmethods__ 以恢复 abc 实例化拦截。
        if "__abstractmethods__" not in cls.__dict__:
            abstracts = {
                attr
                for attr, value in namespace.items()
                if getattr(value, "__isabstractmethod__", False)
            }
            for base in bases:
                for attr in getattr(base, "__abstractmethods__", set()):
                    value = getattr(cls, attr, None)
                    if getattr(value, "__isabstractmethod__", False):
                        abstracts.add(attr)
            cls.__abstractmethods__ = frozenset(abstracts)
        return cls

    def __call__(cls, *args, **kwargs):
        # Shiboken.ObjectType.__call__ 不会检查 __abstractmethods__，
        # 此处手动拦截对含抽象方法类的实例化。
        abstracts = getattr(cls, "__abstractmethods__", frozenset())
        if abstracts:
            raise TypeError(
                f"Can't instantiate abstract class {cls.__name__!r} "
                f"with abstract methods "
                f"{', '.join(sorted(abstracts))}"
            )
        return super().__call__(*args, **kwargs)

    # ABCMeta.__subclasscheck__ / __instancecheck__ 依赖 ``_abc_impl``，
    # 而 Shiboken.ObjectType.__new__ 不调用 ABCMeta.__new__，
    # 导致该属性缺失。此处回退到 type 的标准 MRO 检查，
    # 使 ``issubclass(sub, AbstractTab)`` 在 TabRegistry 发现流程中可用。
    def __subclasscheck__(cls, subclass: type) -> bool:
        return type.__subclasscheck__(cls, subclass)

    def __instancecheck__(cls, instance: object) -> bool:
        return type.__instancecheck__(cls, instance)


class AbstractTab(QWidget, metaclass=_AbstractTabMeta):
    """所有 GUI 选项卡的抽象基类。

    具体子类必须实现 :meth:`tab_id`、:meth:`tab_title`、
    :meth:`collect_config` 与 :meth:`apply_config`，并可按需重写
    :meth:`refresh_voices`、:meth:`refresh_devices`、:meth:`on_show`
    等可选方法。

    控件值变化时子类应调用 :meth:`_emit_changed` 发射
    :attr:`config_changed` 信号，供主窗口监听并更新预览。

    注意:
        :meth:`tab_id`、:meth:`tab_title`、:meth:`tab_group`、
        :meth:`tab_icon` 与 :meth:`tab_tool` 均为 ``@classmethod``，
        以便 TabRegistry 在类对象上调用 ``c.tab_title()`` 进行排序、
        调用 ``c.tab_tool()`` 按工具过滤，无需实例化即可获取元信息。
    """

    # Tab 内控件值变化时发射，供主窗口监听更新预览。
    config_changed = Signal()

    @classmethod
    @abc.abstractmethod
    def tab_id(cls) -> str:
        """返回 Tab 唯一标识（如 ``"voice"``、``"lrc"``）。"""

    @classmethod
    @abc.abstractmethod
    def tab_title(cls) -> str:
        """返回 Tab 显示标题（中文，如 ``"语音"``）。"""

    @classmethod
    def tab_group(cls) -> str:
        """返回 Tab 分组名，默认 ``"其他"``。

        子类可重写以归入特定分组（如 ``"输入输出"``、``"语音音频"``、
        ``"字幕歌词"``、``"高级"``），供侧边栏按分组展示。
        """
        return "其他"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        """返回 Tab 图标，默认 ``None``。

        子类可重写返回分组对应的 QIcon（通常通过
        :class:`IconProvider.tab_icon` 获取）。
        """
        return None

    @classmethod
    def tab_tool(cls) -> ToolType:
        """返回本 Tab 所属的工具类型，默认 :attr:`ToolType.BALCON`。

        具体子类（如 blb2txt 系列 Tab）可重写返回
        :attr:`ToolType.BLB2TXT`，供 TabRegistry 与主窗口按工具
        过滤 Tab 集合。现有 13 个 balcon Tab 无需重写，直接继承
        默认实现即可。
        """
        return ToolType.BALCON

    @classmethod
    def tab_description(cls) -> str:
        """返回侧边栏 tooltip 文本，默认返回 :meth:`tab_title`。

        子类可重写以提供更详细的说明（含参数范围、单位、默认值等），
        供 :class:`SidebarTabWidget` 在悬浮时显示。未重写时回退到
        Tab 标题，保证最小可用语义。
        """
        return cls.tab_title()

    @abc.abstractmethod
    def collect_config(self, cfg: BalconConfig) -> None:
        """从本 Tab 的控件读取值，写入 ``cfg`` 对应字段。"""

    @abc.abstractmethod
    def apply_config(self, cfg: BalconConfig) -> None:
        """从 ``cfg`` 读取值，还原本 Tab 控件状态。"""

    def refresh_voices(self, voices: list[str]) -> None:
        """当语音列表刷新时调用，默认空实现，子类按需重写。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """当设备列表刷新时调用，默认空实现，子类按需重写。"""

    def on_show(self) -> None:
        """Tab 被选中时调用，默认空实现。"""

    def _emit_changed(self) -> None:
        """发射 :attr:`config_changed` 信号，供子类控件事件调用。"""
        self.config_changed.emit()


class AbstractParamTab(AbstractTab):
    """基于 schema 的通用参数 Tab 基类。

    提供 :meth:`_collect_int` 与 :meth:`_apply_int` 辅助方法，供具体 Tab
    在 :meth:`collect_config` / :meth:`apply_config` 中复用，减少重复代码。
    本类为可选辅助层，具体 Tab 亦可直接继承 :class:`AbstractTab`。

    辅助方法按 ``cfg`` 实例的运行时类型动态查找
    :attr:`BaseToolConfig._FIELD_TO_OPTION`，因此同时支持
    :class:`BalconConfig` 与 :class:`Blb2txtConfig` 等任意
    :class:`BaseToolConfig` 子类。
    """

    @staticmethod
    def _option_to_field(cfg: BaseToolConfig, option_name: str) -> str | None:
        """按 ``cfg`` 运行时类型反查 ``option_name`` 对应的字段名。

        Args:
            cfg: 配置实例，用于定位其类的 ``_FIELD_TO_OPTION``。
            option_name: 命令行选项名（如 ``"-s"``）。

        Returns:
            匹配到的字段名；未找到时返回 ``None``。
        """
        field_to_option = getattr(type(cfg), "_FIELD_TO_OPTION", None)
        if not field_to_option:
            return None
        for field_name, option in field_to_option.items():
            if option == option_name:
                return field_name
        return None

    def _collect_int(
        self,
        cfg: BaseToolConfig,
        option_name: str,
        widget: QSpinBox,
    ) -> None:
        """从 QSpinBox 读取 int 值，按 ``option_name`` 设置 cfg 对应字段。

        简化策略：若 spinbox 值为 0 则设为 ``None``（避免冗余参数），
        否则直接设置 int 值。

        Args:
            cfg: 待写入的配置对象，需为 :class:`BaseToolConfig` 子类实例。
            option_name: 命令行选项名（如 ``"-s"``），需在
                ``type(cfg)._FIELD_TO_OPTION`` 中存在。
            widget: 与该选项绑定的 QSpinBox 控件。
        """
        field_name = self._option_to_field(cfg, option_name)
        if field_name is None:
            logger.warning(
                "选项名 %r 未在 %s._FIELD_TO_OPTION 中找到，无法写入 cfg",
                option_name,
                type(cfg).__name__,
            )
            return
        value = widget.value()
        setattr(cfg, field_name, value if value != 0 else None)

    def _apply_int(
        self,
        cfg: BaseToolConfig,
        option_name: str,
        widget: QSpinBox,
    ) -> None:
        """从 cfg 读取值，还原 QSpinBox 控件状态。

        若 cfg 对应字段为 ``None``，则将 spinbox 置 0；否则置为字段值。

        Args:
            cfg: 提供值的配置对象，需为 :class:`BaseToolConfig` 子类实例。
            option_name: 命令行选项名（如 ``"-s"``），需在
                ``type(cfg)._FIELD_TO_OPTION`` 中存在。
            widget: 与该选项绑定的 QSpinBox 控件。
        """
        field_name = self._option_to_field(cfg, option_name)
        if field_name is None:
            logger.warning(
                "选项名 %r 未在 %s._FIELD_TO_OPTION 中找到，无法还原控件",
                option_name,
                type(cfg).__name__,
            )
            return
        value = getattr(cfg, field_name, None)
        widget.setValue(int(value) if value is not None else 0)


__all__ = ["AbstractTab", "AbstractParamTab"]
