"""输出分组 Tab 模块。

提供输出方向与 WAV 格式相关参数的 GUI 编辑，并维护两个非 BalconConfig
字段（输出目录、文件名模板）供主窗口读取。

多格式输出支持：
- 「输出格式」下拉框：WAV/MP3/OGG/AAC/FLAC/WMA
- 非 WAV 格式时需要 ffmpeg，通过环境变量或 PATH 自动查找
- 「ffmpeg 路径」编辑框（可选）：用户可手动指定 ffmpeg.exe 路径
- 选择非 WAV 格式时自动调整文件名模板扩展名（如 ``{name}.wav`` → ``{name}.mp3``）
"""
from __future__ import annotations

import logging
import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chatterbox.core.audio_encoder import (
    AudioFormat,
    EncoderDetector,
    find_ffmpeg,
)
from chatterbox.core.config import BalconConfig
from chatterbox.gui.tabs.base_tab import AbstractTab
from chatterbox.gui.widgets.icon_provider import IconProvider

logger = logging.getLogger(__name__)


class OutputTab(AbstractTab):
    """输出参数分组 Tab。

    除 BalconConfig 字段外，还维护 ``output_dir_edit``、``template_edit``、
    ``format_combo``、``ffmpeg_edit`` 四个公开属性，供主窗口在批量生成
    输出路径时读取，并在程序启动时通过 ``set_output_dir`` /
    ``set_filename_template`` / ``set_output_format`` / ``set_ffmpeg_path`` 还原。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    @classmethod
    def tab_id(cls) -> str:
        return "output"

    @classmethod
    def tab_title(cls) -> str:
        return "输出"

    @classmethod
    def tab_group(cls) -> str:
        return "输入输出"

    @classmethod
    def tab_icon(cls) -> QIcon | None:
        return IconProvider.tab_icon("输入输出")

    @classmethod
    def tab_description(cls) -> str:
        return (
            "输出参数。"
            "输出目录（留空则与输入文件同目录）、"
            "文件名模板（{name}/{ext}/{i}）、"
            "输出格式（WAV/MP3/OGG/AAC/FLAC/WMA, 非 WAV 需 ffmpeg）、"
            "ffmpeg 路径（留空则自动查找）、"
            "输出到 STDOUT (-o)、"
            "原始 PCM 无 WAV 头 (--raw)、"
            "省略 WAV 头长度 (--ignore-length)、"
            "完成后删除输入文件 (--delete-file, 不可恢复)"
        )

    def collect_config(self, cfg: BalconConfig) -> None:
        cfg.o_stdout = self.stdout_check.isChecked()
        cfg.raw = self.raw_check.isChecked()
        cfg.ignore_length = self.ignore_length_check.isChecked()
        cfg.delete_file = self.delete_file_check.isChecked()

    def apply_config(self, cfg: BalconConfig) -> None:
        self.stdout_check.setChecked(cfg.o_stdout)
        self.raw_check.setChecked(cfg.raw)
        self.ignore_length_check.setChecked(cfg.ignore_length)
        self.delete_file_check.setChecked(cfg.delete_file)

    def refresh_voices(self, voices: list[str]) -> None:
        """OutputTab 不使用语音列表，空实现。"""

    def refresh_devices(self, devices: list[tuple[int, str]]) -> None:
        """OutputTab 不使用设备列表，空实现。"""

    def get_output_dir(self) -> str:
        """返回当前输出目录路径。"""
        return self.output_dir_edit.text().strip()

    def get_filename_template(self) -> str:
        """返回当前文件名模板（如 ``"{name}.wav"``）。"""
        return self.template_edit.text().strip()

    def get_output_format(self) -> AudioFormat:
        """返回当前选择的输出格式。"""
        return AudioFormat(self.format_combo.currentData())

    def get_ffmpeg_path(self) -> str:
        """返回用户指定的 ffmpeg 路径（空字符串表示自动查找）。"""
        return self.ffmpeg_edit.text().strip()

    def set_output_dir(self, path: str) -> None:
        """设置输出目录路径（供主窗口还原设置）。"""
        self.output_dir_edit.setText(path)

    def set_filename_template(self, t: str) -> None:
        """设置文件名模板（供主窗口还原设置）。"""
        self.template_edit.setText(t)

    def set_output_format(self, fmt: AudioFormat) -> None:
        """设置输出格式（供主窗口还原设置）。"""
        idx = self.format_combo.findData(fmt.value)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

    def set_ffmpeg_path(self, path: str) -> None:
        """设置 ffmpeg 路径（供主窗口还原设置）。"""
        self.ffmpeg_edit.setText(path)

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

    def _build_ui(self) -> None:
        layout = QFormLayout(self)

        # 输出目录（非 BalconConfig 字段）
        dir_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setMinimumWidth(80)
        self.output_dir_edit.setPlaceholderText("留空则与输入文件同目录")
        self.output_dir_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._on_browse_dir_clicked)
        dir_row.addWidget(self.output_dir_edit, 1)
        dir_row.addWidget(browse_btn)
        layout.addRow("输出目录：", dir_row)

        # 文件名模板（非 BalconConfig 字段）
        self.template_edit = QLineEdit("{name}.wav")
        self.template_edit.setMinimumWidth(80)
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
        layout.addRow("文件名模板：", self.template_edit)

        # 输出格式（非 BalconConfig 字段）
        self.format_combo = QComboBox()
        self.format_combo.setMinimumWidth(80)
        for fmt in AudioFormat:
            label = fmt.value.upper()
            if fmt.needs_ffmpeg:
                label += " (需 ffmpeg)"
            self.format_combo.addItem(label, fmt.value)
        self.format_combo.setCurrentIndex(0)  # 默认 WAV
        self.format_combo.currentIndexChanged.connect(
            self._on_format_changed
        )
        layout.addRow("输出格式：", self.format_combo)

        # ffmpeg 路径（非 BalconConfig 字段，仅非 WAV 格式时使用）
        ffmpeg_row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setMinimumWidth(80)
        self.ffmpeg_edit.setPlaceholderText(
            "留空则自动查找 ffmpeg（PATH 或环境变量）"
        )
        self.ffmpeg_edit.textChanged.connect(
            lambda: self._emit_changed()
        )
        ffmpeg_browse_btn = QPushButton("浏览…")
        ffmpeg_browse_btn.clicked.connect(self._on_browse_ffmpeg_clicked)
        ffmpeg_row.addWidget(self.ffmpeg_edit, 1)
        ffmpeg_row.addWidget(ffmpeg_browse_btn)
        layout.addRow("ffmpeg 路径：", ffmpeg_row)

        # ffmpeg 状态提示
        self.ffmpeg_status_label = QLabel()
        self.ffmpeg_status_label.setWordWrap(True)
        self.ffmpeg_status_label.setMinimumWidth(100)
        layout.addRow("", self.ffmpeg_status_label)

        # 编码器显示标签：展示当前格式将使用的高性能编码器
        self.encoder_label = QLabel()
        self.encoder_label.setWordWrap(True)
        self.encoder_label.setMinimumWidth(100)
        self.encoder_label.setToolTip(
            "编码器决定音频压缩算法。libfdk_aac > aac（内置）；"
            "libmp3lame 是 MP3 标准编码器"
        )
        layout.addRow("选用编码器：", self.encoder_label)

        # 音频质量模式：CBR 320k（默认）/ VBR 质量（-q:a）
        self.quality_container = QWidget()
        quality_row = QHBoxLayout(self.quality_container)
        quality_row.setContentsMargins(0, 0, 0, 0)
        self.quality_mode_combo = QComboBox()
        self.quality_mode_combo.addItem("CBR 320kbps (默认)")
        self.quality_mode_combo.addItem("VBR 质量 (-q:a)")
        self.quality_mode_combo.setToolTip(
            "CBR 模式：固定 320kbps 比特率（MP3/AAC/WMA 最高等效质量）。\n"
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
        layout.addRow("音频质量：", self.quality_container)

        self._update_ffmpeg_status()

        # BalconConfig 字段 —— 输出选项分组
        output_group = QGroupBox("输出选项")
        output_group_layout = QVBoxLayout(output_group)

        self.stdout_check = QCheckBox("输出到 STDOUT (-o)")
        self.stdout_check.setToolTip(
            "输出到 STDOUT 而非文件。用于管道传输给其他程序"
        )
        self.stdout_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        output_group_layout.addWidget(self.stdout_check)

        self.raw_check = QCheckBox("原始 PCM 无 WAV 头 (--raw)")
        self.raw_check.setToolTip(
            "输出原始 PCM 数据（无 WAV 头）。适用于需要后续处理的场景"
        )
        self.raw_check.stateChanged.connect(lambda: self._emit_changed())
        output_group_layout.addWidget(self.raw_check)

        self.ignore_length_check = QCheckBox(
            "省略 WAV 头长度 (--ignore-length)"
        )
        self.ignore_length_check.setToolTip(
            "省略 WAV 头长度字段。某些播放器需要此选项"
        )
        self.ignore_length_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        output_group_layout.addWidget(self.ignore_length_check)

        self.delete_file_check = QCheckBox(
            "完成后删除输入文件 (--delete-file)"
        )
        self.delete_file_check.setToolTip(
            "⚠ 勾选后 balcon 转换成功即删除原文件，不可恢复。"
            "开始批次时会二次确认"
        )
        self.delete_file_check.stateChanged.connect(
            lambda: self._emit_changed()
        )
        output_group_layout.addWidget(self.delete_file_check)

        layout.addRow(output_group)

        self.setLayout(layout)

    def _on_browse_dir_clicked(self) -> None:
        """输出目录浏览按钮：弹出目录选择对话框。"""
        current = self.output_dir_edit.text().strip()
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", current or ""
        )
        if path:
            self.output_dir_edit.setText(path)

    def _on_browse_ffmpeg_clicked(self) -> None:
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
            self._update_ffmpeg_status()

    def _on_format_changed(self) -> None:
        """输出格式变化时：调整模板扩展名 + 更新 ffmpeg 状态。"""
        fmt = self.get_output_format()
        self._adjust_template_extension(fmt)
        self._update_ffmpeg_status()
        self._emit_changed()

    def _on_quality_mode_changed(self) -> None:
        """质量模式切换：启用/禁用 VBR 质量输入框。"""
        is_vbr = self.quality_mode_combo.currentIndex() == 1
        self.quality_spin.setEnabled(is_vbr)
        self._emit_changed()

    def _adjust_template_extension(self, fmt: AudioFormat) -> None:
        """根据输出格式调整文件名模板的扩展名。

        若当前模板以已知音频扩展名结尾（如 ``.wav``、``.mp3``），
        替换为新格式的扩展名；否则不修改（用户可能使用了 ``{ext}`` 占位符）。

        Args:
            fmt: 新的输出格式。
        """
        template = self.template_edit.text().strip()
        if not template:
            return

        # 检查模板是否以已知音频扩展名结尾
        lower_template = template.lower()
        replaced = False
        for known_fmt in AudioFormat:
            ext = f".{known_fmt.extension}"
            if lower_template.endswith(ext):
                # 保留原大小写敏感性：直接替换末尾扩展名
                # 找到原扩展名的起始位置
                ext_start = len(template) - len(ext)
                template = template[:ext_start] + f".{fmt.extension}"
                replaced = True
                break

        if replaced:
            # 阻止信号以避免循环触发 _emit_changed
            self.template_edit.blockSignals(True)
            self.template_edit.setText(template)
            self.template_edit.blockSignals(False)

    def _update_ffmpeg_status(self) -> None:
        """更新 ffmpeg 状态提示标签与选用编码器标签。

        - WAV 格式：隐藏 ffmpeg 状态与编码器标签
        - 非 WAV 格式：显示 ffmpeg 查找结果（已找到路径 / 未找到），
          并展示当前格式按优先级选用的最佳编码器名称
        """
        fmt = self.get_output_format()
        if fmt.is_wav:
            self.ffmpeg_status_label.setText("")
            self.ffmpeg_status_label.setVisible(False)
            self.encoder_label.setText("")
            self.encoder_label.setVisible(False)
            self.quality_container.setVisible(False)
            return

        self.ffmpeg_status_label.setVisible(True)
        self.encoder_label.setVisible(True)
        self.quality_container.setVisible(True)
        user_path = self.get_ffmpeg_path()
        resolved_path: str | None = None
        if user_path:
            if os.path.isfile(user_path):
                self.ffmpeg_status_label.setText(
                    f"✓ 已指定 ffmpeg: {user_path}"
                )
                resolved_path = os.path.abspath(user_path)
            else:
                self.ffmpeg_status_label.setText(
                    f"✗ 指定的 ffmpeg 路径无效: {user_path}"
                )
        else:
            found = find_ffmpeg()
            if found:
                self.ffmpeg_status_label.setText(
                    f"✓ 已在系统中找到 ffmpeg: {found}"
                )
                resolved_path = found
            else:
                self.ffmpeg_status_label.setText(
                    "✗ 未找到 ffmpeg。请安装 ffmpeg 并添加到 PATH，"
                    "或在上方指定 ffmpeg.exe 路径。"
                )

        # 编码器选择：检测 ffmpeg 可用编码器，按优先级选择高性能编码器
        if resolved_path is None:
            self.encoder_label.setText(
                f"默认编码器: {fmt.encoder}（未找到 ffmpeg，无法检测）"
            )
            return
        try:
            available = EncoderDetector.detect(resolved_path)
            selected = fmt.best_encoder(available)
            if selected == fmt.encoder:
                self.encoder_label.setText(
                    f"{selected}（默认编码器）"
                )
            else:
                self.encoder_label.setText(
                    f"{selected}（已选用高性能编码器）"
                )
        except Exception:  # noqa: BLE001
            self.encoder_label.setText(
                f"默认编码器: {fmt.encoder}（检测失败）"
            )


__all__ = ["OutputTab"]
