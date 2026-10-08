"""Turn the human review trail into guidance for the next analysis run.

The correction log (``Project.review_history``) is the highest-signal material
in the whole project: every row is a case where a human looked at the model's
verdict and disagreed. Left in the audit table it teaches nothing, so it is
condensed into a short block that is injected into the analysis prompt.

Extraction is deterministic and lives in ``core``: no model call, no IO, and the
same corrections always produce the same rules. :mod:`services.review_learning`
optionally asks the model to generalise the transitions into prose rules on top
of this, but the deterministic text stands on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import Project, ReviewRecord

FIELD_LABELS = {
    "primary_target": "改动对象",
    "problem_domain": "问题类型",
    "direction_attitude": "方向态度",
    "intensity_attitude": "力度态度",
    "overall_stance": "整体立场",
    "root_issue_status": "原问题状态",
    "information_quality": "信息质量",
    "suspected_sarcasm": "是否反讽",
    "problem_reason": "问题原因",
}

# Corrections below a single example are noise, not a pattern.
MIN_COUNT_FOR_RULE = 2
MAX_EXAMPLES = 2
MAX_EXAMPLE_CHARS = 24
MAX_RULES = 12


@dataclass
class Correction:
    """One field a reviewer changed, with the comment that triggered it."""

    field: str
    old: str
    new: str
    example: str = ""

    @property
    def label(self) -> str:
        return FIELD_LABELS.get(self.field, self.field)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.field, self.old, self.new)


@dataclass
class Lesson:
    """A recurring correction, aggregated across the review trail."""

    field: str
    old: str
    new: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, correction: Correction) -> None:
        self.count += 1
        if correction.example and len(self.examples) < MAX_EXAMPLES:
            self.examples.append(correction.example)

    def render(self) -> str:
        label = FIELD_LABELS.get(self.field, self.field)
        if self.old in ("", "未识别"):
            tail = f"人工补判为「{self.new}」"
        else:
            tail = f"人工由「{self.old}」改为「{self.new}」"
        text = f"- {label}：{tail}（{self.count} 例）"
        if self.examples:
            quoted = "、".join(f"“{item}”" for item in self.examples)
            text += f"。例：{quoted}"
        return text


def _display(value: Any) -> str:
    if value is None:
        return "未识别"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(items) if items else "未识别"
    text = str(value).strip()
    return text or "未识别"


def _clip(text: str, limit: int = MAX_EXAMPLE_CHARS) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def iter_corrections(records: Iterable[ReviewRecord]) -> list[Correction]:
    """Flatten the audit trail into one entry per changed analysis field."""
    output: list[Correction] = []
    for record in records:
        before = record.original.get("analysis") or {}
        after = record.corrected.get("analysis") or {}
        if not before and not after:
            continue
        comment_text = _clip((record.original.get("comment") or {}).get("cleaned_content", ""))
        for name in FIELD_LABELS:
            old, new = before.get(name), after.get(name)
            if old == new:
                continue
            # A field the model was never asked for carries no lesson.
            if name not in before and name not in after:
                continue
            output.append(Correction(field=name, old=_display(old), new=_display(new), example=comment_text))
    return output


def build_lessons(records: Iterable[ReviewRecord], min_count: int = MIN_COUNT_FOR_RULE) -> list[Lesson]:
    """Aggregate corrections into recurring patterns, most frequent first."""
    grouped: dict[tuple[str, str, str], Lesson] = {}
    for correction in iter_corrections(records):
        lesson = grouped.get(correction.key)
        if lesson is None:
            lesson = Lesson(field=correction.field, old=correction.old, new=correction.new)
            grouped[correction.key] = lesson
        lesson.add(correction)
    lessons = [item for item in grouped.values() if item.count >= min_count]
    lessons.sort(key=lambda item: (-item.count, item.field, item.old, item.new))
    return lessons[:MAX_RULES]


def render_lessons(lessons: list[Lesson]) -> str:
    """Prompt-injectable block; empty string when there is nothing to teach."""
    if not lessons:
        return ""
    lines = [lesson.render() for lesson in lessons]
    return "【人工复核经验】以下是人工复核中反复修正过的判断，本批请按此调整：\n" + "\n".join(lines)


def deterministic_lessons(project: Project) -> tuple[list[Lesson], str]:
    """(lessons, prompt block) derived from the project's review trail."""
    lessons = build_lessons(project.review_history)
    return lessons, render_lessons(lessons)


def correction_digest(project: Project) -> str:
    """Stable fingerprint of the trail, used to invalidate cached rule text."""
    lessons, _ = deterministic_lessons(project)
    return "\n".join(f"{item.field}|{item.old}|{item.new}|{item.count}" for item in lessons)


def correction_summary(project: Project) -> dict[str, int]:
    """Counts for the UI: how much material the learning block is built from."""
    corrections = iter_corrections(project.review_history)
    lessons = build_lessons(project.review_history)
    return {
        "复核记录": len(project.review_history),
        "修正字段": len(corrections),
        "归纳规律": len(lessons),
    }
