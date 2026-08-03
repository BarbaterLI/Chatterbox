"""T-C2: FileListWidget 多列显示与排序功能测试。

验证：
- 添加文件后列表项显示多列文本（文件名 | 大小 | 类型 | 修改时间）
- 点击「大小」列头排序（升序/降序切换）
- 列头显示排序方向指示符（▲ / ▼）
- 拖拽功能仍可工作（acceptDrops 属性与 dragEnterEvent）
- 排序键存储在 ``Qt.UserRole + 1``（即 ``SORT_KEY_ROLE``）
- 按类型分组开关与分组标题项行为

测试在无显示环境下运行，使用 ``QT_QPA_PLATFORM=offscreen`` 平台插件。
"""
from __future__ import annotations

import os
import time

# 在导入 PySide6 之前设置 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QFont
from PySide6.QtWidgets import QApplication

import pytest

from balcon_batch_tts.core.tool_type import ToolType
from balcon_batch_tts.gui.widgets.file_list_widget import (
    GROUP_HEADER_ROLE,
    SORT_KEY_ROLE,
    FileListWidget,
    SortableListWidgetItem,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """模块级 QApplication 单例 fixture。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 多列显示
# ---------------------------------------------------------------------------
class TestMultiColumnDisplay:
    """列表项多列文本显示。"""

    def test_item_contains_filename(self, qapp: QApplication, tmp_path) -> None:
        """项文本应包含文件名。"""
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        item = widget.list_widget.item(0)
        assert "hello.txt" in item.text()

    def test_item_contains_size(self, qapp: QApplication, tmp_path) -> None:
        """项文本应包含文件大小（B/KB/MB）。"""
        f = tmp_path / "size_test.txt"
        f.write_text("ab", encoding="utf-8")  # 2 bytes

        widget = FileListWidget()
        widget.add_files([str(f)])

        text = widget.list_widget.item(0).text()
        assert "B" in text  # "2 B"

    def test_item_contains_type(self, qapp: QApplication, tmp_path) -> None:
        """项文本应包含文件类型（扩展名大写）。"""
        f = tmp_path / "doc.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        text = widget.list_widget.item(0).text()
        assert ".TXT" in text

    def test_item_contains_mtime(self, qapp: QApplication, tmp_path) -> None:
        """项文本应包含修改时间（YYYY-MM-DD HH:MM 格式）。"""
        f = tmp_path / "dated.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        text = widget.list_widget.item(0).text()
        # 检查末尾有日期时间格式的文本（YYYY-MM-DD HH:MM）
        # 去掉首尾空白后，最后 16 个字符应为日期时间
        stripped = text.rstrip()
        mtime_part = stripped[-16:]
        # 格式应为 "YYYY-MM-DD HH:MM"
        assert len(mtime_part) == 16
        assert mtime_part[4] == "-"
        assert mtime_part[7] == "-"
        assert mtime_part[10] == " "
        assert mtime_part[13] == ":"

    def test_item_contains_all_four_columns(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """项文本应同时包含文件名、大小、类型、修改时间四列。"""
        f = tmp_path / "complete.txt"
        f.write_text("data", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        text = widget.list_widget.item(0).text()
        assert "complete.txt" in text
        assert ".TXT" in text
        assert "B" in text
        # 末尾有日期时间
        stripped = text.rstrip()
        mtime_part = stripped[-16:]
        assert mtime_part[4] == "-" and mtime_part[13] == ":"

    def test_list_uses_monospace_font(
        self, qapp: QApplication
    ) -> None:
        """列表应使用等宽字体。"""
        widget = FileListWidget()
        font = widget.list_widget.font()
        assert font.styleHint() == QFont.StyleHint.Monospace

    def test_size_formats_as_kb(self, qapp: QApplication, tmp_path) -> None:
        """较大文件应格式化为 KB。"""
        f = tmp_path / "big.txt"
        f.write_text("x" * 2048, encoding="utf-8")  # 2 KB

        widget = FileListWidget()
        widget.add_files([str(f)])

        text = widget.list_widget.item(0).text()
        assert "KB" in text

    def test_different_extensions_show_different_types(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """不同扩展名的文件应显示不同类型。"""
        from balcon_batch_tts.gui.widgets.file_list_widget import (
            _BLB2TXT_DRAG_EXTENSIONS,
        )

        if ".pdf" not in _BLB2TXT_DRAG_EXTENSIONS:
            pytest.skip(".pdf not supported")

        txt = tmp_path / "a.txt"
        txt.write_text("a", encoding="utf-8")
        pdf = tmp_path / "b.pdf"
        pdf.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(txt), str(pdf)])

        texts = [
            widget.list_widget.item(i).text()
            for i in range(widget.list_widget.count())
        ]
        assert any(".TXT" in t for t in texts)
        assert any(".PDF" in t for t in texts)


# ---------------------------------------------------------------------------
# 排序功能
# ---------------------------------------------------------------------------
class TestSorting:
    """列头排序行为。"""

    def test_sort_by_size_ascending(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """点击「大小」列头应按文件大小升序排列。"""
        f1 = tmp_path / "small.txt"
        f1.write_text("a", encoding="utf-8")
        time.sleep(0.02)
        f2 = tmp_path / "medium.txt"
        f2.write_text("a" * 100, encoding="utf-8")
        time.sleep(0.02)
        f3 = tmp_path / "large.txt"
        f3.write_text("a" * 10000, encoding="utf-8")

        widget = FileListWidget()
        # 按非排序顺序添加
        widget.add_files([str(f3), str(f1), str(f2)])

        # 点击「大小」列头（column 1）
        widget._on_header_clicked(1)

        sizes = [
            widget.list_widget.item(i).data(SORT_KEY_ROLE)[1]
            for i in range(widget.list_widget.count())
        ]
        assert sizes == sorted(sizes)
        assert sizes[0] < sizes[-1]

    def test_sort_by_size_descending(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """再次点击「大小」列头应切换为降序。"""
        f1 = tmp_path / "small.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "large.txt"
        f2.write_text("a" * 10000, encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f1), str(f2)])

        # 第一次点击：升序
        widget._on_header_clicked(1)
        sizes_asc = [
            widget.list_widget.item(i).data(SORT_KEY_ROLE)[1]
            for i in range(widget.list_widget.count())
        ]
        assert sizes_asc == sorted(sizes_asc)

        # 第二次点击：降序
        widget._on_header_clicked(1)
        sizes_desc = [
            widget.list_widget.item(i).data(SORT_KEY_ROLE)[1]
            for i in range(widget.list_widget.count())
        ]
        assert sizes_desc == sorted(sizes_desc, reverse=True)

    def test_sort_by_filename_ascending(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """点击「文件名」列头应按文件名升序排列。"""
        f_c = tmp_path / "charlie.txt"
        f_c.write_text("c", encoding="utf-8")
        f_a = tmp_path / "alpha.txt"
        f_a.write_text("a", encoding="utf-8")
        f_b = tmp_path / "bravo.txt"
        f_b.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f_c), str(f_a), str(f_b)])

        widget._on_header_clicked(0)  # filename column

        names = [
            widget.list_widget.item(i).data(SORT_KEY_ROLE)[0]
            for i in range(widget.list_widget.count())
        ]
        assert names == sorted(names)
        assert names[0] == "alpha.txt"

    def test_sort_key_stored_in_user_role_plus_1(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """排序键应存储在 ``Qt.UserRole + 1``（即 ``SORT_KEY_ROLE``）。"""
        f = tmp_path / "keytest.txt"
        f.write_text("hello", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        item = widget.list_widget.item(0)
        keys = item.data(SORT_KEY_ROLE)

        assert keys is not None
        # PySide6 通过 QVariant 存储时可能将 tuple 转为 list
        assert isinstance(keys, (tuple, list))
        assert len(keys) == 4
        # filename_lower
        assert keys[0] == "keytest.txt"
        # size_int
        assert isinstance(keys[1], int)
        assert keys[1] == 5
        # ext_lower
        assert keys[2] == ".txt"
        # mtime_float
        assert isinstance(keys[3], float)
        assert keys[3] > 0

    def test_sort_key_role_equals_user_role_plus_1(self) -> None:
        """``SORT_KEY_ROLE`` 常量应等于 ``Qt.UserRole + 1``。"""
        assert SORT_KEY_ROLE == Qt.UserRole + 1

    def test_items_use_sortable_subclass(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """添加的项应为 ``SortableListWidgetItem`` 实例。"""
        f = tmp_path / "subclass.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        item = widget.list_widget.item(0)
        assert isinstance(item, SortableListWidgetItem)

    def test_sort_by_type(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """点击「类型」列头应按扩展名排序。"""
        from balcon_batch_tts.gui.widgets.file_list_widget import (
            _BLB2TXT_DRAG_EXTENSIONS,
        )

        if ".pdf" not in _BLB2TXT_DRAG_EXTENSIONS:
            pytest.skip(".pdf not supported")

        txt = tmp_path / "z.txt"
        txt.write_text("t", encoding="utf-8")
        pdf = tmp_path / "a.pdf"
        pdf.write_text("p", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(txt), str(pdf)])

        widget._on_header_clicked(2)  # type column

        types = [
            widget.list_widget.item(i).data(SORT_KEY_ROLE)[2]
            for i in range(widget.list_widget.count())
        ]
        assert types == sorted(types)
        # ".pdf" < ".txt"
        assert types[0] == ".pdf"


# ---------------------------------------------------------------------------
# 列头排序方向指示符
# ---------------------------------------------------------------------------
class TestHeaderIndicators:
    """列头排序方向指示符（▲ / ▼）。"""

    def test_ascending_indicator_shown(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """升序时列头应显示 ▲。"""
        f = tmp_path / "ind1.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])
        widget._on_header_clicked(1)  # ascending

        header_text = widget._header_labels[1].text()
        assert "▲" in header_text

    def test_descending_indicator_shown(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """降序时列头应显示 ▼。"""
        f = tmp_path / "ind2.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])
        widget._on_header_clicked(1)  # ascending
        widget._on_header_clicked(1)  # descending

        header_text = widget._header_labels[1].text()
        assert "▼" in header_text

    def test_inactive_column_no_indicator(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """非当前排序列头不应显示指示符。"""
        f = tmp_path / "ind3.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])
        widget._on_header_clicked(1)  # sort by size

        # filename header (column 0) should not have indicator
        header_text = widget._header_labels[0].text()
        assert "▲" not in header_text
        assert "▼" not in header_text

    def test_indicator_switches_on_toggle(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """连续点击同一列头应切换 ▲ / ▼。"""
        f = tmp_path / "toggle.txt"
        f.write_text("x", encoding="utf-8")

        widget = FileListWidget()
        widget.add_files([str(f)])

        widget._on_header_clicked(1)
        assert "▲" in widget._header_labels[1].text()

        widget._on_header_clicked(1)
        assert "▼" in widget._header_labels[1].text()

        widget._on_header_clicked(1)
        assert "▲" in widget._header_labels[1].text()

    def test_four_header_labels_exist(
        self, qapp: QApplication
    ) -> None:
        """应存在 4 个列头标签。"""
        widget = FileListWidget()
        assert len(widget._header_labels) == 4


# ---------------------------------------------------------------------------
# 拖拽功能仍可工作
# ---------------------------------------------------------------------------
class TestDragStillWorks:
    """拖拽功能在添加排序后仍可工作。"""

    def test_list_widget_accept_drops(
        self, qapp: QApplication
    ) -> None:
        """``list_widget`` 应启用 ``acceptDrops``。"""
        widget = FileListWidget()
        assert widget.list_widget.acceptDrops() is True

    def test_widget_accept_drops(self, qapp: QApplication) -> None:
        """``FileListWidget`` 本身应启用 ``acceptDrops``。"""
        widget = FileListWidget()
        assert widget.acceptDrops() is True

    def test_drag_enter_event_accepted(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """拖拽进入事件（uri-list）应被接受。"""
        widget = FileListWidget()

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "drag.txt"))])
        event = QDragEnterEvent(
            QPoint(0, 0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        widget.dragEnterEvent(event)
        assert event.isAccepted()

    def test_drag_enter_event_ignores_non_uri(
        self, qapp: QApplication
    ) -> None:
        """非 uri-list 的拖拽进入事件应被忽略。"""
        widget = FileListWidget()

        mime = QMimeData()
        mime.setText("plain text")
        event = QDragEnterEvent(
            QPoint(0, 0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        widget.dragEnterEvent(event)
        assert not event.isAccepted()


# ---------------------------------------------------------------------------
# 按类型分组
# ---------------------------------------------------------------------------
class TestGroupByType:
    """按类型分组开关行为。"""

    def test_checkbox_exists_and_defaults_off(
        self, qapp: QApplication
    ) -> None:
        """分组开关应存在且默认关闭。"""
        widget = FileListWidget()
        assert widget.group_by_type_check is not None
        assert widget.group_by_type_check.isChecked() is False

    def test_enabling_grouping_adds_headers(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """开启分组后应显示分组标题项。"""
        f1 = tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("b", encoding="utf-8")
        f3 = tmp_path / "c.pdf"
        f3.write_text("c", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(f1), str(f2), str(f3)])

        widget.group_by_type_check.setChecked(True)

        has_header = any(
            widget.list_widget.item(i).data(GROUP_HEADER_ROLE)
            for i in range(widget.list_widget.count())
        )
        assert has_header

    def test_disabling_grouping_removes_headers(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """关闭分组后应移除分组标题项。"""
        f1 = tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.pdf"
        f2.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(f1), str(f2)])

        widget.group_by_type_check.setChecked(True)
        widget.group_by_type_check.setChecked(False)

        has_header = any(
            widget.list_widget.item(i).data(GROUP_HEADER_ROLE)
            for i in range(widget.list_widget.count())
        )
        assert not has_header

    def test_get_files_skips_group_headers(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """``get_files`` 应跳过分组标题项。"""
        f1 = tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.pdf"
        f2.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(f1), str(f2)])

        widget.group_by_type_check.setChecked(True)

        files = widget.get_files()
        assert len(files) == 2  # 不含分组标题项

    def test_group_header_items_non_selectable(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """分组标题项应不可选中。"""
        f1 = tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.pdf"
        f2.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(f1), str(f2)])

        widget.group_by_type_check.setChecked(True)

        for i in range(widget.list_widget.count()):
            item = widget.list_widget.item(i)
            if item.data(GROUP_HEADER_ROLE):
                flags = item.flags()
                assert not (flags & Qt.ItemFlag.ItemIsSelectable)

    def test_count_excludes_group_headers(
        self, qapp: QApplication, tmp_path
    ) -> None:
        """计数徽章应排除分组标题项。"""
        f1 = tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.pdf"
        f2.write_text("b", encoding="utf-8")

        widget = FileListWidget()
        widget.set_tool(ToolType.BLB2TXT)
        widget.add_files([str(f1), str(f2)])

        widget.group_by_type_check.setChecked(True)

        # count_label 应显示 "共 2 个"
        assert "共 2 个" in widget.count_label.text()
