from pathlib import Path

import src.core.settings as config
from src.core.models import PatchChange
from src.core.settings import (
    DEFAULT_REASONING_EFFORT,
    OFFICIAL_BASE_URL,
    Settings,
    normalize_reasoning_effort,
)
from src.integrations.siliconflow_client import SiliconFlowClient, SiliconFlowError


def test_save_api_settings_writes_local_env_without_logging_key(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    config.save_api_settings("secret-test-key", "https://api.example/v1", "text/model", "high")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SILICONFLOW_API_KEY='secret-test-key'" in content
    assert "SILICONFLOW_TEXT_MODEL='text/model'" in content
    assert "SILICONFLOW_REASONING_EFFORT='high'" in content
    assert "VISION" not in content


def test_save_api_settings_clamps_unknown_reasoning_effort(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    # Upstream silently resolves unknown levels to the priciest tier, so the
    # writer folds them back to the balanced default instead.
    config.save_api_settings("secret-test-key", OFFICIAL_BASE_URL, "text/model", "ultra")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert f"SILICONFLOW_REASONING_EFFORT='{DEFAULT_REASONING_EFFORT}'" in content


def test_normalize_reasoning_effort_accepts_known_levels_only():
    assert normalize_reasoning_effort("HIGH") == "high"
    assert normalize_reasoning_effort(" max ") == "max"
    assert normalize_reasoning_effort("nonsense") == DEFAULT_REASONING_EFFORT
    assert normalize_reasoning_effort("") == DEFAULT_REASONING_EFFORT


def test_text_json_sends_reasoning_effort_instead_of_thinking_toggle():
    captured: dict[str, object] = {}

    def fake_transport(operation, model, payload, on_delta):
        captured.update(payload)
        return {
            "content": '{"changes": []}', "reasoning": "", "usage": {}, "finish_reason": "stop",
            "chunks": 1, "http_status": 200, "transport_recovered": False, "curl_exit_code": 0,
            "saw_done": True, "malformed_sse_chunks": 0, "_request_id": "rid", "_started": 0.0,
            "_attempt_label": operation, "_model": model,
        }

    client = SiliconFlowClient(Settings(api_key="k", text_model="text/model", reasoning_effort="high"))
    client._stream_with_retry = fake_transport  # type: ignore[assignment]
    assert client.text_json("prompt", {"article": "x"}, list[PatchChange]) == []
    assert captured["reasoning_effort"] == "high"
    assert captured["model"] == "text/model"
    assert captured["temperature"] == 0
    assert "enable_thinking" not in captured


def test_model_list_requires_credentials():
    try:
        SiliconFlowClient.list_available_models("", "https://api.siliconflow.cn/v1")
    except SiliconFlowError as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("Missing API key must be rejected")
