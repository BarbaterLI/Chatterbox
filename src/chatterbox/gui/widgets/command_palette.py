"""命令面板对话框：提供模糊搜索 + 键盘导航的命令选择界面。

提供 :class:`Command` 数据模型与 :class:`CommandPalette` 对话框。
用户输入关键字模糊匹配命令标题，通过键盘 Up/Down 导航、Enter 执行
选中命令并关闭对话框，Esc 取消。

约束：
- 使用 PySide6（QDialog、QLineEdit、QListWidget、QLabel 等）。
- 不写自定义 QSS，保留 Qt 原版样式；快捷键与占位文本的灰色通过
  ``QPalette`` 设置（非样式表）。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """命令项数据模型。

    Args:
        id: 命令唯一标识（如 "tab.voice"）
        title: 显示标题（如 "跳转到语音与静音"）
        group: 分组（如 "导航"、"工具"、"预设"、"主题"）
        shortcut: 可选快捷键文本（如 "Ctrl+1"）
        handler: 无参回调，触发时调用
    """

    id: str
    title: str
    group: str = ""
    shortcut: str = ""
    handler: Callable[[], None] = field(default=lambda: None)


class CommandPalette(QDialog):
    """命令面板对话框。

    顶部搜索框 + 中间命令列表，支持模糊匹配与键盘导航。
    按 ``group`` 分组排序（同组相邻，组间无标题分隔，仅靠排序聚集）。

    Signals:
        command_triggered(str): 命令执行前发射，参数为 command.id，
            便于外部记录。
    """

    command_triggered = Signal(str)

    def __init__(
        self,
        commands: list[Command],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._commands: list[Command] = list(commands)
        self._build_ui()
        self._populate()
        self._apply_filter("")
        self.setModal(True)
        self.resize(600, 400)
        # 初始状态：清空搜索框、选中第一项、焦点在搜索框
        self.search_box.clear()
        self._select_first_visible()
        self.search_box.setFocus()
        logger.debug(
            "CommandPalette 已初始化，共 %d 条命令", len(self._commands)
        )

    # ----------------------------------------------------------------------
    # UI 构建
    # ----------------------------------------------------------------------
    def _build_ui(self) -> None:
        """构建搜索框 + 命令列表 + 占位标签的垂直布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("输入命令名…")
        self.search_box.textChanged.connect(self._apply_filter)

        self.list_widget = QListWidget(self)
        self.list_widget.itemActivated.connect(self._on_item_activated)

        self.placeholder_label = QLabel("无匹配命令", self)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 灰色文字通过 QPalette 设置（非 QSS）
        pal = self.placeholder_label.palette()
        pal.setColor(
            QPalette.ColorRole.WindowText,
            pal.color(QPalette.ColorRole.Mid),
        )
        self.placeholder_label.setPalette(pal)
        self.placeholder_label.hide()

        layout.addWidget(self.search_box)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.placeholder_label, 1)

        # 安装事件过滤器以捕获键盘事件（Enter/Esc/Up/Down）
        self.search_box.installEventFilter(self)
        self.list_widget.installEventFilter(self)

    def _populate(self) -> None:
        """按 group 稳定排序后填充列表（同组保持插入顺序相邻排列）。"""
        sorted_cmds = sorted(self._commands, key=lambda c: c.group)
        self.list_widget.clear()
        for cmd in sorted_cmds:
            item = QListWidgetItem(self.list_widget)
            widget = self._make_item_widget(cmd)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)
            item.setData(Qt.ItemDataRole.UserRole, cmd)

    def _make_item_widget(self, cmd: Command) -> QWidget:
        """创建单个命令项的自定义 widget（标题 + 右侧灰色快捷键）。"""
        widget = QWidget(self.list_widget)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        title_label = QLabel(cmd.title, widget)
        layout.addWidget(title_label, 1)

        if cmd.shortcut:
            shortcut_label = QLabel(cmd.shortcut, widget)
            # 灰色快捷键通过 QPalette 设置（非 QSS）
            pal = shortcut_label.palette()
            pal.setColor(
                QPalette.ColorRole.WindowText,
                pal.color(QPalette.ColorRole.Mid),
            )
            shortcut_label.setPalette(pal)
            layout.addWidget(shortcut_label, 0)

        return widget

    # ----------------------------------------------------------------------
    # 过滤
    # ----------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        """按标题子串（不区分大小写）过滤命令列表。

        无匹配时隐藏列表并显示占位标签；有匹配时恢复列表并选中第一项。
        """
        keyword = text.strip().lower()
        visible_count = 0
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            cmd: Command = item.data(Qt.ItemDataRole.UserRole)
            matched = not keyword or keyword in cmd.title.lower()
            item.setHidden(not matched)
            if matched:
                visible_count += 1

        if visible_count == 0:
            self.list_widget.hide()
            self.placeholder_label.show()
        else:
            self.list_widget.show()
            self.placeholder_label.hide()
            self._select_first_visible()

    def _select_first_visible(self) -> None:
        """选中第一个可见项；无可见项时清除选中。"""
        for i in range(self.list_widget.count()):
            if not self.list_widget.item(i).isHidden():
                self.list_widget.setCurrentRow(i)
                return
        self.list_widget.setCurrentRow(-1)

    # ----------------------------------------------------------------------
    # 执行
    # ----------------------------------------------------------------------
    def _current_command(self) -> Command | None:
        """返回当前选中的命令；无选中或选中项隐藏时返回 None。"""
        row = self.list_widget.currentRow()
        if row < 0:
            return None
        item = self.list_widget.item(row)
        if item is None or item.isHidden():
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _execute_current(self) -> None:
        """执行当前选中命令：发射信号 → 调用 handler → accept。"""
        cmd = self._current_command()
        if cmd is None:
            return
        self.command_triggered.emit(cmd.id)
        try:
            cmd.handler()
        except Exception:
            logger.exception("命令 %s 执行失败", cmd.id)
        self.accept()

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        """双击/激活项时执行（Enter 由事件过滤器统一处理）。"""
        self._execute_current()

    # ----------------------------------------------------------------------
    # 事件过滤
    # ----------------------------------------------------------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """捕获 Enter/Esc 全局快捷键，以及搜索框中的 Up/Down 导航。"""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            # Enter/Return：执行当前选中命令
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._execute_current()
                return True
            # Esc：关闭对话框
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
            # 搜索框中 Up/Down：导航列表（跳过隐藏项）
            if obj is self.search_box and key in (
                Qt.Key.Key_Down,
                Qt.Key.Key_Up,
            ):
                self._navigate_list(key)
                return True
        return super().eventFilter(obj, event)

    def _navigate_list(self, key: int) -> None:
        """在搜索框中按 Up/Down 导航列表（跳过隐藏项）。"""
        count = self.list_widget.count()
        if count == 0:
            return
        current = self.list_widget.currentRow()
        if key == Qt.Key.Key_Down:
            for next_row in range(current + 1, count):
                if not self.list_widget.item(next_row).isHidden():
                    self.list_widget.setCurrentRow(next_row)
                    return
        else:  # Up
            for prev_row in range(current - 1, -1, -1):
                if not self.list_widget.item(prev_row).isHidden():
                    self.list_widget.setCurrentRow(prev_row)
                    return


__all__ = ["Command", "CommandPalette"]
