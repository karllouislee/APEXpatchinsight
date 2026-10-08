"""Project-level derived state: statistics plus the human review queue.

Kept separate from :mod:`src.core.aggregation` because these functions take
and mutate a whole :class:`Project` instead of plain lists.
"""
from __future__ import annotations

from typing import Any

from .aggregation import aggregate
from .models import Project
from .review_manager import build_review_queue


def refresh_reviews(project: Project) -> dict[str, Any]:
    """Recompute transparent statistics and drop review tasks already resolved.

    A record counts as resolved when the live comment and analysis still match
    what the reviewer saved — editing them again puts the comment back in the
    queue while the audit trail in ``review_history`` is preserved.
    """
    stats = aggregate(project.changes, project.comments, project.analyses)
    comments_by_id = {comment.comment_id: comment for comment in project.comments}
    analyses_by_id = {analysis.comment_id: analysis for analysis in project.analyses}

    resolved_ids: set[str] = set()
    for record in project.review_history:
        if not record.modified_at:
            continue
        current_comment = comments_by_id.get(record.comment_id)
        current_analysis = analyses_by_id.get(record.comment_id)
        if current_comment is None:
            continue
        if current_comment.model_dump(mode="json") != record.corrected.get("comment"):
            continue
        current_payload = current_analysis.model_dump(mode="json") if current_analysis else None
        if current_payload == record.corrected.get("analysis"):
            resolved_ids.add(record.comment_id)

    project.reviews = [
        record
        for record in build_review_queue(
            project.comments, project.analyses, skipped=project.skipped_reviews
        )
        if record.comment_id not in resolved_ids
    ]
    return stats


def format_rate(metric: dict[str, Any] | None) -> str:
    rate = metric.get("rate") if metric else None
    return "—" if rate is None else f"{rate:.1%}"
