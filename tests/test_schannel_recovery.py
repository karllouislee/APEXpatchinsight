import io
import json

import pytest

from src.core.settings import Settings
from src.core.models import PatchChange
from src.integrations.siliconflow_client import (
    SiliconFlowClient,
    SiliconFlowError,
    _can_recover_schannel_close,
    _strict_json_document,
)


SCHANNEL_CLOSE = "curl: (56) schannel: server closed abruptly (missing close_notify)"


def _recovery_candidate(content: str, **overrides) -> bool:
    values = {
        "returncode": 56,
        "stderr": SCHANNEL_CLOSE,
        "content": content,
        "http_status": 200,
        "saw_sse": True,
        "saw_done": False,
        "finish_reason": None,
        "malformed_sse_chunks": 0,
    }
    values.update(overrides)
    return _can_recover_schannel_close(**values)


def test_close_notify_recovery_requires_strict_complete_json():
    assert _recovery_candidate('{"changes": []}') is True
    assert _recovery_candidate('{"changes": [') is False
    assert _recovery_candidate('{"changes": []} trailing') is False
    assert _recovery_candidate('{"changes": []}', http_status=0) is False
    assert _recovery_candidate('{"changes": []}', malformed_sse_chunks=1) is False
    assert _recovery_candidate('{"changes": []}', finish_reason="length") is False
    assert _recovery_candidate(
        '{"changes": []}', stderr="curl: (56) connection reset by peer"
    ) is False


def test_strict_document_accepts_complete_fence_and_rejects_trailing_data():
    fence = chr(96) * 3
    assert _strict_json_document(f'{fence}json\n{{"changes": []}}\n{fence}') == {"changes": []}
    with pytest.raises(SiliconFlowError):
        _strict_json_document('{"changes": []} trailing-partial')


class _FakeProcess:
    def __init__(self, stdout_text: str, stderr_text: str, returncode: int):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self._returncode = returncode

    def wait(self, timeout=None):
        return self._returncode


def _sse_response(content: str, *, finish_reason="stop", done=True, status=200) -> str:
    chunk = {
        "choices": [{"delta": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"total_tokens": 12},
    }
    lines = [f"data: {json.dumps(chunk)}"]
    if done:
        lines.append("data: [DONE]")
    lines.append(f"__STATUS__:{status}")
    return "\n".join(lines) + "\n"


def _client(event_sink=None) -> SiliconFlowClient:
    return SiliconFlowClient(
        Settings(
            api_key="test-key",
            base_url="https://api.siliconflow.com/v1",
            text_model="test-model",
            reasoning_effort="high",
        ),
        event_sink=event_sink,
    )


def test_text_json_recovers_complete_close_notify_response_without_retry(monkeypatch):
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(_sse_response('{"changes": []}'), SCHANNEL_CLOSE, 56)

    monkeypatch.setattr("src.integrations.siliconflow_client.shutil.which", lambda _: "curl.exe")
    monkeypatch.setattr("src.integrations.siliconflow_client.subprocess.Popen", fake_popen)

    result = _client().text_json("prompt", {"article": "x"}, list[PatchChange])

    assert result == []
    assert len(calls) == 1


def test_incomplete_close_notify_response_fails_once(monkeypatch):
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(_sse_response('{"changes": [', finish_reason=None, done=False), SCHANNEL_CLOSE, 56)

    monkeypatch.setattr("src.integrations.siliconflow_client.shutil.which", lambda _: "curl.exe")
    monkeypatch.setattr("src.integrations.siliconflow_client.subprocess.Popen", fake_popen)

    with pytest.raises(SiliconFlowError, match="不会自动重试"):
        _client().text_json("prompt", {"article": "x"}, list[PatchChange])

    assert len(calls) == 1


def test_recovered_transport_still_requires_schema_and_logs_final_failure(monkeypatch):
    calls = []
    events = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        invalid = '{"changes": [{"target": {"name": "R-99"}, "summary": "x"}]}'
        return _FakeProcess(_sse_response(invalid), SCHANNEL_CLOSE, 56)

    monkeypatch.setattr("src.integrations.siliconflow_client.shutil.which", lambda _: "curl.exe")
    monkeypatch.setattr("src.integrations.siliconflow_client.subprocess.Popen", fake_popen)

    with pytest.raises(SiliconFlowError, match="数据结构"):
        _client(events.append).text_json("prompt", {"article": "x"}, list[PatchChange])

    assert len(calls) == 1
    final = [event for event in events if event.get("status") in {"success", "failed"}][-1]
    assert final["status"] == "failed"


def test_zero_response_transport_error_is_not_automatically_retried(monkeypatch):
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess("__STATUS__:0\n", "curl: (28) operation timed out", 28)

    monkeypatch.setattr("src.integrations.siliconflow_client.shutil.which", lambda _: "curl.exe")
    monkeypatch.setattr("src.integrations.siliconflow_client.subprocess.Popen", fake_popen)

    with pytest.raises(SiliconFlowError, match="不会自动重试"):
        _client().text_json("prompt", {"article": "x"}, list[PatchChange])

    assert len(calls) == 1