"""Persist the comment corpus (raw imported comments + cleaned comments)
so a later session can keep appending new CSV imports to the same corpus.

Storage: workspace/comments_store.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.models import CleanComment, RawComment

STORE_FILENAME = "comments_store.json"


def store_path(root: Path) -> Path:
    return root / STORE_FILENAME


def _comment_id_number(comment_id: str) -> int | None:
    if not comment_id.startswith("COM-"):
        return None
    try:
        return int(comment_id.split("-", 1)[1])
    except ValueError:
        return None


def merge_extracted_comments(existing: list[RawComment], extracted: list[RawComment]) -> list[RawComment]:
    """Append newly extracted comments with fresh, stable comment_ids.

    Existing comments keep their ids (analyses and review records reference
    them), new ones continue after the current max — re-running recognition
    on a later import never renumbers the old corpus.
    """
    next_number = max(
        (number for comment in existing if (number := _comment_id_number(comment.comment_id)) is not None),
        default=0,
    ) + 1
    for comment in extracted:
        comment.comment_id = f"COM-{next_number:04d}"
        next_number += 1
    return [*existing, *extracted]


def load_comment_store(root: Path) -> dict[str, Any]:
    path = store_path(root)
    if not path.exists():
        return {"raw_comments": [], "comments": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"raw_comments": [], "comments": []}
    return {
        "raw_comments": list(data.get("raw_comments", [])),
        "comments": [CleanComment.model_validate(item) for item in data.get("comments", [])],
        "updated_at": data.get("updated_at", ""),
    }


def save_comment_store(root: Path, raw_comments: list[RawComment], comments: list[CleanComment], updated_at: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = store_path(root)
    payload = {
        "version": 1,
        "updated_at": updated_at,
        "raw_comments": [item.model_dump(mode="json") for item in raw_comments],
        "comments": [item.model_dump(mode="json") for item in comments],
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def clear_comment_store(root: Path) -> None:
    store_path(root).unlink(missing_ok=True)
