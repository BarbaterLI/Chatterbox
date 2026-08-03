"""外部工具类型枚举。

定义本应用可调度的外部命令行工具类型（balcon 与 blb2txt），
作为调度器、配置层与 GUI 之间共享的工具标识。新增工具时仅需
在此枚举追加一条记录并补充 ``display_name``。

同时定义 :class:`ProcessPriority` 枚举，用于控制 balcon / ffmpeg
子进程的 Windows 进程优先级，便于在高并发场景下平衡系统响应性。
"""
from __future__ import annotations

import enum
import os
import subprocess


class ToolType(str, enum.Enum):
    """外部工具类型枚举。

    继承 ``str`` 便于直接序列化与作为字典键使用。

    Attributes:
        BALCON: balcon.exe 文本转语音工具。
        BLB2TXT: blb2txt.exe 文本提取工具。
        SAPI: SAPI5 直达 TTS（通过 pywin32 直调 COM 接口）。
    """

    BALCON = "balcon"
    BLB2TXT = "blb2txt"
    SAPI = "sapi"

    @property
    def display_name(self) -> str:
        """返回该工具的中文展示名称。"""
        if self is ToolType.BALCON:
            return "balcon TTS"
        if self is ToolType.BLB2TXT:
            return "blb2txt 文本提取"
        if self is ToolType.SAPI:
            return "SAPI5 直达 TTS"
        # 防御性：枚举新增成员未补充 display_name 时显式失败。
        raise ValueError(f"未定义的 ToolType {self!r} 缺少 display_name")


class ProcessPriority(str, enum.Enum):
    """子进程优先级枚举。

    继承 ``str`` 便于 JSON 序列化。映射到 Windows 进程优先级类
    （``creationflags``），非 Windows 平台仅 ``NORMAL`` 生效（其他值
    退化为 0，不影响进程调度）。

    Attributes:
        IDLE: 空闲优先级，仅在系统空闲时运行。
        BELOW_NORMAL: 低于正常，适合后台批量任务。
        NORMAL: 正常优先级（默认）。
        ABOVE_NORMAL: 高于正常。
        HIGH: 高优先级，可能影响系统响应。
    """

    IDLE = "idle"
    BELOW_NORMAL = "below_normal"
    NORMAL = "normal"
    ABOVE_NORMAL = "above_normal"
    HIGH = "high"

    @property
    def display_name(self) -> str:
        """返回中文展示名称。"""
        _NAMES = {
            ProcessPriority.IDLE: "空闲",
            ProcessPriority.BELOW_NORMAL: "低于正常",
            ProcessPriority.NORMAL: "正常",
            ProcessPriority.ABOVE_NORMAL: "高于正常",
            ProcessPriority.HIGH: "高",
        }
        return _NAMES[self]

    @property
    def windows_priority_class(self) -> int:
        """返回 Windows 进程优先级类标志位。

        非 Windows 平台返回 0（不影响进程调度）。
        """
        if os.name != "nt":
            return 0
        _FLAGS = {
            ProcessPriority.IDLE: 0x00000040,          # IDLE_PRIORITY_CLASS
            ProcessPriority.BELOW_NORMAL: 0x00004000,   # BELOW_NORMAL_PRIORITY_CLASS
            ProcessPriority.NORMAL: 0x00000020,         # NORMAL_PRIORITY_CLASS
            ProcessPriority.ABOVE_NORMAL: 0x00008000,   # ABOVE_NORMAL_PRIORITY_CLASS
            ProcessPriority.HIGH: 0x00000080,           # HIGH_PRIORITY_CLASS
        }
        return _FLAGS[self]


def priority_creationflags(priority: ProcessPriority | str | None = None) -> int:
    """返回组合了进程优先级与 ``CREATE_NO_WINDOW`` 的 creationflags。

    Args:
        priority: 进程优先级，可为 :class:`ProcessPriority` 枚举、字符串值
            或 ``None``（默认 :attr:`ProcessPriority.NORMAL`）。

    Returns:
        Windows 下返回 ``priority_class | CREATE_NO_WINDOW``，
        非 Windows 返回 0。
    """
    if priority is None:
        priority = ProcessPriority.NORMAL
    elif isinstance(priority, str):
        priority = ProcessPriority(priority)
    flags = priority.windows_priority_class
    if os.name == "nt":
        flags |= subprocess.CREATE_NO_WINDOW
    return flags


__all__ = ["ToolType", "ProcessPriority", "priority_creationflags"]
