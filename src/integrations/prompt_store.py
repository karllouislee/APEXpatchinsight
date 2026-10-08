"""Prompt files on disk plus in-memory per-session overrides.

Prompts ship as plain text under ``prompts/`` so they can be reviewed and
diffed like code. Edits made in the sidebar are kept in memory only: they
never rewrite the bundled files.
"""
from __future__ import annotations

from ..core.paths import PROMPTS_DIR

_overrides: dict[str, str] = {}


def list_prompts() -> list[str]:
    return sorted(path.name for path in PROMPTS_DIR.glob("*.txt"))


def read_prompt(name: str) -> str:
    return _overrides.get(name) or (PROMPTS_DIR / name).read_text(encoding="utf-8")


def set_prompt_override(name: str, content: str) -> None:
    content = content.strip()
    if content:
        _overrides[name] = content
    else:
        _overrides.pop(name, None)


def reset_prompt_override(name: str) -> str:
    _overrides.pop(name, None)
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")
