"""输出文件名模板引擎模块。

提供模板渲染与上下文构建能力，支持 ``{name}``、``{ext}``、``{voice}``、``{index}``、``{date}``
等占位符。纯标准库实现，无 GUI 依赖。
"""
from __future__ import annotations

import datetime
import logging
import os.path
import re

logger = logging.getLogger(__name__)

SUPPORTED_PLACEHOLDERS: dict[str, str] = {
    "name": "输入文件名（不含扩展名）",
    "ext": "输入扩展名（不含点）",
    "voice": "所选语音名",
    "index": "批次内序号（从 1 起，零填充至 3 位）",
    "date": "当前日期 YYYYMMDD",
}

DEFAULT_TEMPLATE = "{name}.wav"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def render_template(template: str, context: dict) -> str:
    """渲染模板字符串。

    参数：
        template: 模板字符串，如 ``"{name}_{voice}_{index}.wav"``
        context: 占位符到值的字典，键为 ``name``/``ext``/``voice``/``index``/``date``，
            值为字符串。

    返回：
        渲染后的字符串。

    行为：
        - 使用正则 ``r"\\{(\\w+)\\}"`` 匹配 ``{placeholder}`` 形式。
        - 对 ``{index}`` 应用零填充至 3 位（如 ``1`` → ``001``），但仅当 context 中
          ``index`` 是 int 或数字字符串时；非数字字符串保持原样。
        - 未知占位符（如 ``{foo}``）保留原样 ``{foo}``，记录 ``logger.warning``，不抛异常。
        - 不修改传入的 context 字典。
    """
    local_context = dict(context)

    idx_value = local_context.get("index")
    if isinstance(idx_value, int):
        local_context["index"] = f"{idx_value:03d}"
    elif isinstance(idx_value, str):
        try:
            n = int(idx_value)
        except ValueError:
            pass
        else:
            local_context["index"] = f"{n:03d}"

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in local_context:
            return str(local_context[key])
        logger.warning("未知占位符: {%s}，保留原样", key)
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


def build_context(
    input_path: str,
    voice: str,
    index: int,
    date: str | None = None,
) -> dict[str, str]:
    """从输入文件路径、语音名、序号构建 context 字典。

    参数：
        input_path: 输入文件路径。
        voice: 所选语音名（``None`` 视为空串）。
        index: 批次内序号（从 1 起）。
        date: 日期字符串 ``YYYYMMDD``；为 ``None`` 时取当前日期。

    返回：
        包含 ``name``/``ext``/``voice``/``index``/``date`` 五个键的字典。
    """
    name = os.path.splitext(os.path.basename(input_path))[0]
    ext = os.path.splitext(input_path)[1].lstrip(".")
    if voice is None:
        voice = ""
    if date is None:
        date = datetime.date.today().strftime("%Y%m%d")
    return {
        "name": name,
        "ext": ext,
        "voice": voice,
        "index": str(index),
        "date": date,
    }


def render_output_path(
    template: str,
    input_path: str,
    voice: str,
    index: int,
    output_dir: str | None = None,
    date: str | None = None,
) -> str:
    """便捷封装：构建 context + render_template。

    参数：
        template: 模板字符串。
        input_path: 输入文件路径。
        voice: 所选语音名。
        index: 批次内序号。
        output_dir: 输出目录；为 ``None`` 时只返回文件名。
        date: 日期字符串；为 ``None`` 时取当前日期。

    返回：
        渲染后的文件名或完整路径。若渲染结果不含扩展名，自动追加 ``.wav``。
    """
    context = build_context(input_path, voice, index, date)
    rendered = render_template(template, context)

    if not os.path.splitext(rendered)[1]:
        rendered = rendered + ".wav"

    if output_dir is not None:
        return os.path.join(output_dir, rendered)
    return rendered
