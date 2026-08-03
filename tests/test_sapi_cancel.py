"""SAPI5 可取消合成单元测试（Task 15）。

验证 :func:`sapi_runner._speak_with_cancel` 的三种路径（同步模式、异步正常完成、
异步取消）以及 :class:`SapiTask` 向 ``synthesize_to_file`` 传递 ``cancel_event``
参数的行为。

使用 ``unittest.mock`` 模拟 SpVoice COM 对象与 ``time.sleep``（避免测试真实休眠）。
测试环境可能没有 pywin32 或 SAPI5 引擎，故在导入 ``sapi_runner`` 前通过
``sys.modules`` 注入 mock，确保 ``_SAPI_AVAILABLE = True``。

属性访问模拟说明：``voice.Status`` 在 SAPI5 中是属性访问（非方法调用），
MagicMock 默认对属性访问返回同一子 mock，无法模拟「每次返回不同值」。
故采用 ``type(voice).Status = PropertyMock(...)`` 模式，使每次访问消费
``side_effect`` 序列中的下一个值。该写法会修改 ``MagicMock`` 类本身，
由 ``_cleanup_status_propertymock`` 夹具在每条测试后清理。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

# 在导入 PySide6 之前设置 offscreen 平台（SapiTask 测试需要 QApplication）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 在导入 sapi_runner 前 mock pywin32（仅当不可用时）。
if "win32com" not in sys.modules:
    sys.modules["win32com"] = MagicMock()
    sys.modules["win32com.client"] = MagicMock()
if "pythoncom" not in sys.modules:
    sys.modules["pythoncom"] = MagicMock()

import pytest
from PySide6.QtWidgets import QApplication

from balcon_batch_tts.core import sapi_runner
from balcon_batch_tts.core.sapi_runner import SapiError, _speak_with_cancel
from balcon_batch_tts.core.audio_encoder import AudioFormat
from balcon_batch_tts.core.sapi_config import SapiConfig
from balcon_batch_tts.core.sapi_worker import SapiTask


# ---------------------------------------------------------------------------
# 公共夹具
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_time_sleep():
    """禁用 ``time.sleep`` 使轮询测试即时完成（无真实休眠）。"""
    with patch.object(time, "sleep"):
        yield


@pytest.fixture(autouse=True)
def _cleanup_status_propertymock():
    """清理 ``type(voice).Status`` PropertyMock，避免污染全局 ``MagicMock`` 类。

    测试 2/3 通过 ``type(voice).Status = PropertyMock(...)`` 模拟 ``voice.Status``
    属性访问，这会修改 ``MagicMock`` 类本身。每个测试后删除该类属性以隔离。
    """
    yield
    if "Status" in MagicMock.__dict__:
        try:
            delattr(MagicMock, "Status")
        except (AttributeError, TypeError):
            pass


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """会话级 ``QApplication`` 单例（``SapiTask`` 信号系统需要）。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Test 1: 同步模式（cancel_event=None）
# ---------------------------------------------------------------------------
def test_speak_with_cancel_no_event_uses_sync_mode():
    """无 ``cancel_event`` 时使用同步模式 ``Speak(text, 0)``，不访问 ``Status``。"""
    voice = MagicMock()

    _speak_with_cancel(voice, "hello", None)

    # 同步模式：Speak 以 flags=0 调用一次
    voice.Speak.assert_called_once_with("hello", 0)
    # 同步模式不进入轮询循环，不访问 voice.Status（MagicMock 属性访问会创建
    # 子 mock 但无副作用，此处不强制断言）


# ---------------------------------------------------------------------------
# Test 2: 异步正常完成
# ---------------------------------------------------------------------------
def test_speak_with_cancel_completes_normally():
    """有 ``cancel_event`` 但未触发时，轮询到 ``RunningState=0`` 正常返回。"""
    voice = MagicMock()
    # 第一次轮询返回 RunningState=1（运行中），第二次返回 0（完成）
    status_values = [MagicMock(RunningState=1), MagicMock(RunningState=0)]
    type(voice).Status = PropertyMock(side_effect=status_values)
    event = threading.Event()

    _speak_with_cancel(voice, "text", event)

    # 异步模式：Speak 以 flags=1（SPF_ASYNC）调用
    voice.Speak.assert_called_once_with("text", 1)
    # 未取消，Skip 不应被调用
    voice.Skip.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: 异步取消
# ---------------------------------------------------------------------------
def test_speak_with_cancel_triggered():
    """``cancel_event`` 已设置时调用 ``voice.Skip`` 并抛出 ``SapiError``。"""
    voice = MagicMock()
    # Status 总是返回运行中（永不完成），确保进入取消分支
    type(voice).Status = PropertyMock(return_value=MagicMock(RunningState=1))
    event = threading.Event()
    event.set()  # 预先设置取消

    with pytest.raises(SapiError, match="取消"):
        _speak_with_cancel(voice, "text", event)

    # 异步模式启动
    voice.Speak.assert_called_once_with("text", 1)
    # 应调用 Skip 跳过剩余句子
    voice.Skip.assert_called_once_with("Sentence", 0, 0)


# ---------------------------------------------------------------------------
# Test 4: SapiTask 传递 cancel_event
# ---------------------------------------------------------------------------
def test_sapi_task_passes_cancel_event_to_synthesize(qapp, tmp_path):
    """``SapiTask._exec_wav`` 将 ``self._cancel_event`` 传给 ``synthesize_to_file``。"""
    input_file = tmp_path / "input.txt"
    input_file.write_text("hello", encoding="utf-8")
    output_path = str(tmp_path / "out.wav")

    config = SapiConfig.create_default()
    task = SapiTask(
        input_file=str(input_file),
        config=config,
        output_path=output_path,
        output_format=AudioFormat.WAV,
    )

    with patch("balcon_batch_tts.core.sapi_worker.init_com"), \
         patch(
             "balcon_batch_tts.core.sapi_worker.synthesize_to_file"
         ) as mock_synth:
        task.run()

    mock_synth.assert_called_once()
    # cancel_event 通过关键字参数传递，应为任务自身的 _cancel_event 实例
    call_kwargs = mock_synth.call_args.kwargs
    assert call_kwargs["cancel_event"] is task._cancel_event
