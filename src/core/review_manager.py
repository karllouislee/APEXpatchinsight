from __future__ import annotations

from copy import deepcopy

from .text_utils import normalize_for_quote
from .models import CleanComment, CommentAnalysis, ReviewRecord, utc_now


def review_reasons(comment: CleanComment, analysis: CommentAnalysis | None) -> list[str]:
    reasons: list[str] = []
    if not comment.is_complete:
        reasons.append("评论内容不完整")
    if comment.suspected_duplicate:
        reasons.append("疑似重复评论")
    if not analysis:
        reasons.append("尚未完成语义分析")
        return reasons
    if analysis.analysis_confidence < 0.70:
        reasons.append("分析置信度低于 0.70")
    if analysis.suspected_sarcasm:
        reasons.append("疑似反讽或玩梗")
    if len(analysis.secondary_targets) > 0:
        reasons.append("同时匹配多个改动")
    if analysis.direction_attitude == "无法判断":
        reasons.append("态度无法判断")
    if analysis.evidence_quote and normalize_for_quote(analysis.evidence_quote) not in normalize_for_quote(comment.cleaned_content):
        reasons.append("evidence_quote 无法在原文中找到")
    return reasons


def build_review_queue(
    comments: list[CleanComment],
    analyses: list[CommentAnalysis],
    skipped: list[str] | tuple[str, ...] = (),
) -> list[ReviewRecord]:
    """Queue the analysed corpus for human review.

    Comments ruled invalid or duplicate during cleaning are skipped: analysis
    never runs on them, so they would otherwise sit in the queue forever with
    the misleading "尚未完成语义分析" reason. Comments the reviewer explicitly
    skipped are left out too, so a skipped task survives queue rebuilds.
    """
    skip_ids = set(skipped)
    lookup = {analysis.comment_id: analysis for analysis in analyses}
    queue: list[ReviewRecord] = []
    for comment in comments:
        if not comment.is_valid or comment.duplicate_of or comment.comment_id in skip_ids:
            continue
        analysis = lookup.get(comment.comment_id)
        reasons = review_reasons(comment, analysis)
        if reasons:
            original = {"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json") if analysis else None}
            queue.append(ReviewRecord(comment_id=comment.comment_id, reasons=reasons, original=original, corrected=deepcopy(original)))
    return queue


def record_correction(record: ReviewRecord, corrected: dict) -> ReviewRecord:
    record.corrected = deepcopy(corrected)
    changed_fields: list[str] = []
    for section in ("comment", "analysis"):
        before = record.original.get(section) or {}
        after = corrected.get(section) or {}
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                changed_fields.append(f"{section}.{key}")
    record.changed_fields = changed_fields
    record.modified_at = utc_now()
    return record

