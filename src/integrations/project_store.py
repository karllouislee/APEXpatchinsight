from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.models import Project, utc_now


def safe_project_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned or "project"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, project_id: str) -> Path:
        return self.root / f"{safe_project_id(project_id)}.json"

    def save(self, project: Project) -> Path:
        project.updated_at = utc_now()
        path = self.path_for(project.project_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return path

    def load(self, project_id: str) -> Project:
        return Project.model_validate_json(self.path_for(project_id).read_text(encoding="utf-8"))

    def list_projects(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))

    def export_json(self, project: Project) -> str:
        return json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2)
