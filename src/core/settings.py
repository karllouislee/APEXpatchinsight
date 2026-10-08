from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv, set_key

from .paths import DEMO_DIR, ENV_FILE, WORKSPACE_DIR

OFFICIAL_BASE_URL = "https://api.siliconflow.com/v1"

# GLM-5.3-Flash is a natively multimodal model whose reasoning is always on:
# it cannot be disabled, only tuned through ``reasoning_effort``.
RECOMMENDED_TEXT_MODEL = "zai-org/GLM-5.3-Flash"
REASONING_EFFORTS = ("low", "high", "max")
DEFAULT_REASONING_EFFORT = "high"

load_dotenv(ENV_FILE)


def normalize_reasoning_effort(value: str) -> str:
    """Clamp a reasoning-effort label to the levels GLM-5.x actually accepts.

    The chat template silently resolves anything unrecognised to ``max``, which
    is also the most expensive option — so unknown input falls back to the
    balanced default instead of quietly burning the token budget.
    """
    candidate = (value or "").strip().lower()
    return candidate if candidate in REASONING_EFFORTS else DEFAULT_REASONING_EFFORT


def normalize_base_url(value: str) -> str:
    """Return an OpenAI-compatible API root even if an endpoint was pasted."""
    candidate = (value or "").strip().split()[0] if (value or "").strip() else OFFICIAL_BASE_URL
    candidate = candidate.rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/models"):
        if candidate.lower().endswith(suffix):
            candidate = candidate[: -len(suffix)].rstrip("/")
            break
    if candidate == "https://api.siliconflow.cn/v1":
        return OFFICIAL_BASE_URL
    return candidate or OFFICIAL_BASE_URL


def _setting(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    if name == "SILICONFLOW_BASE_URL":
        return normalize_base_url(value)
    return value or default


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default_factory=lambda: os.getenv("SILICONFLOW_API_KEY", "").strip())
    base_url: str = field(default_factory=lambda: _setting("SILICONFLOW_BASE_URL", OFFICIAL_BASE_URL))
    text_model: str = field(default_factory=lambda: _setting("SILICONFLOW_TEXT_MODEL", RECOMMENDED_TEXT_MODEL))
    reasoning_effort: str = field(
        default_factory=lambda: normalize_reasoning_effort(_setting("SILICONFLOW_REASONING_EFFORT", DEFAULT_REASONING_EFFORT))
    )
    workspace_dir: Path = WORKSPACE_DIR
    demo_dir: Path = DEMO_DIR

    @property
    def text_ready(self) -> bool:
        return bool(self.api_key and self.base_url and self.text_model)

    @property
    def safe_status(self) -> dict[str, bool]:
        return {"API Key": bool(self.api_key), "文本模型": self.text_ready}


def get_settings() -> Settings:
    settings = Settings()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    return settings


def save_api_settings(api_key: str, base_url: str, text_model: str, reasoning_effort: str) -> None:
    """Persist API settings locally without returning or logging the secret."""
    env_path = ENV_FILE
    env_path.touch(exist_ok=True)
    values = {
        "SILICONFLOW_API_KEY": api_key.strip(),
        "SILICONFLOW_BASE_URL": normalize_base_url(base_url),
        "SILICONFLOW_TEXT_MODEL": text_model.strip() or RECOMMENDED_TEXT_MODEL,
        "SILICONFLOW_REASONING_EFFORT": normalize_reasoning_effort(reasoning_effort),
    }
    for key, value in values.items():
        set_key(str(env_path), key, value, quote_mode="always")
        os.environ[key] = value
