"""blb2txt 参数声明式 Schema。

以 dataclass 形式声明 blb2txt.exe 全部命令行参数，作为 GUI 动态渲染与
配置校验的统一数据源。新增 blb2txt 参数时仅需在本模块追加一条
``ParamSpec`` 记录，无需改动 GUI 代码。

复用 ``parameter_schema`` 中的 ``ParamSpec`` / ``ParamKind`` 类型定义，
保持与 balcon schema 一致的契约。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

from typing import Iterable

from chatterbox.core.parameter_schema import ParamKind, ParamSpec


# ---------------------------------------------------------------------------
# blb2txt 全部参数声明（按分组顺序排列）
# ---------------------------------------------------------------------------
BLB2TXT_PARAMETER_SCHEMA: list[ParamSpec] = [
    # --- Input ---
    ParamSpec(
        name="-f",
        kind=ParamKind.file,
        group="Input",
        multiple=True,
        help="输入文件（可多个）",
    ),
    ParamSpec(
        name="-fl",
        kind=ParamKind.file,
        group="Input",
        help="文件列表（文本文件，每行一个文件路径）",
    ),
    ParamSpec(
        name="-i",
        kind=ParamKind.flag,
        group="Input",
        help="从 stdin 读取",
    ),
    ParamSpec(
        name="-s",
        kind=ParamKind.flag,
        group="Input",
        help="递归子目录",
    ),
    ParamSpec(
        name="-x",
        kind=ParamKind.flag,
        group="Input",
        help="相对路径（不保存绝对路径）",
    ),
    ParamSpec(
        name="-if",
        kind=ParamKind.str,
        group="Input",
        default="ansi",
        help="输入文件编码（如 utf-8、ansi）",
    ),
    ParamSpec(
        name="-pwd",
        kind=ParamKind.str,
        group="Input",
        help="密码（用于加密文档）",
    ),

    # --- Output ---
    ParamSpec(
        name="-v",
        kind=ParamKind.file,
        group="Output",
        help="输出目录",
    ),
    ParamSpec(
        name="-p",
        kind=ParamKind.str,
        group="Output",
        help="文件名前缀",
    ),
    ParamSpec(
        name="-ext",
        kind=ParamKind.str,
        group="Output",
        default="txt",
        help="输出扩展名",
    ),
    ParamSpec(
        name="-out",
        kind=ParamKind.file,
        group="Output",
        help="输出到单一文件",
    ),
    ParamSpec(
        name="-o",
        kind=ParamKind.flag,
        group="Output",
        help="覆盖已存在文件",
    ),
    ParamSpec(
        name="-u",
        kind=ParamKind.flag,
        group="Output",
        help="输出到子目录",
    ),
    ParamSpec(
        name="-b",
        kind=ParamKind.flag,
        group="Output",
        help="备份已存在文件",
    ),
    ParamSpec(
        name="-a",
        kind=ParamKind.flag,
        group="Output",
        help="追加到已存在文件",
    ),
    ParamSpec(
        name="-n",
        kind=ParamKind.int,
        group="Output",
        default=1,
        help="命名模式（1=原名，2=原名_序号，3=序号）",
    ),
    ParamSpec(
        name="-e",
        kind=ParamKind.str,
        group="Output",
        default="ansi",
        help="输出编码（ansi/utf8/utf8b/utf16/utf16be/utf16le）",
    ),
    ParamSpec(
        name="-cf",
        kind=ParamKind.str,
        group="Output",
        default="YES",
        help="控制台输出文件（YES/NO/STOP）",
    ),
    ParamSpec(
        name="-cft",
        kind=ParamKind.str,
        group="Output",
        default="txt",
        help="控制台输出文件类型（txt/html）",
    ),

    # --- Split ---
    ParamSpec(
        name="-t",
        kind=ParamKind.flag,
        group="Split",
        help="按主题分割",
    ),
    ParamSpec(
        name="-k",
        kind=ParamKind.str,
        group="Split",
        help="按关键词分割（多个用 ; 分隔）",
    ),
    ParamSpec(
        name="-r",
        kind=ParamKind.flag,
        group="Split",
        help="递归分割",
    ),
    ParamSpec(
        name="-w",
        kind=ParamKind.flag,
        group="Split",
        help="分割后写入子目录",
    ),
    ParamSpec(
        name="-l",
        kind=ParamKind.int,
        group="Split",
        default=1,
        help="分割级别",
    ),
    ParamSpec(
        name="-c",
        kind=ParamKind.int,
        group="Split",
        help="按字符数分割",
    ),
    ParamSpec(
        name="-toc",
        kind=ParamKind.flag,
        group="Split",
        help="生成目录",
    ),
    ParamSpec(
        name="-m",
        kind=ParamKind.int,
        group="Split",
        default=512,
        help="最小分割长度",
    ),
    ParamSpec(
        name="-j",
        kind=ParamKind.flag,
        group="Split",
        help="连接分割片段",
    ),
    ParamSpec(
        name="-hh",
        kind=ParamKind.flag,
        group="Split",
        help="保留 HTML 标题",
    ),

    # --- TextProcessing ---
    ParamSpec(
        name="--remove-spaces",
        alias="-rs",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除空格",
    ),
    ParamSpec(
        name="--remove-hyphens",
        alias="-rh",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除连字符",
    ),
    ParamSpec(
        name="--remove-lines",
        alias="-rl",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除空行",
    ),
    ParamSpec(
        name="--remove-multiple",
        alias="-rm",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="合并多空格",
    ),
    ParamSpec(
        name="--remove-paragraphs",
        alias="-rp",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除空段落",
    ),
    ParamSpec(
        name="--remove-square-brackets",
        alias="-rsb",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除方括号内容",
    ),
    ParamSpec(
        name="--remove-curly-brackets",
        alias="-rcb",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除花括号内容",
    ),
    ParamSpec(
        name="--remove-angle-brackets",
        alias="-rab",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除尖括号内容",
    ),
    ParamSpec(
        name="--remove-round-brackets",
        alias="-rrb",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除圆括号内容",
    ),
    ParamSpec(
        name="--remove-comments",
        alias="-rc",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除注释",
    ),
    ParamSpec(
        name="--remove-page-numbers",
        alias="-rpn",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="移除页码",
    ),
    ParamSpec(
        name="--ocr-correction",
        alias="-ocr",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="OCR 纠正",
    ),
    ParamSpec(
        name="--lowercase",
        alias="-ls",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="转小写",
    ),
    ParamSpec(
        name="--ascii-pure",
        alias="-ap",
        kind=ParamKind.flag,
        group="TextProcessing",
        help="仅保留 ASCII",
    ),

    # --- Dictionary ---
    ParamSpec(
        name="-d",
        kind=ParamKind.file,
        group="Dictionary",
        help="字典文件路径",
    ),

    # --- Notes ---
    ParamSpec(
        name="--extract-summary",
        alias="-es",
        kind=ParamKind.int,
        group="Notes",
        default=0,
        help="提取摘要（0/1）",
    ),
    ParamSpec(
        name="--skip-notes",
        alias="-sn",
        kind=ParamKind.flag,
        group="Notes",
        help="跳过注释",
    ),
    ParamSpec(
        name="--include-notes",
        alias="-in",
        kind=ParamKind.int,
        group="Notes",
        default=1,
        help="包含注释（0/1）",
    ),
    ParamSpec(
        name="--insert-note-begin",
        alias="-inb",
        kind=ParamKind.str,
        group="Notes",
        help="注释开始标记",
    ),
    ParamSpec(
        name="--insert-note-end",
        alias="-ine",
        kind=ParamKind.str,
        group="Notes",
        help="注释结束标记",
    ),

    # --- Tables ---
    ParamSpec(
        name="--extract-tables",
        alias="-et",
        kind=ParamKind.int,
        group="Tables",
        default=1,
        help="提取表格（0/1）",
    ),

    # --- CSV ---
    ParamSpec(
        name="--csv-comma",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 逗号分隔",
    ),
    ParamSpec(
        name="--csv-semicolon",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 分号分隔",
    ),
    ParamSpec(
        name="--csv-space",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 空格分隔",
    ),
    ParamSpec(
        name="--csv-tab",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 制表符分隔",
    ),
    ParamSpec(
        name="--csv-double-quote",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 双引号",
    ),
    ParamSpec(
        name="--csv-single-quote",
        kind=ParamKind.flag,
        group="CSV",
        help="CSV 单引号",
    ),

    # --- EML ---
    ParamSpec(
        name="--eml-save",
        kind=ParamKind.flag,
        group="EML",
        help="保存 EML",
    ),
    ParamSpec(
        name="--eml-att",
        kind=ParamKind.flag,
        group="EML",
        help="保存附件",
    ),
    ParamSpec(
        name="--eml-cc",
        kind=ParamKind.flag,
        group="EML",
        help="包含抄送",
    ),
    ParamSpec(
        name="--eml-date",
        kind=ParamKind.str,
        group="EML",
        help="日期格式",
    ),
    ParamSpec(
        name="--eml-from",
        kind=ParamKind.str,
        group="EML",
        help="发件人格式",
    ),
    ParamSpec(
        name="--eml-org",
        kind=ParamKind.flag,
        group="EML",
        help="原始格式",
    ),
    ParamSpec(
        name="--eml-rt",
        kind=ParamKind.flag,
        group="EML",
        help="保留 RTF",
    ),
    ParamSpec(
        name="--eml-subj",
        kind=ParamKind.str,
        group="EML",
        help="主题格式",
    ),
    ParamSpec(
        name="--eml-to",
        kind=ParamKind.str,
        group="EML",
        help="收件人格式",
    ),

    # --- Archives ---
    ParamSpec(
        name="-dll",
        kind=ParamKind.file,
        group="Archives",
        help="DLL 路径（用于 ZIP/RAR）",
    ),
    ParamSpec(
        name="-dex",
        kind=ParamKind.str,
        group="Archives",
        help="排除文件扩展名列表",
    ),
    ParamSpec(
        name="-dne",
        kind=ParamKind.flag,
        group="Archives",
        help="不提取空文件",
    ),

    # --- Images ---
    ParamSpec(
        name="-g",
        kind=ParamKind.flag,
        group="Images",
        help="提取图像",
    ),
    ParamSpec(
        name="-cvr",
        kind=ParamKind.flag,
        group="Images",
        help="提取封面",
    ),

    # --- Misc ---
    ParamSpec(
        name="-dp",
        kind=ParamKind.flag,
        group="Misc",
        help="禁用提示",
    ),
    ParamSpec(
        name="-cfg",
        kind=ParamKind.file,
        group="Misc",
        help="配置文件路径",
    ),
]


# ---------------------------------------------------------------------------
# 分组聚合与查找工具
# ---------------------------------------------------------------------------
BLB2TXT_ALL_GROUP_NAMES: list[str] = [
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
]


BLB2TXT_GROUP_TITLES: dict[str, str] = {
    "Input": "输入",
    "Output": "输出",
    "Split": "文本分割",
    "TextProcessing": "文本处理",
    "Dictionary": "字典",
    "Notes": "注释",
    "Tables": "表格",
    "CSV": "CSV 格式",
    "EML": "EML 邮件",
    "Archives": "归档",
    "Images": "图像",
    "Misc": "其他",
}


def _build_params_by_group(
    schema: Iterable[ParamSpec],
) -> dict[str, list[ParamSpec]]:
    grouped: dict[str, list[ParamSpec]] = {
        name: [] for name in BLB2TXT_ALL_GROUP_NAMES
    }
    for spec in schema:
        if spec.group not in grouped:
            # 防御性：schema 中出现了 BLB2TXT_ALL_GROUP_NAMES 之外的分组。
            grouped[spec.group] = []
        grouped[spec.group].append(spec)
    return grouped


BLB2TXT_PARAMS_BY_GROUP: dict[str, list[ParamSpec]] = _build_params_by_group(
    BLB2TXT_PARAMETER_SCHEMA
)


def get_blb2txt_param(name: str) -> ParamSpec | None:
    """按主选项名或别名查找 blb2txt 的 ``ParamSpec``。

    Args:
        name: 选项名，可以是主名（如 ``--remove-spaces``）或别名（如 ``-rs``）。

    Returns:
        匹配到的 ``ParamSpec``；未找到时返回 ``None``。
    """
    for spec in BLB2TXT_PARAMETER_SCHEMA:
        if spec.name == name or spec.alias == name:
            return spec
    return None


__all__ = [
    "BLB2TXT_PARAMETER_SCHEMA",
    "BLB2TXT_PARAMS_BY_GROUP",
    "BLB2TXT_ALL_GROUP_NAMES",
    "BLB2TXT_GROUP_TITLES",
    "get_blb2txt_param",
]
