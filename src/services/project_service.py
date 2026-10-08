"""Bootstrap and persistence for the active project and its comment corpus."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.models import CleanComment, Project, RawComment
from ..core.paths import DEMO_DIR
from ..core.settings import Settings
from ..integrations.comment_store import (
    clear_comment_store,
    load_comment_store,
    save_comment_store,
)
from ..integrations.project_store import ProjectStore
from .demo_data import build_demo_project

# Files that live next to projects but are not projects.
NON_PROJECT_JSON = {"comments_store.json", "community_aliases.override.json"}


def _demo_project() -> Project:
    demo_path = DEMO_DIR / "project.json"
    if demo_path.exists():
        return Project.model_validate_json(demo_path.read_text(encoding="utf-8"))
    return build_demo_project(DEMO_DIR)


def load_latest_project(workspace_dir: Path) -> Project | None:
    """Return the most recently saved project so work survives a restart."""
    if not workspace_dir.exists():
        return None
    candidates = sorted(
        (path for path in workspace_dir.glob("*.json") if path.name not in NON_PROJECT_JSON and not path.name.endswith(".tmp")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            return Project.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def load_or_create_project(settings: Settings) -> Project:
    return load_latest_project(settings.workspace_dir) or _demo_project()


def load_comment_corpus(workspace_dir: Path) -> dict[str, Any]:
    return load_comment_store(workspace_dir)


def apply_restored_comments(project: Project, store: dict[str, Any]) -> int:
    """Attach a persisted corpus, downgrading a demo project to a real one.

    Mixing real comments into the fictional demo would blend two unrelated
    contexts, so the demo's changes and article are dropped while the comments
    are kept.
    """
    comments: list[CleanComment] = store.get("comments") or []
    if not comments:
        return 0
    project.comments = comments
    if project.is_demo:
        project.is_demo = False
        project.demo_disclaimer = ""
        project.changes = []
        project.article = None
    return len(comments)


def raw_comment_models(raw: list[dict[str, Any]]) -> list[RawComment]:
    return [RawComment.model_validate(item) for item in raw]


def raw_comment_payloads(raw: list[RawComment]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in raw]


def persist_comment_corpus(
    workspace_dir: Path,
    raw_comments: list[RawComment],
    comments: list[CleanComment],
) -> Path:
    """Auto-save the corpus after every mutation (提取 / 人工修正 / 清空)."""
    return save_comment_store(workspace_dir, raw_comments, comments, datetime.now().isoformat())


def clear_comment_corpus(workspace_dir: Path) -> None:
    clear_comment_store(workspace_dir)


def save_project(store: ProjectStore, project: Project) -> Path:
    return store.save(project)
