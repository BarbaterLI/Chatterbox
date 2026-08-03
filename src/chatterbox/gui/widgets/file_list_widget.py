"""文件列表控件：支持拖拽与对话框添加待处理文件。

提供 ``FileListWidget``，封装 QListWidget + 操作按钮，支持：
- 通过文件对话框多选添加文件
- 通过文件对话框选择文件夹，递归扫描其中匹配扩展名的文件
- 通过文件对话框选择 ``-fl`` 文本列表文件，按行解析路径
- 拖拽本地文件或文件夹到列表添加（文件夹递归扫描）
- 移除选中项、清空列表
- 文件列表变化时通过 ``files_changed`` 信号通知外部
- 空状态提示、拖拽视觉反馈、文件计数徽章、右键上下文菜单

Task 11e 优化（Qt6 原生动画）：
- 拖拽进入时通过 :class:`QGraphicsDropShadowEffect` 阴影强度动画反馈
  （``blurRadius`` 从 0 → 15，``OutBack`` 缓动轻微回弹）
- 拖拽离开/放下时阴影强度反向动画（平滑收回）
- 动画通过 :class:`AnimationManager` 统一管理，支持「禁用动画」降级
- 不再使用局部 QSS 边框高亮，统一由 QGraphicsEffect 提供反馈

约束：
- 使用 PySide6（QGraphicsDropShadowEffect、QPropertyAnimation、QStackedWidget、
  QListWidget、QLabel、QPushButton、QMenu、QFileDialog、QHBoxLayout、
  QVBoxLayout、QSizePolicy、QAbstractItemView）。
- 不引入自定义 QSS，保留 Qt6 原版样式。
- Python 3.10+ 类型注解，启用 ``from __future__ import annotations``。
"""

from __future__ import annotations

import datetime
import logging
import os

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QMouseEvent,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.tool_type import ToolType
from chatterbox.gui.theme.design_tokens import DesignTokens
from chatterbox.gui.widgets.animation_manager import AnimationManager

logger = logging.getLogger(__name__)

# 文件对话框过滤器：balcon 模式（文本/字幕文件）
_BALCON_FILE_FILTER = (
    "文本文件 (*.txt);;"
    "字幕文件 (*.srt *.lrc *.ssa *.ass *.smi *.vtt);;"
    "所有文件 (*.*)"
)

# 文件对话框过滤器：blb2txt 模式（文档文件，覆盖 spec 全部扩展名）
_BLB2TXT_FILE_FILTER = (
    "文档文件 (*.pdf *.docx *.doc *.epub *.fb2 *.html *.htm *.lit *.md "
    "*.mht *.mobi *.odp *.ods *.odt *.pdb *.prc *.rtf *.tcr *.txt *.txtz "
    "*.wpd *.wri *.xls *.xlsx *.ppt *.pptx *.azw *.azw3 *.chm *.djvu);;"
    "所有文件 (*.*)"
)

# 文件对话框过滤器：SAPI 模式（文本/字幕文件，支持 xml 供 SSML 使用）
_SAPI_FILE_FILTER = (
    "文本文件 (*.txt *.srt *.lrc *.ass *.ssa *.xml);;所有文件 (*.*)"
)

# 拖拽扩展名白名单：balcon 模式（文本/字幕）
_BALCON_DRAG_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".srt", ".lrc", ".ssa", ".ass", ".smi", ".vtt"}
)

# 拖拽扩展名白名单：blb2txt 模式（文档类型，与 _BLB2TXT_FILE_FILTER 一致）
_BLB2TXT_DRAG_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf", ".docx", ".doc", ".epub", ".fb2", ".html", ".htm", ".lit",
        ".md", ".mht", ".mobi", ".odp", ".ods", ".odt", ".pdb", ".prc",
        ".rtf", ".tcr", ".txt", ".txtz", ".wpd", ".wri", ".xls", ".xlsx",
        ".ppt", ".pptx", ".azw", ".azw3", ".chm", ".djvu",
    }
)

# 拖拽扩展名白名单：SAPI 模式（文本/字幕，与 _SAPI_FILE_FILTER 一致）
_SAPI_DRAG_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".srt", ".lrc", ".ass", ".ssa", ".xml"}
)

# Task 11e：拖拽阴影反馈参数
# 阴影颜色由 DesignTokens.color_drag_shadow() 运行时提供
_DRAG_SHADOW_BLUR_RADIUS_MAX = 15.0  # 拖拽进入时最大模糊半径
_DRAG_SHADOW_BLUR_RADIUS_MIN = 0.0   # 默认与离开时模糊半径
_DRAG_SHADOW_OFFSET = 4  # 阴影偏移（让阴影更明显）
_DRAG_ANIM_DURATION_MS = 250  # 阴影动画时长（OutBack 缓动）

# T-C2: 多列显示与排序配置
# 列定义: (键名, 列头文本, 列宽字符数)
_COLUMNS: list[tuple[str, str, int]] = [
    ("filename", "文件名", 32),
    ("size", "大小", 10),
    ("type", "类型", 8),
    ("mtime", "修改时间", 17),
]

# 排序键存储角色: 存储 tuple (filename_lower, size_int, ext_lower, mtime_float)
SORT_KEY_ROLE: int = Qt.UserRole + 1

# 分组标题项标记角色: 存储 bool (True 表示该项是分组标题)
GROUP_HEADER_ROLE: int = Qt.UserRole + 2

# 排序方向指示符
_SORT_ASC_INDICATOR = " ▲"
_SORT_DESC_INDICATOR = " ▼"


class SortableListWidgetItem(QListWidgetItem):
    """支持多列排序的 QListWidgetItem 子类。

    排序键存储在 ``SORT_KEY_ROLE``，格式为 tuple:
    ``(filename_lower, size_int, ext_lower, mtime_float)``。

    当前排序列由类属性 ``_sort_column`` 控制
    （0=文件名, 1=大小, 2=类型, 3=修改时间）。
    排序时 ``QListWidget.sortItems()`` 调用 ``operator<``，此处覆盖
    ``__lt__`` 从排序键中取出对应列的值进行比较。
    """

    # 类级排序列索引（由 FileListWidget 在点击列头时设置）
    _sort_column: int = 0

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, QListWidgetItem):
            return False
        my_keys = self.data(SORT_KEY_ROLE)
        other_keys = other.data(SORT_KEY_ROLE)
        if my_keys is not None and other_keys is not None:
            col = SortableListWidgetItem._sort_column
            try:
                my_val = my_keys[col]
                other_val = other_keys[col]
                if my_val is None:
                    my_val = ""
                if other_val is None:
                    other_val = ""
                return bool(my_val < other_val)
            except (IndexError, TypeError):
                pass
        # 回退到文本比较（大小写不敏感）
        return self.text().lower() < other.text().lower()


class HeaderLabel(QLabel):
    """可点击的列头标签，点击时发射 ``column_clicked`` 信号。"""

    column_clicked = Signal(int)

    def __init__(
        self, text: str, column: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self._column = column

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.column_clicked.emit(self._column)
        super().mousePressEvent(event)


class FileListWidget(QWidget):
    """待处理文件列表控件。

    继承 QWidget，封装列表与操作按钮，支持拖拽与 ``-fl`` 列表文件导入。

    Task 11e：拖拽进入时通过 :class:`QGraphicsDropShadowEffect` 阴影强度
    动画反馈（``blurRadius`` 0→15，``OutBack`` 缓动轻微回弹），动画通过
    :class:`AnimationManager` 统一管理，支持「禁用动画」降级。

    Signals:
        files_changed(list): 文件列表变化时发射，参数为 ``list[str]`` 绝对路径。
    """

    files_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 当前工具类型，默认 balcon（向后兼容）
        self._current_tool: ToolType = ToolType.BALCON

        # T-C2: 排序状态
        self._sort_column: int = 0  # 0=文件名, 1=大小, 2=类型, 3=修改时间
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
        self._has_sorted: bool = False
        self._group_by_type_enabled: bool = False
        self._header_labels: list[HeaderLabel] = []

        # 列表
        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # T-C2: 列表使用等宽字体（用于多列对齐）
        mono_font = QFont("Courier New", 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setFixedPitch(True)
        self.list_widget.setFont(mono_font)

        # 空状态提示（文案随 _current_tool 切换）
        # T-D3: 主提示 + 副提示差异化
        self.empty_label = QLabel(self._empty_label_text(), self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setMinimumWidth(100)
        self.empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        empty_font = self.empty_label.font()
        ps = empty_font.pointSize()
        if ps <= 0:
            ps = 9
        empty_font.setPointSize(ps + 2)
        self.empty_label.setFont(empty_font)
        palette = self.empty_label.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText, DesignTokens.color_neutral()
        )
        self.empty_label.setPalette(palette)

        # T-D3: 副提示行（小号灰色字「拖入文件夹将递归扫描」）
        self.empty_sub_label = QLabel("拖入文件夹将递归扫描", self)
        self.empty_sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        sub_font = self.empty_sub_label.font()
        sub_ps = sub_font.pointSize()
        if sub_ps <= 0:
            sub_ps = 9
        sub_font.setPointSize(max(1, sub_ps - 1))
        self.empty_sub_label.setFont(sub_font)
        self._apply_sub_label_color()

        # T-D3: 空状态容器（主提示 + 副提示垂直居中排列）
        self.empty_container = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addWidget(self.empty_sub_label)
        empty_layout.addStretch()

        # 用 QStackedWidget 包装：page 0 = 空提示容器，page 1 = 列表
        self.stacked_widget = QStackedWidget(self)
        self.stacked_widget.addWidget(self.empty_container)    # index 0
        self.stacked_widget.addWidget(self.list_widget)        # index 1

        # Task 11e：QGraphicsDropShadowEffect 应用到 stacked_widget
        # 阴影颜色与原 QSS 边框颜色一致，blurRadius 默认 0（不可见）
        self._shadow_effect = QGraphicsDropShadowEffect(self.stacked_widget)
        self._shadow_effect.setColor(DesignTokens.color_drag_shadow())
        self._shadow_effect.setBlurRadius(_DRAG_SHADOW_BLUR_RADIUS_MIN)
        self._shadow_effect.setOffset(_DRAG_SHADOW_OFFSET)
        self.stacked_widget.setGraphicsEffect(self._shadow_effect)

        # Task 11e：拖拽阴影动画引用（持有以防止 GC）
        self._shadow_anim: QPropertyAnimation | None = None

        # 按钮
        self.add_files_btn = QPushButton("添加文件", self)
        self.add_folder_btn = QPushButton("添加文件夹", self)
        self.add_file_list_btn = QPushButton("添加列表", self)
        self.add_file_list_btn.setToolTip(
            "添加文件列表 (-fl)：从文本文件批量导入路径"
        )
        self.remove_selected_btn = QPushButton("移除选中", self)
        self.clear_btn = QPushButton("清空", self)

        # 限制按钮最小宽度，避免按钮行强制撑宽整个控件
        for btn in (self.add_files_btn, self.add_folder_btn,
                     self.add_file_list_btn, self.remove_selected_btn,
                     self.clear_btn):
            btn.setMinimumWidth(40)

        # 文件计数徽章
        self.count_label = QLabel("共 0 个文件", self)

        # T-C2: 按类型分组开关（默认关闭）
        self.group_by_type_check = QCheckBox("按类型分组", self)
        self.group_by_type_check.setChecked(False)
        self.group_by_type_check.setToolTip("开启后按扩展名分组显示")

        # 按钮行
        button_row = QHBoxLayout()
        button_row.addWidget(self.add_files_btn)
        button_row.addWidget(self.add_folder_btn)
        button_row.addWidget(self.add_file_list_btn)
        button_row.addWidget(self.remove_selected_btn)
        button_row.addWidget(self.clear_btn)
        button_row.addStretch()
        button_row.addWidget(self.group_by_type_check)
        button_row.addWidget(self.count_label)

        # T-C2: 列头行（4 个可点击 HeaderLabel，与列表项列对齐）
        char_width = max(self.list_widget.fontMetrics().horizontalAdvance("M"), 6)
        header_row = QHBoxLayout()
        header_row.setSpacing(0)
        header_row.setContentsMargins(0, 0, 0, 0)
        stretch_factors = [3, 1, 1, 1]
        for i, (_key, text, width_chars) in enumerate(_COLUMNS):
            label = HeaderLabel(text, i, self)
            label.setFont(self.list_widget.font())
            label.setMinimumWidth(char_width * 4 + 10)
            label.column_clicked.connect(self._on_header_clicked)
            self._header_labels.append(label)
            header_row.addWidget(label, stretch_factors[i])
        header_row.addStretch()

        # 主布局
        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addLayout(header_row)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)

        # 信号连接
        self.add_files_btn.clicked.connect(self.add_files_dialog)
        self.add_folder_btn.clicked.connect(self.add_folder_dialog)
        self.add_file_list_btn.clicked.connect(self.add_file_list_dialog)
        self.remove_selected_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.clear_all)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemSelectionChanged.connect(self._update_count)
        self.group_by_type_check.toggled.connect(self._toggle_group_by_type)

        # 启用拖拽接收
        self.setAcceptDrops(True)

        # 初始化空状态与计数
        self._update_empty_state()
        self._update_count()

        logger.debug("FileListWidget 已初始化")

    # ----------------------------------------------------------------------
    # 内部：空状态、计数、上下文菜单
    # ----------------------------------------------------------------------
    def _empty_label_text(self) -> str:
        """根据当前工具返回空状态主提示文案（T-D3 差异化）。"""
        if self._current_tool is ToolType.BLB2TXT:
            return (
                "拖入文档或点击添加（PDF 自动选用主版本，"
                "支持 .pdf .docx .doc .xlsx .xls .pptx .ppt .epub .html .txt）"
            )
        if self._current_tool is ToolType.SAPI:
            return (
                "拖入文本文件或点击添加"
                "（支持 .txt .srt .lrc .ass .ssa .xml）"
            )
        return (
            "拖入文件或点击添加"
            "（支持 .txt .srt .lrc .vtt .ssa .ass .smi .md .xml）"
        )

    def _apply_sub_label_color(self) -> None:
        """从 :class:`DesignTokens` 读取中性灰并应用到副提示标签。

        T-D3: 副提示颜色不硬编码，统一由 ``DesignTokens.color_neutral()``
        提供（亮主题 ``#555555`` / 暗主题 ``#9ca3af``）。
        """
        palette = self.empty_sub_label.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText, DesignTokens.color_neutral()
        )
        self.empty_sub_label.setPalette(palette)

    def _get_file_filter(self) -> str:
        """根据当前工具返回文件对话框过滤器字符串。"""
        if self._current_tool is ToolType.BLB2TXT:
            return _BLB2TXT_FILE_FILTER
        if self._current_tool is ToolType.SAPI:
            return _SAPI_FILE_FILTER
        return _BALCON_FILE_FILTER

    def _get_allowed_extensions(self) -> frozenset[str]:
        """根据当前工具返回拖拽允许的文件扩展名集合（小写，含点）。"""
        if self._current_tool is ToolType.BLB2TXT:
            return _BLB2TXT_DRAG_EXTENSIONS
        if self._current_tool is ToolType.SAPI:
            return _SAPI_DRAG_EXTENSIONS
        return _BALCON_DRAG_EXTENSIONS

    def _update_empty_state(self) -> None:
        """根据列表是否为空切换 QStackedWidget 当前页。"""
        if self.list_widget.count() == 0:
            self.stacked_widget.setCurrentIndex(0)
        else:
            self.stacked_widget.setCurrentIndex(1)

    def _update_count(self) -> None:
        """更新文件计数徽章文本（含已选数量）。"""
        selected = len(self.list_widget.selectedItems())
        # T-C2: 排除分组标题项
        file_count = sum(
            1
            for i in range(self.list_widget.count())
            if not self.list_widget.item(i).data(GROUP_HEADER_ROLE)
        )
        self.count_label.setText(
            f"共 {file_count} 个（已选 {selected}）"
        )

    def _refresh_count_label(self) -> None:
        """恢复 count_label 的正常计数文本（拖拽拒收提示 3 秒后调用）。"""
        self._update_count()

    def _set_drag_highlight(self, on: bool) -> None:
        """切换拖拽视觉反馈（Task 11e：QGraphicsDropShadowEffect 动画）。

        ``on=True``：启动 ``blurRadius`` 0→15 动画（OutBack 缓动轻微回弹）。
        ``on=False``：启动 ``blurRadius`` 当前→0 动画（平滑收回）。

        动画通过 :class:`AnimationManager` 创建，支持「禁用动画」降级
        （禁用时 duration=0，瞬时跳到目标值）。

        Args:
            on: ``True`` 表示拖拽进入（强化阴影）；``False`` 表示拖拽离开/放下（收回阴影）。
        """
        # 停止进行中的阴影动画
        if self._shadow_anim is not None:
            try:
                self._shadow_anim.stop()
            except RuntimeError:
                pass
            self._shadow_anim = None

        # 计算动画起止值
        current_blur = self._shadow_effect.blurRadius()
        if on:
            start = current_blur
            end = _DRAG_SHADOW_BLUR_RADIUS_MAX
        else:
            start = current_blur
            end = _DRAG_SHADOW_BLUR_RADIUS_MIN

        # 起止值相同，无需动画
        if abs(start - end) < 0.01:
            return

        # 通过 AnimationManager 创建动画（尊重禁用动画开关）
        anim_mgr = AnimationManager.instance()
        self._shadow_anim = anim_mgr.make_property_animation(
            target=self._shadow_effect,
            prop=b"blurRadius",
            start=start,
            end=end,
            duration=_DRAG_ANIM_DURATION_MS,
            easing=QEasingCurve.Type.OutBack,  # 拖拽反馈使用 OutBack（轻微回弹）
        )
        self._shadow_anim.start()

    def _show_context_menu(self, pos: QPoint) -> None:
        """右键上下文菜单：移除选中、清空、在资源管理器中显示。

        仅在列表非空且右键位置有项时显示。
        """
        if self.list_widget.count() == 0:
            return
        if self.list_widget.itemAt(pos) is None:
            return
        menu = QMenu(self)
        menu.addAction("移除选中", self.remove_selected)
        menu.addAction("清空", self.clear_all)
        menu.addSeparator()
        menu.addAction("在资源管理器中显示", self._reveal_selected_in_explorer)
        menu.exec(self.list_widget.viewport().mapToGlobal(pos))

    def _reveal_selected_in_explorer(self) -> None:
        """在 Windows 资源管理器中打开首个选中文件所在目录。"""
        selected = self.list_widget.selectedItems()
        if not selected:
            return
        item = selected[0]
        path = item.data(Qt.UserRole)
        if not path:
            path = item.text()
        if not path:
            return
        try:
            directory = os.path.dirname(path)
            if directory and os.path.isdir(directory):
                os.startfile(directory)  # type: ignore[attr-defined]
        except OSError as exc:
            logger.warning("无法打开资源管理器 %r: %s", path, exc)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数格式化为 B/KB/MB/GB 字符串。"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    # T-C2: 多列显示与排序辅助方法
    # ----------------------------------------------------------------------
    @staticmethod
    def _format_mtime(ts: float) -> str:
        """格式化修改时间戳为 ``YYYY-MM-DD HH:MM`` 字符串。"""
        try:
            dt = datetime.datetime.fromtimestamp(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            return "?"

    @staticmethod
    def _get_file_type(path: str) -> str:
        """获取文件类型字符串（扩展名大写或 ``DIR``）。"""
        if os.path.isdir(path):
            return "DIR"
        ext = os.path.splitext(path)[1].upper()
        return ext if ext else "FILE"

    @staticmethod
    def _format_display_text(
        filename: str, size_str: str, type_str: str, mtime_str: str
    ) -> str:
        """格式化多列显示文本（等宽字体对齐）。

        列宽由 ``_COLUMNS`` 定义，使用固定宽度空格填充。
        文件名超长时截断并添加省略号。
        """
        max_name = _COLUMNS[0][2]
        if len(filename) > max_name:
            display_name = filename[: max_name - 3] + "..."
        else:
            display_name = filename
        return (
            f"{display_name:<{max_name}} "
            f"{size_str:>{_COLUMNS[1][2]}} "
            f"{type_str:<{_COLUMNS[2][2]}} "
            f"{mtime_str:<{_COLUMNS[3][2]}}"
        )

    def _on_header_clicked(self, column: int) -> None:
        """点击列头：切换排序列与方向，然后排序。

        首次点击任意列头时设为升序；后续点击当前排序列时切换升序/降序；
        点击新列时设为升序。
        """
        if not self._has_sorted:
            # 首次排序：始终升序
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        elif column == self._sort_column:
            # 同列：切换方向
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                self._sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._sort_order = Qt.SortOrder.AscendingOrder
        else:
            # 新列：升序
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder

        self._has_sorted = True

        # 更新 SortableListWidgetItem 类级排序列
        SortableListWidgetItem._sort_column = self._sort_column

        self._update_header_indicators()

        if self._group_by_type_enabled:
            self._apply_grouping()
        else:
            self._apply_sort()

    def _update_header_indicators(self) -> None:
        """更新列头排序方向指示符（▲ 升序 / ▼ 降序）。"""
        for i, (_key, text, _width) in enumerate(_COLUMNS):
            if i == self._sort_column:
                if self._sort_order == Qt.SortOrder.AscendingOrder:
                    indicator = _SORT_ASC_INDICATOR
                else:
                    indicator = _SORT_DESC_INDICATOR
                self._header_labels[i].setText(text + indicator)
            else:
                self._header_labels[i].setText(text)

    def _apply_sort(self) -> None:
        """使用当前排序列与方向对列表排序。"""
        SortableListWidgetItem._sort_column = self._sort_column
        self.list_widget.sortItems(self._sort_order)

    def _toggle_group_by_type(self, checked: bool) -> None:
        """切换按类型分组模式。"""
        self._group_by_type_enabled = checked
        if checked:
            self._apply_grouping()
        else:
            self._remove_group_headers()
            self._apply_sort()
        self._update_count()

    def _apply_grouping(self) -> None:
        """按扩展名分组，在每组前插入分组标题项。"""
        # 取出所有项
        items: list[QListWidgetItem] = []
        while self.list_widget.count() > 0:
            items.append(self.list_widget.takeItem(0))

        # 过滤掉已有分组标题项
        file_items = [
            it for it in items if not it.data(GROUP_HEADER_ROLE)
        ]

        # 按类型（扩展名）排序
        file_items.sort(
            key=lambda it: (it.data(SORT_KEY_ROLE) or ("", 0, "", 0.0))[2]
        )

        # 按类型分组
        groups: dict[str, list[QListWidgetItem]] = {}
        for item in file_items:
            keys = item.data(SORT_KEY_ROLE) or ("", 0, "", 0.0)
            ext = keys[2]
            groups.setdefault(ext, []).append(item)

        # 重新添加（每组前插入标题项）
        for ext in sorted(groups.keys()):
            group_items = groups[ext]
            header = self._create_group_header(ext, len(group_items))
            self.list_widget.addItem(header)
            for item in group_items:
                self.list_widget.addItem(item)

    def _remove_group_headers(self) -> None:
        """移除所有分组标题项。"""
        i = 0
        while i < self.list_widget.count():
            item = self.list_widget.item(i)
            if item.data(GROUP_HEADER_ROLE):
                self.list_widget.takeItem(i)
            else:
                i += 1

    @staticmethod
    def _create_group_header(ext: str, count: int) -> QListWidgetItem:
        """创建一个分组标题项（不可选、加粗）。"""
        label = ext.upper() if ext else "FILE"
        header = QListWidgetItem(f"── {label} ({count}) ──")
        header.setData(GROUP_HEADER_ROLE, True)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        header.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return header

    # ----------------------------------------------------------------------
    # 公开方法
    # ----------------------------------------------------------------------
    def set_tool(self, tool: ToolType) -> None:
        """切换当前工具类型，更新空状态提示文案与文件过滤器。

        不立即弹出文件对话框，仅设置内部状态，后续 ``add_files_dialog``
        与拖拽事件将根据该状态选择对应的过滤器与扩展名白名单。

        T-D3: 切换工具时同时刷新副提示颜色（主题可能已变）。

        Args:
            tool: 工具类型枚举值（``ToolType.BALCON`` 或 ``ToolType.BLB2TXT``）。
        """
        if tool is self._current_tool:
            return
        self._current_tool = tool
        self.empty_label.setText(self._empty_label_text())
        self._apply_sub_label_color()
        logger.debug("FileListWidget 工具切换为 %s", tool.value)

    def add_files(self, files: list[str]) -> None:
        """添加文件到列表，按绝对路径去重，并发射 ``files_changed``。

        T-C2: 每项以多列等宽对齐显示（文件名 | 大小 | 类型 | 修改时间），
        完整路径存储在 ``Qt.UserRole``，排序键存储在 ``SORT_KEY_ROLE``
        （即 ``Qt.UserRole + 1``）。

        Args:
            files: 文件路径列表，相对路径会被转为绝对路径。
        """
        if not files:
            return

        existing = set(self.get_files())
        added = 0
        for path in files:
            if not path:
                continue
            try:
                abs_path = os.path.abspath(path)
            except (OSError, ValueError) as exc:
                logger.warning("无法解析路径 %r: %s", path, exc)
                continue
            if abs_path in existing:
                continue
            existing.add(abs_path)

            # T-C2: 多列显示文本（文件名 | 大小 | 类型 | 修改时间）
            filename = os.path.basename(abs_path)
            try:
                size = os.path.getsize(abs_path)
                size_str = self._format_size(size)
            except OSError:
                size = 0
                size_str = "?"
            try:
                mtime = os.path.getmtime(abs_path)
                mtime_str = self._format_mtime(mtime)
            except OSError:
                mtime = 0.0
                mtime_str = "?"
            type_str = self._get_file_type(abs_path)

            display_text = self._format_display_text(
                filename, size_str, type_str, mtime_str
            )

            # 排序键: (filename_lower, size_int, ext_lower, mtime_float)
            ext_lower = os.path.splitext(filename)[1].lower()
            sort_keys = (
                filename.lower(),
                size,
                ext_lower,
                mtime,
            )

            item = SortableListWidgetItem()
            item.setText(display_text)
            item.setData(Qt.UserRole, abs_path)
            item.setData(SORT_KEY_ROLE, sort_keys)
            item.setToolTip(abs_path)
            self.list_widget.addItem(item)
            added += 1

        if added > 0:
            logger.debug("已添加 %d 个文件", added)
            if self._group_by_type_enabled:
                self._apply_grouping()
            elif self._has_sorted:
                self._apply_sort()
            self._update_empty_state()
            self._update_count()
            self.files_changed.emit(self.get_files())

    def add_files_dialog(self) -> None:
        """打开文件对话框（多选），调用 ``add_files``。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择文件",
            "",
            self._get_file_filter(),
        )
        if paths:
            self.add_files(paths)

    def add_folder_dialog(self) -> None:
        """打开对话框选择一个文件夹，递归扫描其中匹配当前工具扩展名白名单的文件。

        使用 :meth:`QFileDialog.getExistingDirectory` 选择目录，调用
        :meth:`_collect_files_from_folder` 递归收集文件，最终通过
        :meth:`add_files` 添加到列表（复用去重与显示逻辑）。

        空目录或无匹配文件的目录将记录 info 日志，不弹错误对话框。
        """
        path = QFileDialog.getExistingDirectory(
            self,
            "选择文件夹",
            "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if not path:
            return

        allowed_ext = self._get_allowed_extensions()
        files = self._collect_files_from_folder(path, allowed_ext)
        if not files:
            logger.info(
                "文件夹 %s 中未找到当前工具 %s 支持的文件类型",
                path,
                self._current_tool.value,
            )
            return

        logger.debug("从文件夹 %s 扫描到 %d 个文件", path, len(files))
        self.add_files(files)

    @staticmethod
    def _collect_files_from_folder(
        folder: str, allowed_ext: frozenset[str]
    ) -> list[str]:
        """递归扫描文件夹，返回扩展名匹配的文件绝对路径列表。

        使用 :func:`os.walk` 递归遍历，按 ``allowed_ext``（小写含点）
        过滤。符号链接不会被跟随（``os.walk(followlinks=False)`` 默认行为），
        避免循环引用风险。无读取权限的子目录会被跳过并记录 warning。

        Args:
            folder: 要扫描的根文件夹路径。
            allowed_ext: 允许的扩展名集合（小写含点，如 ``{".txt", ".srt"}``）。

        Returns:
            匹配文件的绝对路径列表，按 ``os.walk`` 的遍历顺序（自顶向下）。
        """
        matched: list[str] = []
        try:
            for root, dirs, filenames in os.walk(folder, followlinks=False):
                for name in filenames:
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in allowed_ext:
                        continue
                    full_path = os.path.join(root, name)
                    matched.append(os.path.abspath(full_path))
        except OSError as exc:
            logger.warning("扫描文件夹 %r 失败: %s", folder, exc)
        return matched

    def add_file_list_dialog(self) -> None:
        """打开对话框选择一个文本列表文件，按行解析路径并添加。

        空行与首尾空白会被忽略。
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文件列表 (-fl)",
            "",
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            logger.error("读取文件列表失败 %r: %s", path, exc)
            return

        files = [line.strip() for line in lines if line.strip()]
        if files:
            self.add_files(files)

    def remove_selected(self) -> None:
        """移除当前选中的列表项。"""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        logger.debug("已移除 %d 个选中项", len(selected_items))
        # T-C2: 分组模式下重新分组以更新标题计数
        if self._group_by_type_enabled:
            self._apply_grouping()
        self._update_empty_state()
        self._update_count()
        self.files_changed.emit(self.get_files())

    def clear_all(self) -> None:
        """清空整个列表（有内容时弹确认对话框）。"""
        if self.list_widget.count() == 0:
            return
        reply = QMessageBox.question(
            self,
            "确认",
            "清空所有文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.list_widget.clear()
        logger.debug("已清空文件列表")
        self._update_empty_state()
        self._update_count()
        self.files_changed.emit(self.get_files())

    def get_files(self) -> list[str]:
        """返回当前所有文件路径列表。

        路径优先从 ``Qt.UserRole`` 读取；若为空则回退到项文本（向后兼容）。
        T-C2: 跳过分组标题项（``GROUP_HEADER_ROLE`` 标记）。
        """
        files: list[str] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(GROUP_HEADER_ROLE):
                continue
            path = item.data(Qt.UserRole)
            if not path:
                path = item.text()
            files.append(path)
        return files

    # ----------------------------------------------------------------------
    # 拖拽事件
    # ----------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """拖拽进入：仅接受 ``text/uri-list`` MIME 类型，并加视觉反馈。"""
        if event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
            self._set_drag_highlight(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        """拖拽离开：恢复默认样式。"""
        self._set_drag_highlight(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """拖拽放下：提取本地文件/文件夹 URL，按当前工具扩展名白名单过滤后添加。

        若拖拽对象为文件夹，递归扫描其中匹配扩展名的文件后添加；
        若拖拽对象为文件，按扩展名白名单过滤后直接添加。
        """
        mime = event.mimeData()
        if not mime.hasFormat("text/uri-list"):
            self._set_drag_highlight(False)
            event.ignore()
            return

        allowed_ext = self._get_allowed_extensions()
        files: list[str] = []
        rejected: list[str] = []
        folder_count = 0
        for url in mime.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if not local_path:
                    continue

                # 文件夹：递归扫描其中匹配扩展名的文件
                if os.path.isdir(local_path):
                    folder_files = self._collect_files_from_folder(
                        local_path, allowed_ext
                    )
                    if folder_files:
                        files.extend(folder_files)
                        folder_count += 1
                    else:
                        logger.info(
                            "文件夹 %s 中未找到当前工具 %s 支持的文件类型",
                            local_path,
                            self._current_tool.value,
                        )
                    continue

                # 文件：按扩展名白名单过滤
                ext = os.path.splitext(local_path)[1].lower()
                if ext not in allowed_ext:
                    rejected.append(local_path)
                    continue
                files.append(local_path)

        self._set_drag_highlight(False)
        if rejected:
            logger.warning(
                "当前工具 %s 不支持以下文件扩展名，已忽略: %s",
                self._current_tool.value,
                ", ".join(rejected),
            )
            self.count_label.setText(f"忽略 {len(rejected)} 个不支持的文件")
            QTimer.singleShot(3000, self._refresh_count_label)
        if files:
            if folder_count > 0:
                logger.debug(
                    "拖拽放入 %d 个文件夹，共扫描到 %d 个文件",
                    folder_count,
                    len(files),
                )
            self.add_files(files)
            event.acceptProposedAction()
        else:
            event.ignore()
