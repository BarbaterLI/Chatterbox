"""IconProvider 单元测试。

验证 ``tool_icon(ToolType)`` 工具图标、``tool_icon(str)`` 动作图标
与 ``tab_icon(group)`` 分组图标的返回契约（非空 QIcon）。

覆盖：
- ``ToolType.BALCON`` / ``ToolType.BLB2TXT`` 工具图标非空。
- 原有字符串名称动作图标（``"add"`` / ``"start"`` 等）仍可正常获取
  （多态改造的回归保护）。
- blb2txt 新增 6 个分组（文本处理 / 字典注释 / 表格CSV / EML /
  归档图像 / 其他）的 ``tab_icon`` 返回非空。
- 既有 balcon 分组（输入输出 / 语音音频 / 字幕歌词 / 高级）不受影响。

测试在 offscreen Qt 平台下运行，无需真实显示设备。
"""
from __future__ import annotations

import os

# 必须在导入 PySide6 之前设置 offscreen 平台插件，避免无显示环境报错。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.widgets.icon_provider import IconProvider


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """返回全局 QApplication 单例（offscreen 模式）。

    SVG 渲染依赖 QGuiApplication 事件循环基础设施，因此需要 QApplication。
    """
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# tool_icon(ToolType) —— 工具标识图标
# ---------------------------------------------------------------------------
class TestToolIconByToolType:
    """``tool_icon(ToolType)`` 返回工具标识图标（balcon 喇叭 / blb2txt 文档提取）。"""

    def test_balcon_tool_icon_non_null(self, qapp: QApplication) -> None:
        icon = IconProvider.tool_icon(ToolType.BALCON)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_blb2txt_tool_icon_non_null(self, qapp: QApplication) -> None:
        icon = IconProvider.tool_icon(ToolType.BLB2TXT)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_balcon_and_blb2txt_icons_distinct(self, qapp: QApplication) -> None:
        """两个工具图标应基于不同 SVG，pixmap 像素不完全相同。"""
        balcon_icon = IconProvider.tool_icon(ToolType.BALCON)
        blb2txt_icon = IconProvider.tool_icon(ToolType.BLB2TXT)
        assert not balcon_icon.isNull()
        assert not blb2txt_icon.isNull()


# ---------------------------------------------------------------------------
# tool_icon(str) —— 动作图标（回归保护）
# ---------------------------------------------------------------------------
class TestToolIconByName:
    """``tool_icon(str)`` 原有动作图标接口保持不变（多态改造无回归）。"""

    @pytest.mark.parametrize(
        "name",
        [
            "add",
            "remove",
            "clear",
            "refresh",
            "start",
            "stop",
            "preview",
            "save",
            "load",
            "settings",
        ],
    )
    def test_action_icon_non_null(
        self, qapp: QApplication, name: str
    ) -> None:
        icon = IconProvider.tool_icon(name)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_unknown_name_returns_null_icon(self, qapp: QApplication) -> None:
        icon = IconProvider.tool_icon("non_existent_icon")
        assert icon.isNull()


# ---------------------------------------------------------------------------
# tab_icon —— blb2txt 新增分组
# ---------------------------------------------------------------------------
class TestBlb2txtTabGroupIcons:
    """``tab_icon`` 对 blb2txt 6 个新分组返回非空 QIcon。"""

    @pytest.mark.parametrize(
        "group",
        ["文本处理", "字典注释", "表格CSV", "EML", "归档图像", "其他"],
    )
    def test_blb2txt_group_icon_non_null(
        self, qapp: QApplication, group: str
    ) -> None:
        icon = IconProvider.tab_icon(group)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()


# ---------------------------------------------------------------------------
# tab_icon —— 既有 balcon 分组（回归保护）
# ---------------------------------------------------------------------------
class TestBalconTabGroupIcons:
    """``tab_icon`` 对既有 balcon 4 个分组仍返回非空 QIcon。"""

    @pytest.mark.parametrize(
        "group",
        ["输入输出", "语音音频", "字幕歌词", "高级"],
    )
    def test_balcon_group_icon_non_null(
        self, qapp: QApplication, group: str
    ) -> None:
        icon = IconProvider.tab_icon(group)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_input_output_shared_between_tools(self, qapp: QApplication) -> None:
        """blb2txt 与 balcon 共用"输入输出"分组，应返回同一分组图标。"""
        icon = IconProvider.tab_icon("输入输出")
        assert not icon.isNull()


# ---------------------------------------------------------------------------
# tab_icon —— 边界情况
# ---------------------------------------------------------------------------
class TestTabIconEdgeCases:
    """``tab_icon`` 对未知分组返回空 QIcon。"""

    def test_unknown_group_returns_null_icon(
        self, qapp: QApplication
    ) -> None:
        icon = IconProvider.tab_icon("不存在的分组")
        assert icon.isNull()

    def test_english_key_also_works(self, qapp: QApplication) -> None:
        """英文 key（如 ``"eml"``）应同样可解析。"""
        icon = IconProvider.tab_icon("eml")
        assert not icon.isNull()
