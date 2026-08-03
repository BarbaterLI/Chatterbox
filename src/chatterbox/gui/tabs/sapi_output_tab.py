"""SAPI5 输出设置选项卡模块。"""
from __future__ import annotations

import logging
import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.audio_encoder import AudioFormat
from chatterbox.core.sapi_config import SapiConfig
from chatterbox.core.tool_type import ToolType
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class SapiOutputTab(AbstractTab):
    """SAPI5 输出设置分组 Tab。

    维护输出目录、文件名模板、输出格式、ffmpeg 路径 4 个非 SapiConfig
    字段（通过 property 供主窗口读取），以及输入编码（SapiConfig 字段）。

    同 balcon :class:`OutputTab` 模式：输出目录 / 模板 / 格式 / ffmpeg 路径
    不在配置对象中，由主窗口通过 property 直接读取管理。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "sapi_output"

    @classmethod
    def tab_title(cls) -> str:
        return "输出设置"

    @classmethod
    def tab_group(cls) -> str:
        return "输入输出"

    @classmethod
    def tab_tool(cls) -> ToolType:
        return ToolType.SAPI

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("输入输出")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "SAPI5 输出设置。"
            "输出目录（留空则与输入文件同目录）、"
            "文件名模板（{name}/{ext}/{i}）、"
            "输出格式（WAV/MP3/OGG/FLAC, 非 WAV 需 ffmpeg）、"
            "ffmpeg 路径（留空则自动查找）、"
            "输入文本编码（默认 utf-8）"
        )

    @property
    def output_dir(self) -> str:
        """返回当前输出目录路径。"""
        return self.output_dir_edit.text()

    @property
    def filename_template(self) -> str:
        """返回当前文件名模板。"""
        return self.template_edit.text()

    @property
    def output_format(self) -> AudioFormat:
        """返回当前选择的输出格式。

        PySide6 QComboBox 将 str 子类（如 ``AudioFormat``）通过 QVariant
        存储时会退化为纯 ``str``，需通过 :meth:`AudioFormat.from_extension`
        还原为枚举实例，确保 ``is_wav`` / ``needs_ffmpeg`` 等属性可用。
        """
        data = self.format_combo.currentData()
        if isinstance(data, AudioFormat):
            return data
        return AudioFormat.from_extension(str(data) if data else "wav")

    @property
    def ffmpeg_path(self) -> str:
        """返回用户指定的 ffmpeg 路径。"""
        return self.ffmpeg_edit.text()

    def get_vbr_quality(self) -> int:
        """返回 VBR 质量值：-1 表示 CBR 默认（320kbps），0~10 为 VBR 质量等级。"""
        if self.quality_mode_combo.currentIndex() == 0:
            return -1  # CBR 模式
        return self.quality_spin.value()

    def set_vbr_quality(self, quality: int) -> None:
        """设置 VBR 质量值（供主窗口还原设置）。

        Args:
            quality: -1 表示 CBR 模式，0~10 为 VBR 质量等级。
        """
        if quality < 0:
            self.quality_mode_combo.setCurrentIndex(0)
        else:
            self.quality_mode_combo.setCurrentIndex(1)
            self.quality_spin.setValue(quality)

    def collect_config(self, cfg: SapiConfig) -> None:
        """从控件读取值，写入 :class:`SapiConfig`。

        输出目录、模板、格式、ffmpeg 路径不在 SapiConfig 中
        （同 balcon OutputTab 模式，由 MainWindow 通过 property 读取）。
        """
        cfg.input_encoding = self.encoding_edit.text().strip() or "utf-8"

    def apply_config(self, cfg: SapiConfig) -> None:
        """从 :class:`SapiConfig` 读取值，还原控件状态。"""
        self.encoding_edit.setText(cfg.input_encoding)

    def refresh_voices(self, voices: list[str]) -> None:
        """SapiOutputTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """SapiOutputTab 不使用设备列表，空实现。"""

    def _build_ui(self) -> None:
        """构建 SAPI5 输出设置界面。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        # 输出目录
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setMinimumWidth(80)
        self.output_dir_edit.setPlaceholderText("留空则与输入文件同目录")
        self.output_dir_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        dir_browse_btn = QPushButton("浏览…")
        dir_browse_btn.clicked.connect(self._on_browse_dir)
        dir_row.addWidget(self.output_dir_edit, 1)
        dir_row.addWidget(dir_browse_btn)
        form.addRow("输出目录：", dir_row)

        # 文件名模板
        self.template_edit = QLineEdit("{name}.wav")
        self.template_edit.setMinimumWidth(80)
        self.template_edit.setPlaceholderText("{name}.wav")
        self.template_edit.setToolTip(
            "输出文件名模板。可用占位符：\n"
            "  {name} - 输入文件名（不含扩展名）或序号\n"
            "  {ext}  - 输出扩展名（如 wav）\n"
            "  {i}    - 文件序号（从 1 开始）\n"
            "示例：{name}.wav / {i:03d}.wav / {name}_out.{ext}\n"
            "注意：扩展名会根据「输出格式」自动调整。"
        )
        self.template_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        form.addRow("文件名模板：", self.template_edit)

        # 输出格式
        self.format_combo = QComboBox()
        self.format_combo.setMinimumWidth(80)
        self.format_combo.addItem("WAV (无损)", AudioFormat.WAV)
        self.format_combo.addItem("MP3", AudioFormat.MP3)
        self.format_combo.addItem("OGG", AudioFormat.OGG)
        self.format_combo.addItem("FLAC", AudioFormat.FLAC)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("输出格式：", self.format_combo)

        # ffmpeg 路径（非 WAV 格式时需要）
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.setContentsMargins(0, 0, 0, 0)
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setMinimumWidth(80)
        self.ffmpeg_edit.setPlaceholderText(
            "留空则自动查找 ffmpeg（非 WAV 格式时需要）"
        )
        self.ffmpeg_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        ffmpeg_browse_btn = QPushButton("浏览…")
        ffmpeg_browse_btn.clicked.connect(self._on_browse_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_edit, 1)
        ffmpeg_row.addWidget(ffmpeg_browse_btn)
        form.addRow("ffmpeg 路径：", ffmpeg_row)

        # 音频质量模式：CBR 320k（默认）/ VBR 质量（-q:a）
        # 仅非 WAV 格式时可用（与 OutputTab 一致）
        self.quality_container = QWidget()
        quality_row = QHBoxLayout(self.quality_container)
        quality_row.setContentsMargins(0, 0, 0, 0)
        self.quality_mode_combo = QComboBox()
        self.quality_mode_combo.addItem("CBR 320kbps (默认)")
        self.quality_mode_combo.addItem("VBR 质量 (-q:a)")
        self.quality_mode_combo.setToolTip(
            "CBR 模式：固定 320kbps 比特率（MP3 最高等效质量）。\n"
            "VBR 模式：使用 ffmpeg -q:a 参数指定可变比特率质量等级。\n\n"
            "注意：\n"
            "- MP3 (libmp3lame): 0=最高(~245kbps) ~ 9=最低(~65kbps)\n"
            "- Vorbis: 0=最低 ~ 10=最高(~500kbps)\n"
            "- VBR 质量可能低于 320kbps CBR，但文件更小、音质效率更高"
        )
        self.quality_mode_combo.currentIndexChanged.connect(
            self._on_quality_mode_changed
        )
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 10)
        self.quality_spin.setValue(2)
        self.quality_spin.setEnabled(False)  # CBR 模式下禁用
        self.quality_spin.setToolTip(
            "VBR 质量等级（0~10）。\n"
            "不同编码器含义不同，请参阅质量模式说明。"
        )
        quality_row.addWidget(self.quality_mode_combo, 1)
        quality_row.addWidget(self.quality_spin)
        form.addRow("音频质量：", self.quality_container)

        # 编码（输入文本文件编码）
        self.encoding_edit = QLineEdit("utf-8")
        self.encoding_edit.setMinimumWidth(80)
        self.encoding_edit.setPlaceholderText("输入文本文件编码，如 utf-8")
        self.encoding_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        form.addRow("编码：", self.encoding_edit)

        outer.addLayout(form)
        outer.addStretch(1)

        self.setLayout(outer)

        # 初始化质量控件可见性（默认 WAV 格式 → 隐藏）
        self._update_quality_visibility()

    def _on_format_changed(self) -> None:
        """输出格式变化时：更新质量控件可见性并发射 changed 信号。"""
        self._update_quality_visibility()
        self._emit_changed()

    def _on_quality_mode_changed(self) -> None:
        """质量模式切换：启用/禁用 VBR 质量输入框。"""
        is_vbr = self.quality_mode_combo.currentIndex() == 1
        self.quality_spin.setEnabled(is_vbr)
        self._emit_changed()

    def _update_quality_visibility(self) -> None:
        """根据当前输出格式调整质量控件的可见性。

        WAV 格式无需转码，隐藏质量控件；
        非 WAV 格式（MP3/OGG/FLAC）显示质量控件（与 OutputTab 一致）。
        """
        fmt = self.output_format
        self.quality_container.setVisible(not fmt.is_wav)

    def _on_browse_dir(self) -> None:
        """输出目录浏览按钮：弹出目录选择对话框。"""
        current = self.output_dir_edit.text().strip()
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", current or ""
        )
        if path:
            self.output_dir_edit.setText(path)

    def _on_browse_ffmpeg(self) -> None:
        """ffmpeg 路径浏览按钮：弹出文件选择对话框。"""
        current = self.ffmpeg_edit.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ffmpeg 可执行文件",
            current or "",
            "可执行文件 (*.exe);;所有文件 (*.*)"
            if os.name == "nt"
            else "所有文件 (*)",
        )
        if path:
            self.ffmpeg_edit.setText(path)


__all__ = ["SapiOutputTab"]
