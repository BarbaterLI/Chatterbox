"""应用设置持久化模块。

管理 :class:`AppSettings` 的序列化与反序列化，负责保存 GUI 层面的
非配置类状态：balcon.exe 路径、最大并发数、最近输出目录、窗口几何、
最近预设目录、文件名模板等。

纯标准库实现，禁止依赖 PySide6 或任何 GUI 库。
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"


def get_default_settings_path() -> str:
    """返回默认 settings.json 路径。

    优先使用 ``~/.chatterbox/settings.json``；若用户目录不可用
    （``os.path.expanduser('~')`` 返回原字符串），则回退到程序当前
    目录下的 ``settings.json``。所需目录会自动创建。
    """
    home = os.path.expanduser("~")
    if home and home != "~" and os.path.isdir(home):
        directory = os.path.join(home, ".chatterbox")
    else:
        directory = os.getcwd()
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        logger.warning("创建设置目录 %r 失败：%s", directory, exc)
    return os.path.join(directory, SETTINGS_FILE_NAME)


def _find_project_root() -> str:
    """从当前文件位置向上查找项目根目录（包含 ``pyproject.toml`` 的目录）。

    依次检查当前目录的父目录，直到找到包含 ``pyproject.toml`` 的目录。
    最多向上查找 10 级；未找到时返回空字符串。
    ``os.getcwd()`` 可能因运行环境（如临时目录）而不可靠，故基于脚本
    实际安装位置逐级查找，避免自动选择临时目录路径。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isfile(os.path.join(current, "pyproject.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return ""


def _is_in_temp_dir(path: str) -> bool:
    """判断路径是否位于系统的临时目录下。

    自动选择工具路径时，临时目录（如 ``%TEMP%``）中的路径应被拒绝，
    因为临时目录中的可执行文件通常是意外的或不可靠的。
    """
    temp_dirs = {
        os.environ.get("TEMP", ""),
        os.environ.get("TMP", ""),
    }
    abs_path = os.path.abspath(path)
    for temp_dir in temp_dirs:
        if temp_dir and abs_path.startswith(temp_dir.rstrip("\\") + "\\"):
            return True
    return False


def get_default_balcon_path() -> str:
    """返回默认 balcon.exe 路径：基于项目根目录的 ``balcon/balcon.exe``。

    优先从项目根目录（由 :func:`_find_project_root` 确定）查找；若未找到
    或路径位于临时目录下则回退到 ``os.getcwd()`` 版本。
    """
    root = _find_project_root()
    for base in (root, os.getcwd()):
        if not base:
            continue
        path = os.path.join(base, "balcon", "balcon.exe")
        path = os.path.abspath(path)
        if os.path.isfile(path) and not _is_in_temp_dir(path):
            return path
    return os.path.abspath(os.path.join(os.getcwd(), "balcon", "balcon.exe"))


def get_default_blb2txt_path() -> str:
    """返回默认 blb2txt.exe 路径：基于项目根目录的 ``blb2txt/blb2txt.exe``。

    优先从项目根目录查找；若未找到或路径位于临时目录下则回退到
    ``os.getcwd()`` 版本。
    """
    root = _find_project_root()
    for base in (root, os.getcwd()):
        if not base:
            continue
        path = os.path.join(base, "blb2txt", "blb2txt.exe")
        path = os.path.abspath(path)
        if os.path.isfile(path) and not _is_in_temp_dir(path):
            return path
    return os.path.abspath(os.path.join(os.getcwd(), "blb2txt", "blb2txt.exe"))


def get_default_blb2txt_lite_path() -> str:
    """返回默认 blb2txt 精简版路径：``blb2txt/Without PDF/blb2txt.exe``。

    优先从项目根目录查找；若未找到或路径位于临时目录下则回退到
    ``os.getcwd()`` 版本。
    """
    root = _find_project_root()
    for base in (root, os.getcwd()):
        if not base:
            continue
        path = os.path.join(base, "blb2txt", "Without PDF", "blb2txt.exe")
        path = os.path.abspath(path)
        if os.path.isfile(path) and not _is_in_temp_dir(path):
            return path
    return os.path.abspath(
        os.path.join(os.getcwd(), "blb2txt", "Without PDF", "blb2txt.exe")
    )


@dataclass
class AppSettings:
    """应用级设置数据模型。

    字段均使用基础类型，便于 JSON 序列化。``balcon_path`` 默认值通过
    :func:`field(default_factory=...)` 延迟调用，避免在模块导入时
    固定路径。
    """

    balcon_path: str = field(default_factory=get_default_balcon_path)
    blb2txt_path: str = field(default_factory=get_default_blb2txt_path)
    blb2txt_lite_path: str = field(default_factory=get_default_blb2txt_lite_path)
    max_concurrency: int = 2
    last_output_dir: str = ""
    window_geometry: str = ""
    last_preset_dir: str = ""
    filename_template: str = "{name}.wav"
    disable_animations: bool = False
    # 多格式输出：默认 WAV（向后兼容），可选 mp3/ogg/aac/flac/wma
    output_format: str = "wav"
    # ffmpeg 路径：空字符串表示自动查找（PATH 或环境变量）
    ffmpeg_path: str = ""
    # 主题：light / dark / auto（跟随系统）
    theme: str = "auto"
    # 紧凑度：compact / comfortable
    density: str = "comfortable"
    # 字体缩放：范围 0.85 ~ 1.3
    font_scale: float = 1.0
    # 按 tool_type 持久化折叠分组，如 {"balcon": ["语音音频", "字幕与同步"]}
    collapsed_groups: dict[str, list[str]] = field(default_factory=dict)
    # 最近文件，最多 10 项
    recent_files: list[str] = field(default_factory=list)
    # 最近预设，最多 10 项
    recent_presets: list[str] = field(default_factory=list)
    # 子进程优先级：idle / below_normal / normal / above_normal / high
    process_priority: str = "normal"
    # VBR 质量：-1 表示使用默认 CBR 320k；0~10 为 ffmpeg -q:a VBR 质量等级
    vbr_quality: int = -1

    @classmethod
    def load(cls, path: str | None = None) -> AppSettings:
        """从 JSON 文件加载设置。

        Args:
            path: settings.json 路径，``None`` 时使用
                :func:`get_default_settings_path`。

        Returns:
            重建的 :class:`AppSettings` 实例；文件缺失或解析失败时
            返回默认实例并记录 warning。
        """
        if path is None:
            path = get_default_settings_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.info("设置文件 %r 不存在，使用默认设置", path)
            return cls()
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("解析设置文件 %r 失败：%s，使用默认设置", path, exc)
            return cls()
        if not isinstance(data, dict):
            logger.warning("设置文件 %r 顶层非对象，使用默认设置", path)
            return cls()
        return cls.from_dict(data)

    def save(self, path: str | None = None) -> None:
        """保存设置到 JSON 文件（原子写入）。

        Args:
            path: 目标路径，``None`` 时使用
                :func:`get_default_settings_path`。
        """
        if path is None:
            path = get_default_settings_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except OSError:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def to_dict(self) -> dict[str, object]:
        """返回可 JSON 序列化的字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AppSettings:
        """从字典重建 :class:`AppSettings`。

        仅取已知字段，缺失字段使用默认值。
        """
        known = {f.name for f in dataclasses.fields(cls)}
        kwargs: dict[str, object] = {
            k: v for k, v in data.items() if k in known
        }
        return cls(**kwargs)


__all__ = [
    "AppSettings",
    "SETTINGS_FILE_NAME",
    "get_default_settings_path",
    "get_default_balcon_path",
    "get_default_blb2txt_path",
    "get_default_blb2txt_lite_path",
]
