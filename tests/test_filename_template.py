"""filename_template 模块单元测试。

验证模板渲染、上下文构建与输出路径生成行为。
"""
from __future__ import annotations

import datetime
import os.path

import pytest

from balcon_batch_tts.core.filename_template import (
    build_context,
    render_output_path,
    render_template,
)


# ---------------------------------------------------------------------------
# render_template 基本占位符
# ---------------------------------------------------------------------------
class TestRenderTemplate:
    """render_template 应正确替换已知占位符。"""

    def test_basic_name_placeholder(self) -> None:
        result = render_template("{name}.wav", {"name": "book"})
        assert result == "book.wav"

    def test_multiple_placeholders_with_index_padding(self) -> None:
        result = render_template(
            "{name}_{voice}_{index}",
            {"name": "book", "voice": "Emma", "index": "1"},
        )
        assert result == "book_Emma_001"

    def test_name_ext_placeholders(self) -> None:
        result = render_template(
            "{name}.{ext}",
            {"name": "book", "ext": "txt"},
        )
        assert result == "book.txt"

    def test_date_placeholder(self) -> None:
        result = render_template("{date}", {"date": "20260727"})
        assert result == "20260727"

    def test_int_index_gets_zero_padded(self) -> None:
        result = render_template("{index}", {"index": 5})
        assert result == "005"

    def test_string_numeric_index_gets_zero_padded(self) -> None:
        result = render_template("{index}", {"index": "7"})
        assert result == "007"

    def test_large_index_not_truncated(self) -> None:
        result = render_template("{index}", {"index": "1234"})
        assert result == "1234"

    def test_non_numeric_index_preserved_as_is(self) -> None:
        result = render_template("{index}", {"index": "abc"})
        assert result == "abc"

    def test_template_without_placeholders(self) -> None:
        result = render_template("plain.wav", {})
        assert result == "plain.wav"

    def test_does_not_mutate_input_context(self) -> None:
        ctx = {"name": "book", "index": "1"}
        original = dict(ctx)
        render_template("{name}_{index}", ctx)
        assert ctx == original


# ---------------------------------------------------------------------------
# 未知占位符
# ---------------------------------------------------------------------------
class TestUnknownPlaceholder:
    """未知占位符应保留原样，不抛异常。"""

    def test_unknown_placeholder_preserved(self) -> None:
        result = render_template("{foo}", {})
        assert result == "{foo}"

    def test_mixed_known_and_unknown_placeholders(self) -> None:
        result = render_template("{name}_{foo}", {"name": "book"})
        assert result == "book_{foo}"

    def test_multiple_unknown_placeholders(self) -> None:
        result = render_template("{foo}_{bar}", {})
        assert result == "{foo}_{bar}"


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------
class TestBuildContext:
    """build_context 应从输入路径与语音名构建完整 context。"""

    def test_build_context_basic(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 1)
        assert isinstance(ctx, dict)
        assert ctx["name"] == "book"
        assert ctx["ext"] == "txt"
        assert ctx["voice"] == "Emma"
        assert ctx["index"] == "1"

    def test_build_context_includes_date(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 1)
        assert "date" in ctx
        assert isinstance(ctx["date"], str)

    def test_build_context_date_is_today(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 1)
        today = datetime.date.today().strftime("%Y%m%d")
        assert ctx["date"] == today

    def test_build_context_custom_date(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 1, date="20250101")
        assert ctx["date"] == "20250101"

    def test_build_context_voice_none_becomes_empty(self) -> None:
        ctx = build_context("d:/text/book.txt", None, 1)
        assert ctx["voice"] == ""

    def test_build_context_no_extension(self) -> None:
        ctx = build_context("d:/text/book", "Emma", 1)
        assert ctx["name"] == "book"
        assert ctx["ext"] == ""

    def test_build_context_index_is_string(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 42)
        assert ctx["index"] == "42"

    def test_build_context_returns_five_keys(self) -> None:
        ctx = build_context("d:/text/book.txt", "Emma", 1)
        assert set(ctx.keys()) == {"name", "ext", "voice", "index", "date"}


# ---------------------------------------------------------------------------
# render_output_path
# ---------------------------------------------------------------------------
class TestRenderOutputPath:
    """render_output_path 应组合 context 与 render_template，自动追加 .wav。"""

    def test_with_output_dir_appends_wav(self) -> None:
        result = render_output_path(
            "{name}_{voice}_{index}",
            "d:/text/book.txt",
            "Emma",
            1,
            "d:/out",
        )
        assert os.path.basename(result) == "book_Emma_001.wav"
        assert os.path.dirname(result) != ""

    def test_without_output_dir_returns_filename_only(self) -> None:
        result = render_output_path(
            "{name}_{voice}_{index}",
            "d:/text/book.txt",
            "Emma",
            1,
        )
        assert result == "book_Emma_001.wav"

    def test_no_double_wav_when_template_has_extension(self) -> None:
        result = render_output_path(
            "{name}.wav",
            "d:/text/book.txt",
            "Emma",
            1,
            "d:/out",
        )
        assert os.path.basename(result) == "book.wav"
        assert ".wav.wav" not in result

    def test_without_dir_no_double_wav(self) -> None:
        result = render_output_path(
            "{name}.wav",
            "d:/text/book.txt",
            "Emma",
            1,
        )
        assert result == "book.wav"

    def test_custom_extension_not_overridden_by_wav(self) -> None:
        result = render_output_path(
            "{name}.{ext}",
            "d:/text/book.txt",
            "Emma",
            1,
        )
        assert result == "book.txt"

    def test_with_custom_date(self) -> None:
        result = render_output_path(
            "{name}_{date}",
            "d:/text/book.txt",
            "Emma",
            1,
            "d:/out",
            date="20250101",
        )
        assert os.path.basename(result) == "book_20250101.wav"
