"""插件式选项卡。TabRegistry 自动发现 AbstractTab 子类。"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING

from chatterbox.core.tool_type import ToolType

if TYPE_CHECKING:
    from chatterbox.gui.tabs.base_tab import AbstractTab


def _discover_tabs() -> list[type[AbstractTab]]:
    """自动发现本包下所有 AbstractTab 子类。

    Returns:
        按 tab_title 排序的 Tab 类列表。
    """
    from chatterbox.gui.tabs.base_tab import AbstractTab

    discovered: list[type[AbstractTab]] = []
    package = importlib.import_module("chatterbox.gui.tabs")
    for _finder, name, _is_pkg in pkgutil.iter_modules(package.__path__):
        if name in {"base_tab", "__init__"}:
            continue
        module = importlib.import_module(f"chatterbox.gui.tabs.{name}")
        for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, AbstractTab)
                and obj is not AbstractTab
                and obj.__module__ == module.__name__
            ):
                discovered.append(obj)
    # 去重并按 tab_title 排序
    seen: set[str] = set()
    unique: list[type[AbstractTab]] = []
    for cls in discovered:
        if cls.__name__ in seen:
            continue
        seen.add(cls.__name__)
        unique.append(cls)
    unique.sort(key=lambda c: c.tab_title())
    return unique


class TabRegistry:
    """Tab 注册表，提供已注册 Tab 类的访问。"""

    _tabs: list[type[AbstractTab]] | None = None

    @classmethod
    def get_all_tabs(cls) -> list[type[AbstractTab]]:
        """获取所有已注册 Tab 类（按 tab_title 排序）。"""
        if cls._tabs is None:
            cls._tabs = _discover_tabs()
        return list(cls._tabs)

    @classmethod
    def get_tabs_by_tool(cls, tool: ToolType) -> list[type[AbstractTab]]:
        """按工具类型过滤已注册 Tab 类。

        通过 :meth:`AbstractTab.tab_tool` classmethod 判定每个 Tab
        所属的工具，返回所有匹配 ``tool`` 的 Tab 类（按 ``tab_title``
        排序，与 :meth:`get_all_tabs` 顺序一致）。

        Args:
            tool: 目标工具类型（如 :attr:`ToolType.BALCON`、
                :attr:`ToolType.BLB2TXT`）。

        Returns:
            匹配该工具的 Tab 类列表；若该工具暂无 Tab，返回空列表，
            不抛异常。
        """
        return [t for t in cls.get_all_tabs() if t.tab_tool() == tool]

    @classmethod
    def get_all_tabs_grouped(
        cls, tool: ToolType | None = None
    ) -> dict[str, list[type[AbstractTab]]]:
        """按 :meth:`AbstractTab.tab_group` 分组返回已注册 Tab 类。

        Args:
            tool: 可选的工具类型过滤。为 ``None`` 时返回全部 Tab 的分组
                （向后兼容）；非 ``None`` 时仅对 :meth:`tab_tool` 等于
                ``tool`` 的 Tab 进行分组。

        Returns:
            ``dict[group_name, list[tab_class]]``，分组顺序固定为：
            ``输入输出``、``语音音频``、``字幕歌词``、``文本处理``、
            ``格式选项``、``高级``、``其他``。
            空分组会被移除。每个分组内的 Tab 按 ``get_all_tabs`` 的
            ``tab_title`` 排序顺序保留。
        """
        grouped: dict[str, list[type[AbstractTab]]] = {
            "输入输出": [],
            "语音音频": [],
            "字幕歌词": [],
            "文本处理": [],
            "格式选项": [],
            "高级": [],
            "其他": [],
        }
        tabs = cls.get_tabs_by_tool(tool) if tool is not None else cls.get_all_tabs()
        for tab_cls in tabs:
            group = tab_cls.tab_group()
            if group not in grouped:
                grouped["其他"].append(tab_cls)
            else:
                grouped[group].append(tab_cls)
        # 移除空分组
        return {k: v for k, v in grouped.items() if v}

    @classmethod
    def refresh(cls) -> None:
        """重新扫描并刷新注册表。"""
        cls._tabs = None
        cls._tabs = _discover_tabs()
