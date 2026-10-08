"""Single source of truth for every filesystem location the app touches.

Modules used to derive their own roots with ``Path(__file__).parents[1]``,
which silently breaks whenever a file moves one level deeper. Anything that
needs a project path imports it from here instead.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"

DEMO_DIR = DATA_DIR / "demo"
COMMUNITY_ALIASES_FILE = DATA_DIR / "community_aliases.json"

CHANGE_HISTORY_DIR = WORKSPACE_DIR / "change_history"

ENV_FILE = PROJECT_ROOT / ".env"
