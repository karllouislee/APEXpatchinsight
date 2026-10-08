"""Semantic analysis in two stages, plus the human validation workflow.

**Stage 1 — topic.** Every valid comment is classified into a change target.
That alone yields the topic-heat reading, which is usually the first thing
anyone wants and is cheap to produce.

**Stage 2 — attitude, one target at a time.** The classified corpus splits into
buckets by target, and each bucket runs on its own with only that target's
change row. A comment the first stage could not map lands in the
``UNMAPPED`` bucket: it still gets an attitude, because "no matching change"
and "no opinion" are different answers.

Both stages are resumable and every batch is persisted by the caller before the
next one starts, so an interrupted run never pays twice.
"""
from __future__ import annotations

from typing import Any

from ..core.models import (
    STAGE_DONE,
    STAGE_PENDING,
    STAGE_TOPIC,
    CleanComment,
    CommentAnalysis,
    Project,
    ValidationRecord,
    apply_derived_fields,
)
from ..core.review_manager import build_review_queue
from ..core.validation import sample_comments, validation_metrics
from .comment_analyzer import (
    MAX_ATTITUDE_BATCH_SIZE,
    MAX_BATCH_SIZE,
    analyze_attitude_batch,
    analyze_topic_batch,
)
from .insight_generator import deterministic_insights, generate_with_ai

# Bucket label for comments stage 1 could not map to any confirmed change.
UNMAPPED = "未对应到改动"


# --- queue queries -----------------------------------------------------------


def eligible_comments(project: Project) -> list[CleanComment]:
    return [c for c in project.comments if c.is_valid and not c.duplicate_of]


def analysis_by_comment(project: Project) -> dict[str, CommentAnalysis]:
    return {a.comment_id: a for a in project.analyses}


def topic_pending(project: Project) -> list[CleanComment]:
    """Valid comments that stage 1 has not classified yet.

    A missing analysis counts as pending; an existing one counts as done
    whatever its stage, so re-running topic classification only pays for
    comments that have never been classified.
    """
    analyzed = analysis_by_comment(project)
    return [c for c in eligible_comments(project) if c.comment_id not in analyzed]


def attitude_pending(project: Project) -> list[tuple[CleanComment, CommentAnalysis]]:
    """(comment, analysis) pairs that have a topic but no attitude yet."""
    analyzed = analysis_by_comment(project)
    return [
        (c, analyzed[c.comment_id])
        for c in eligible_comments(project)
        if c.comment_id in analyzed and analyzed[c.comment_id].analysis_stage != STAGE_DONE
    ]


def attitude_buckets(project: Project) -> dict[str | None, list[CleanComment]]:
    """Pending attitude comments grouped by the target stage 1 assigned.

    Keyed by target so each group can be sent on its own with only that
    target's change row; ``None`` holds the unmapped ones.
    """
    buckets: dict[str | None, list[CleanComment]] = {}
    for comment, analysis in attitude_pending(project):
        buckets.setdefault(analysis.primary_target, []).append(comment)
    return buckets


def analysis_progress(project: Project) -> dict[str, int]:
    """Stage-aware counters for the UI."""
    candidates = eligible_comments(project)
    analyzed = analysis_by_comment(project)
    classified = sum(1 for c in candidates if c.comment_id in analyzed)
    judged = sum(
        1 for c in candidates
        if c.comment_id in analyzed and analyzed[c.comment_id].analysis_stage == STAGE_DONE
    )
    return {
        "total": len(candidates),
        "classified": classified,
        "judged": judged,
        "topic_pending": len(candidates) - classified,
        "attitude_pending": classified - judged,
    }


# --- stage 1: topic ----------------------------------------------------------


def analyze_next_topic_batch(
    project: Project,
    client,
    alias_dict,
    batch_size: int = MAX_BATCH_SIZE,
    lessons: str = "",
) -> list[CommentAnalysis]:
    """Classify exactly one batch of pending comments and persist it."""
    pending = topic_pending(project)
    if not pending:
        return []
    fresh = analyze_topic_batch(
        pending, project.changes, client, batch_size=batch_size, alias_dict=alias_dict, lessons=lessons
    )
    merge_analyses(project, fresh)
    return fresh


# --- stage 2: attitude -------------------------------------------------------


def analyze_next_attitude_batch(
    project: Project,
    client,
    alias_dict,
    batch_size: int = MAX_ATTITUDE_BATCH_SIZE,
    lessons: str = "",
) -> tuple[str | None, list[CommentAnalysis]]:
    """Judge attitude for one batch of one target.

    Returns ``(bucket_label, fresh)``. ``bucket_label`` is the target the batch
    belongs to (``None`` for the unmapped bucket) so the caller can show which
    change item is being worked on.
    """
    buckets = attitude_buckets(project)
    if not buckets:
        return None, []
    # Deterministic order: mapped targets first (in change-list order), then the
    # unmapped bucket, so a run walks the change items one by one.
    ordered: list[str | None] = []
    for change in project.changes:
        if change.target in buckets and change.target not in ordered:
            ordered.append(change.target)
    ordered.extend(key for key in buckets if key is not None and key not in ordered)
    if None in buckets:
        ordered.append(None)

    target = ordered[0]
    batch = buckets[target][:batch_size]
    fresh = analyze_attitude_batch(
        batch, target, project.changes, client, batch_size=batch_size, alias_dict=alias_dict, lessons=lessons
    )
    merge_attitudes(project, fresh)
    return target, fresh


def merge_analyses(project: Project, fresh: list[CommentAnalysis]) -> None:
    """Fold a batch into the project, replacing any stale rows for the same id."""
    incoming = {analysis.comment_id: analysis for analysis in fresh}
    project.analyses = [
        *[analysis for analysis in project.analyses if analysis.comment_id not in incoming],
        *incoming.values(),
    ]


def merge_attitudes(project: Project, fresh: list[CommentAnalysis]) -> None:
    """Apply stage-2 verdicts onto the stage-1 rows they belong to.

    The target and problem domain were decided in stage 1; only the attitude,
    quote, confidence and sarcasm flag are overwritten. Comments with no stage-1
    row (should not happen, but a resumed run can produce it) are appended.
    """
    incoming = {analysis.comment_id: analysis for analysis in fresh}
    content_by_id = {c.comment_id: c.cleaned_content for c in project.comments}
    merged: list[CommentAnalysis] = []
    for analysis in project.analyses:
        verdict = incoming.pop(analysis.comment_id, None)
        if verdict is None:
            merged.append(analysis)
            continue
        updated = analysis.model_copy(update={
            "analysis_stage": STAGE_DONE,
            "direction_attitude": verdict.direction_attitude,
            "intensity_attitude": verdict.intensity_attitude,
            "evidence_quote": verdict.evidence_quote or analysis.evidence_quote,
            "analysis_confidence": verdict.analysis_confidence,
            "suspected_sarcasm": verdict.suspected_sarcasm,
        })
        merged.append(apply_derived_fields(updated, content_by_id.get(analysis.comment_id, "")))
    merged.extend(incoming.values())
    project.analyses = merged


# --- restart -----------------------------------------------------------------


def clear_analyses(project: Project) -> dict[str, int]:
    """Drop every model-produced result and start over.

    Comments, the human review trail and the sampling validations survive: they
    are inputs and human work, not things the model produced. The cached review
    lessons survive too — they were learned from human corrections and stay
    valid whatever the model does next.
    """
    counts = {
        "analyses": len(project.analyses),
        "reviews": len(project.reviews),
        "insights": len(project.insights or {}),
        "skips": len(project.skipped_reviews),
    }
    project.analyses = []
    project.reviews = []
    project.insights = {}
    # Skip marks belong to the previous analysis round; a fresh run queues
    # everything again.
    project.skipped_reviews = []
    return counts


def reset_attitude(project: Project) -> dict[str, int]:
    """Keep the topic classification, throw the attitudes away.

    Used when the attitude prompt or the review lessons change: re-classifying
    every comment would buy nothing, since stage 1 does not depend on them.
    """
    pending = [analysis for analysis in project.analyses if analysis.analysis_stage == STAGE_DONE]
    for analysis in pending:
        analysis.analysis_stage = STAGE_TOPIC
        analysis.direction_attitude = "无法判断"
        analysis.intensity_attitude = "无法判断"
        analysis.overall_stance = "无法判断"
        analysis.root_issue_status = "无法判断"
        analysis.problem_reason = []
    counts = {"attitude_reset": len(pending)}
    project.reviews = []
    project.insights = {}
    return counts


# --- review queue ------------------------------------------------------------


def rebuild_review_queue(project: Project) -> None:
    project.reviews = build_review_queue(
        project.comments, project.analyses, skipped=project.skipped_reviews
    )


def deterministic_insight_payload(project: Project, stats: dict[str, Any]) -> dict[str, Any]:
    insights = deterministic_insights(project.changes, stats)
    return {item.target: item.model_dump(mode="json") for item in insights}


def ai_insight_payload(project: Project, stats: dict[str, Any], client) -> dict[str, Any]:
    insights = generate_with_ai(project.changes, stats, project.comments, client)
    return {item.target: item.model_dump(mode="json") for item in insights}


def sample_validation_ids(comments: list[CleanComment], size: int) -> list[str]:
    return [comment.comment_id for comment in sample_comments(comments, size)]


def save_validation(project: Project, comment_id: str, values: dict[str, bool | None]) -> None:
    record = ValidationRecord(comment_id=comment_id, **values)
    project.validations = [item for item in project.validations if item.comment_id != comment_id] + [record]


def validation_rows(project: Project) -> list[dict[str, Any]]:
    metrics = validation_metrics(project.validations)
    return [
        {"指标": key, "认可": value["accepted"], "已判断": value["judged"], "认可率": _rate(value)}
        for key, value in metrics.items()
    ]


def _rate(metric: dict[str, Any]) -> str:
    rate = metric.get("rate")
    return "—" if rate is None else f"{rate:.1%}"
