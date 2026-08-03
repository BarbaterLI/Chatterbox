"""预设（preset）持久化模块。

将工具配置（如 :class:`chatterbox.core.config.BalconConfig`）序列化为
JSON 文件，或从 JSON 文件读取原始参数字典，由调用方根据 ``tool_type`` 选择
对应的 Config 类反序列化，用于保存与加载用户自定义的 TTS 参数预设。

JSON 结构::

    {"version": "1.0", "tool_type": "balcon", "params": { ... 工具配置字段 ... }}

旧版本预设文件（无 ``tool_type`` 字段）默认视为 ``"balcon"``，保持向后兼容。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

import json
import logging
import os

from chatterbox.core.config import BalconConfig

logger = logging.getLogger(__name__)

PRESET_VERSION = "1.0"


def save_preset(path: str, config: BalconConfig, tool_type: str = "balcon") -> None:
    """将 config 序列化为 JSON 写入 path。

    Args:
        path: 目标 preset.json 路径。
        config: 待保存的配置实例（``BalconConfig`` / ``Blb2txtConfig`` 等，
            只要有 ``to_dict`` 方法即可）。
        tool_type: 工具类型标识（如 ``"balcon"``、``"blb2txt"``、``"sapi"``），
            默认 ``"balcon"`` 以保持向后兼容。
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload: dict[str, object] = {
        "version": PRESET_VERSION,
        "tool_type": tool_type,
        "params": config.to_dict(),
    }
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def load_preset(path: str) -> tuple[str, dict[str, object]]:
    """从 JSON 文件读取并返回 ``(tool_type, params)``。

    不再返回 :class:`BalconConfig` 实例，而是返回原始 params 字典，由调用方
    根据 ``tool_type`` 选择对应的 Config 类（``BalconConfig`` /
    ``Blb2txtConfig`` / ``SapiConfig``）进行反序列化。

    旧版本预设文件（无 ``tool_type`` 字段）默认返回 ``("balcon", params)``，
    保持向后兼容。

    Args:
        path: preset.json 路径。

    Returns:
        元组 ``(tool_type, params)``：``tool_type`` 为工具类型字符串
        （如 ``"balcon"``、``"blb2txt"``），``params`` 为原始参数字典。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: JSON 解析失败、结构不合法或缺少 ``params`` 字段。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"预设文件 {path!r} JSON 解析失败：{exc}") from exc
    except OSError as exc:
        raise ValueError(f"读取预设文件 {path!r} 失败：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"预设文件 {path!r} 顶层非对象")
    if "params" not in data:
        raise ValueError(f"预设文件 {path!r} 缺少 'params' 字段")
    params = data["params"]
    if not isinstance(params, dict):
        raise ValueError(f"预设文件 {path!r} 的 'params' 字段非对象")

    version = data.get("version")
    if version != PRESET_VERSION:
        logger.warning(
            "预设文件 %r 的版本 %r 与当前支持版本 %r 不一致，仍尝试加载",
            path, version, PRESET_VERSION,
        )

    # 旧预设文件无 tool_type 字段，默认 "balcon" 保持向后兼容。
    tool_type = data.get("tool_type", "balcon")
    if not isinstance(tool_type, str):
        raise ValueError(f"预设文件 {path!r} 的 'tool_type' 字段非字符串")

    return tool_type, params


def load_preset_safe(path: str) -> tuple[str, dict[str, object]] | None:
    """安全加载预设：捕获异常并记录日志，失败返回 ``None``。"""
    try:
        return load_preset(path)
    except FileNotFoundError:
        logger.warning("预设文件 %r 不存在", path)
    except ValueError as exc:
        logger.warning("加载预设文件 %r 失败：%s", path, exc)
    except OSError as exc:
        logger.warning("加载预设文件 %r 时发生 IO 错误：%s", path, exc)
    return None


__all__ = [
    "PRESET_VERSION",
    "save_preset",
    "load_preset",
    "load_preset_safe",
]
