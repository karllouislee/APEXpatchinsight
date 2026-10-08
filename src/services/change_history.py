"""Save/restore snapshots of a structured change list under workspace/change_history."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..core.models import PatchChange
from ..core.paths import CHANGE_HISTORY_DIR


def safe_history_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return cleaned or "changes"


def save_change_history(name: str, changes: list[PatchChange]) -> Path:
    CHANGE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CHANGE_HISTORY_DIR / f"{timestamp}_{safe_history_name(name)}.json"
    path.write_text(
        json.dumps([change.model_dump(mode="json") for change in changes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_change_history(path: Path) -> list[PatchChange]:
    return [PatchChange.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def list_change_history() -> list[Path]:
    if not CHANGE_HISTORY_DIR.exists():
        return []
    return sorted(CHANGE_HISTORY_DIR.glob("*.json"), reverse=True)
