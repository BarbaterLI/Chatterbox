"""blb2txt 配置模型模块。

定义 :class:`Blb2txtConfig` dataclass，封装 blb2txt.exe 全部 72 个命令行参数。
提供参数列表生成、校验与序列化能力，作为 GUI 与命令行之间的统一数据载体。

字段命名采用 Python 风格（snake_case），通过类级常量 ``_FIELD_TO_OPTION``
映射到 blb2txt 选项名。所有字段均有默认值，:meth:`create_default` 返回的实例
对应"无任何参数"状态，确保 :meth:`to_args` 输出为空列表。

通用方法（:meth:`to_args` / :meth:`validate` / :meth:`to_dict` /
:meth:`from_dict` / :meth:`create_default`）由 :class:`BaseToolConfig` 提供，
本类仅负责声明字段、``_FIELD_TO_OPTION`` 与 ``_schema`` 三个 ``ClassVar``。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from chatterbox.core.base_config import BaseToolConfig
from chatterbox.core.blb2txt_schema import BLB2TXT_PARAMETER_SCHEMA, ParamSpec


@dataclass
class Blb2txtConfig(BaseToolConfig):
    """blb2txt 全部命令行参数的配置模型（72 个字段）。

    字段分组与 :data:`blb2txt_schema.BLB2TXT_PARAMETER_SCHEMA` 保持一致，
    顺序亦与 schema 声明顺序相同，确保 :meth:`to_args` 输出顺序稳定。

    默认值策略：所有字段在默认值下均不产生命令行参数，即
    :meth:`create_default` 返回实例的 :meth:`to_args` 为空列表 ``[]``。
    schema 中声明的 ``default``（如 ``-n`` 默认 1、``-e`` 默认 "ansi"）
    仅作为 GUI 显示参考，不作为 dataclass 字段默认值；用户显式设置非
    ``None`` / 非 ``False`` / 非空列表后，对应参数才会出现在
    :meth:`to_args` 输出中。

    通用方法继承自 :class:`BaseToolConfig`，本类仅声明字段与两个
    ``ClassVar``（``_FIELD_TO_OPTION`` 与 ``_schema``）。
    """

    # --- Input ---
    f_files: list[str] = field(default_factory=list)
    fl_file_list: str | None = None
    i_stdin: bool = False
    s_recursive: bool = False
    x_relative: bool = False
    if_encoding: str | None = None
    pwd_password: str | None = None

    # --- Output ---
    v_output: str | None = None
    p_prefix: str | None = None
    ext_extension: str | None = None
    out_file: str | None = None
    o_overwrite: bool = False
    u_subdir: bool = False
    b_backup: bool = False
    a_append: bool = False
    n_naming: int | None = None
    e_encoding: str | None = None
    cf_console_file: str | None = None
    cft_console_type: str | None = None

    # --- Split ---
    t_topic: bool = False
    k_keywords: str | None = None
    r_recursive: bool = False
    w_subdir: bool = False
    l_level: int | None = None
    c_chars: int | None = None
    toc: bool = False
    m_min_length: int | None = None
    j_join: bool = False
    hh_html: bool = False

    # --- TextProcessing ---
    remove_spaces: bool = False
    remove_hyphens: bool = False
    remove_lines: bool = False
    remove_multiple: bool = False
    remove_paragraphs: bool = False
    remove_square_brackets: bool = False
    remove_curly_brackets: bool = False
    remove_angle_brackets: bool = False
    remove_round_brackets: bool = False
    remove_comments: bool = False
    remove_page_numbers: bool = False
    ocr_correction: bool = False
    lowercase: bool = False
    ascii_pure: bool = False

    # --- Dictionary ---
    d_dict: str | None = None

    # --- Notes ---
    extract_summary: int | None = None
    skip_notes: bool = False
    include_notes: int | None = None
    insert_note_begin: str | None = None
    insert_note_end: str | None = None

    # --- Tables ---
    extract_tables: int | None = None

    # --- CSV ---
    csv_comma: bool = False
    csv_semicolon: bool = False
    csv_space: bool = False
    csv_tab: bool = False
    csv_double_quote: bool = False
    csv_single_quote: bool = False

    # --- EML ---
    eml_save: bool = False
    eml_att: bool = False
    eml_cc: bool = False
    eml_date: str | None = None
    eml_from: str | None = None
    eml_org: bool = False
    eml_rt: bool = False
    eml_subj: str | None = None
    eml_to: str | None = None

    # --- Archives ---
    dll_path: str | None = None
    dex_exclude: str | None = None
    dne_no_empty: bool = False

    # --- Images ---
    g_images: bool = False
    cvr_cover: bool = False

    # --- Misc ---
    dp_no_prompt: bool = False
    cfg_file: str | None = None

    # 字段名 → blb2txt 选项名映射（按字段声明顺序，与 schema 一致）。
    # 使用 ClassVar 避免被 dataclass 当作字段处理。
    _FIELD_TO_OPTION: ClassVar[dict[str, str]] = {
        # Input
        "f_files": "-f",
        "fl_file_list": "-fl",
        "i_stdin": "-i",
        "s_recursive": "-s",
        "x_relative": "-x",
        "if_encoding": "-if",
        "pwd_password": "-pwd",
        # Output
        "v_output": "-v",
        "p_prefix": "-p",
        "ext_extension": "-ext",
        "out_file": "-out",
        "o_overwrite": "-o",
        "u_subdir": "-u",
        "b_backup": "-b",
        "a_append": "-a",
        "n_naming": "-n",
        "e_encoding": "-e",
        "cf_console_file": "-cf",
        "cft_console_type": "-cft",
        # Split
        "t_topic": "-t",
        "k_keywords": "-k",
        "r_recursive": "-r",
        "w_subdir": "-w",
        "l_level": "-l",
        "c_chars": "-c",
        "toc": "-toc",
        "m_min_length": "-m",
        "j_join": "-j",
        "hh_html": "-hh",
        # TextProcessing
        "remove_spaces": "--remove-spaces",
        "remove_hyphens": "--remove-hyphens",
        "remove_lines": "--remove-lines",
        "remove_multiple": "--remove-multiple",
        "remove_paragraphs": "--remove-paragraphs",
        "remove_square_brackets": "--remove-square-brackets",
        "remove_curly_brackets": "--remove-curly-brackets",
        "remove_angle_brackets": "--remove-angle-brackets",
        "remove_round_brackets": "--remove-round-brackets",
        "remove_comments": "--remove-comments",
        "remove_page_numbers": "--remove-page-numbers",
        "ocr_correction": "--ocr-correction",
        "lowercase": "--lowercase",
        "ascii_pure": "--ascii-pure",
        # Dictionary
        "d_dict": "-d",
        # Notes
        "extract_summary": "--extract-summary",
        "skip_notes": "--skip-notes",
        "include_notes": "--include-notes",
        "insert_note_begin": "--insert-note-begin",
        "insert_note_end": "--insert-note-end",
        # Tables
        "extract_tables": "--extract-tables",
        # CSV
        "csv_comma": "--csv-comma",
        "csv_semicolon": "--csv-semicolon",
        "csv_space": "--csv-space",
        "csv_tab": "--csv-tab",
        "csv_double_quote": "--csv-double-quote",
        "csv_single_quote": "--csv-single-quote",
        # EML
        "eml_save": "--eml-save",
        "eml_att": "--eml-att",
        "eml_cc": "--eml-cc",
        "eml_date": "--eml-date",
        "eml_from": "--eml-from",
        "eml_org": "--eml-org",
        "eml_rt": "--eml-rt",
        "eml_subj": "--eml-subj",
        "eml_to": "--eml-to",
        # Archives
        "dll_path": "-dll",
        "dex_exclude": "-dex",
        "dne_no_empty": "-dne",
        # Images
        "g_images": "-g",
        "cvr_cover": "-cvr",
        # Misc
        "dp_no_prompt": "-dp",
        "cfg_file": "-cfg",
    }

    # 参数声明列表，作为通用方法的查找来源。引用 blb2txt schema 常量。
    _schema: ClassVar[list[ParamSpec]] = BLB2TXT_PARAMETER_SCHEMA

    # 敏感字段集合：to_dict 时会被脱敏为 None，避免明文密码泄漏到 checkpoint
    # 与日志文件。from_dict 不做反向处理（恢复时用户需重新输入密码）。
    _SENSITIVE_FIELDS: ClassVar[frozenset[str]] = frozenset({"pwd_password"})

    def to_dict(self) -> dict[str, object]:
        """返回可 JSON 序列化的字典，敏感字段（如密码）脱敏为 ``None``。

        重写父类实现：在 :func:`dataclasses.asdict` 基础上，将
        :data:`_SENSITIVE_FIELDS` 中的字段值替换为 ``None``，避免明文密码
        被持久化到 checkpoint 文件或日志中。``from_dict`` 不做反向处理——
        恢复批次时用户需重新输入密码。
        """
        data = super().to_dict()
        for field_name in self._SENSITIVE_FIELDS:
            if field_name in data and data[field_name]:
                # 保留 has_password 的语义信号：非 None 但不可逆
                data[field_name] = "***"
        return data


__all__ = ["Blb2txtConfig"]
