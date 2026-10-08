"""Feed the human review trail back into the next analysis run.

Two layers, cheapest first:

1. :func:`core.review_lessons.deterministic_lessons` turns the audit trail into
   "field: 人工由 X 改为 Y（n 例）" bullets. Free, reproducible, always available.
2. Optionally the model generalises those transitions into prose rules ("玩家说
   '没感觉' 应判为力度不足"), which transfer to phrasings nobody corrected yet.

The generalised rules are cached on the project and keyed by a fingerprint of
the correction trail, so one extra request per analysis run at most — and none
at all when nothing has been reviewed or nothing changed since last time.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..core.models import Project, utc_now
from ..core.review_lessons import (
    MAX_RULES,
    correction_digest,
    deterministic_lessons,
)
from ..integrations.siliconflow_client import SiliconFlowClient, SiliconFlowError, load_prompt

PROMPT_NAME = "review_lessons_prompt.txt"
RULES_KEY = "rules"
DIGEST_KEY = "digest"

MODEL_LEAD = "【人工复核经验】以下规则来自人工对模型上一轮判断的修正，本批务必遵守："


class LessonRules(BaseModel):
    rules: list[str] = Field(default_factory=list)

    @field_validator("rules", mode="before")
    @classmethod
    def coerce_rules(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("rules", mode="after")
    @classmethod
    def clean_rules(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lstrip("-").strip() for item in value if str(item).strip()]
        return cleaned[:MAX_RULES]


def render_rules(rules: list[str]) -> str:
    if not rules:
        return ""
    return MODEL_LEAD + "\n" + "\n".join(f"- {item}" for item in rules)


def cached_rules(project: Project) -> list[str]:
    """Rules from the cache, but only while the correction trail is unchanged."""
    cache = project.review_lessons or {}
    if cache.get(DIGEST_KEY) != correction_digest(project):
        return []
    rules = cache.get(RULES_KEY) or []
    return [str(item) for item in rules if str(item).strip()]


def lesson_block(project: Project, client: SiliconFlowClient | None = None, refresh: bool = False) -> tuple[str, str]:
    """Prompt block plus where it came from: ``model`` / ``rules`` / ``none``.

    Never raises: a failed summarisation costs a request but must not block the
    analysis run, so it falls back to the deterministic bullets.
    """
    _lessons, deterministic = deterministic_lessons(project)
    if not deterministic:
        return "", "none"
    if not refresh:
        cached = cached_rules(project)
        if cached:
            return render_rules(cached), "model"
    if client is None:
        return deterministic, "rules"
    try:
        rules = _summarize(project, client)
    except SiliconFlowError:
        return deterministic, "rules"
    project.review_lessons = {
        DIGEST_KEY: correction_digest(project),
        RULES_KEY: rules,
        "updated_at": utc_now(),
    }
    return (render_rules(rules) or deterministic), "model"


def _summarize(project: Project, client: SiliconFlowClient) -> list[str]:
    _lessons, deterministic = deterministic_lessons(project)
    result = client.text_json(load_prompt(PROMPT_NAME), {"corrections": deterministic}, LessonRules)
    return result.rules


def clear_cache(project: Project) -> None:
    project.review_lessons = {}
