"""Human review of the edge cases the analysis flagged.

The queue supports prev/next navigation and a per-item skip, so a reviewer can
walk the list linearly instead of re-picking from a dropdown after every save.
The form only asks for judgements the comment text can actually support — who
the comment is about and which way it leans. Attitude-shaped rollups the text
cannot support (问题类型 / 力度态度 / 原问题状态) are not editable here: a
human cannot reliably pick them from a comment, so the values the analysis
produced simply stand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

from ...core.models import CleanComment, CommentAnalysis, Project, ReviewRecord
from ...core.review_manager import record_correction
from ...core.text_utils import split_keywords
from ..state import AppContext

DIRECTION_VALUES = ["支持改动方向", "反对改动方向", "对方向没有明确态度", "无法判断"]
STANCE_VALUES = ["支持", "反对", "条件性支持", "需要继续观察", "仅描述现象", "玩梗或无有效信息", "与当前改动无关", "无法判断"]
QUALITY_VALUES = ["高", "中", "低"]

SELECT_KEY = "review-selected-task"


@dataclass
class ReviewForm:
    """Everything the reviewer can correct for one queued comment.

    Fields the comment text cannot support are deliberately absent: they are
    never overwritten by a review save, so the analysis keeps whatever it
    produced for them.
    """

    text: str = ""
    is_valid: bool = True
    duplicate_of: str | None = None
    manual_keywords: str = ""
    primary: str | None = None
    secondary: list[str] = field(default_factory=list)
    direction: str = "无法判断"
    stance: str = "无法判断"
    quality: str = "中"
    reasons_text: str = ""
    evidence_quote: str = ""
    suspected_sarcasm: bool = False

    def apply(self, comment: CleanComment, analysis: CommentAnalysis | None) -> tuple[CleanComment, CommentAnalysis | None, dict]:
        corrected_comment = comment.model_copy(deep=True)
        corrected_comment.cleaned_content = self.text
        corrected_comment.content = self.text
        corrected_comment.is_valid = self.is_valid
        corrected_comment.duplicate_of = self.duplicate_of
        corrected_comment.manual_keywords = split_keywords(self.manual_keywords)

        corrected_analysis = analysis.model_copy(deep=True) if analysis else None
        if corrected_analysis is not None:
            corrected_analysis.primary_target = self.primary or None
            corrected_analysis.secondary_targets = list(self.secondary)
            corrected_analysis.problem_reason = split_keywords(self.reasons_text)
            corrected_analysis.direction_attitude = self.direction
            corrected_analysis.overall_stance = self.stance
            corrected_analysis.information_quality = self.quality
            corrected_analysis.evidence_quote = self.evidence_quote
            corrected_analysis.suspected_sarcasm = self.suspected_sarcasm

        payload = {
            "comment": corrected_comment.model_dump(mode="json"),
            "analysis": corrected_analysis.model_dump(mode="json") if corrected_analysis else None,
        }
        return corrected_comment, corrected_analysis, payload


def _index_of(options: list[Any], value: Any) -> int:
    return options.index(value) if value in options else 0


def _duplicate_choice(container, project: Project, comment: CleanComment) -> str | None:
    others = [None, *[item.comment_id for item in project.comments if item.comment_id != comment.comment_id]]
    return container.selectbox(
        "重复于",
        others,
        index=_index_of(others, comment.duplicate_of),
        key=f"review-duplicate-{comment.comment_id}",
    )


def _render_form(ctx: AppContext, record: ReviewRecord) -> None:
    project = ctx.project
    comment = next((item for item in project.comments if item.comment_id == record.comment_id), None)
    if comment is None:
        st.error("该评论已不存在，无法复核。")
        return

    analysis = next((item for item in project.analyses if item.comment_id == record.comment_id), None)
    st.caption(f"修正 {comment.comment_id}")
    form = ReviewForm(
        text=st.text_area("评论原文", comment.cleaned_content, key=f"review-text-{comment.comment_id}")
    )
    basic_left, basic_right = st.columns(2)
    form.is_valid = basic_left.checkbox(
        "有效评论", value=comment.is_valid, key=f"review-valid-{comment.comment_id}"
    )
    form.duplicate_of = _duplicate_choice(basic_right, project, comment)
    form.manual_keywords = st.text_input(
        "人工关键词（逗号分隔）",
        value="，".join(comment.manual_keywords),
        key=f"review-keywords-{comment.comment_id}",
    )

    if analysis is not None:
        targets = [change.target for change in project.changes if change.target]
        primary_options = [None, *targets]
        map_left, map_right = st.columns(2)
        form.primary = map_left.selectbox(
            "主要改动对象", primary_options, index=_index_of(primary_options, analysis.primary_target),
            key=f"review-primary-{comment.comment_id}",
        )
        form.secondary = map_right.multiselect(
            "次要改动对象", targets,
            default=[item for item in analysis.secondary_targets if item in targets],
            key=f"review-secondary-{comment.comment_id}",
        )
        col1, col2, col3 = st.columns(3)
        form.direction = col1.selectbox(
            "方向态度", DIRECTION_VALUES, index=_index_of(DIRECTION_VALUES, analysis.direction_attitude),
            key=f"review-direction-{comment.comment_id}",
        )
        form.stance = col2.selectbox(
            "整体立场", STANCE_VALUES, index=_index_of(STANCE_VALUES, analysis.overall_stance),
            key=f"review-stance-{comment.comment_id}",
        )
        form.quality = col3.selectbox(
            "信息质量", QUALITY_VALUES, index=_index_of(QUALITY_VALUES, analysis.information_quality),
            key=f"review-quality-{comment.comment_id}",
        )
        form.reasons_text = st.text_area(
            "问题原因（逗号分隔）", value="，".join(analysis.problem_reason), key=f"review-reasons-{comment.comment_id}"
        )
        form.evidence_quote = st.text_area(
            "证据引文", value=analysis.evidence_quote, key=f"review-evidence-{comment.comment_id}"
        )
        form.suspected_sarcasm = st.checkbox(
            "疑似反讽或玩梗", value=analysis.suspected_sarcasm, key=f"review-sarcasm-{comment.comment_id}"
        )

    if st.button("确认并保存复核", type="primary", width="stretch", key=f"save-review-{comment.comment_id}"):
        corrected_comment, corrected_analysis, payload = form.apply(comment, analysis)
        audit = record_correction(record.model_copy(deep=True), payload)
        project.review_history.append(audit)
        project.comments = [
            corrected_comment if item.comment_id == corrected_comment.comment_id else item
            for item in project.comments
        ]
        if corrected_analysis is not None:
            project.analyses = [
                corrected_analysis if item.comment_id == corrected_analysis.comment_id else item
                for item in project.analyses
            ]
        ctx.persist_comments()
        ctx.store.save(project)
        st.success(f"复核已保存；记录 {len(audit.changed_fields)} 个修改字段。")
        st.rerun()


def _render_history(project: Project) -> None:
    if not project.review_history:
        return
    with st.expander(f"复核历史（{len(project.review_history)} 条）", expanded=False):
        rows = [{
            "comment_id": item.comment_id,
            "修改时间": item.modified_at,
            "修改字段": "、".join(item.changed_fields) or "确认原判断",
            "入队原因": "、".join(item.reasons),
        } for item in reversed(project.review_history)]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _restore_skipped(ctx: AppContext) -> None:
    """Put every skipped task back into the queue and rebuild it."""
    ctx.project.skipped_reviews = []
    ctx.recalculate()
    ctx.store.save(ctx.project)
    st.session_state.pop(SELECT_KEY, None)


def _render_queue(ctx: AppContext) -> ReviewRecord | None:
    """The queue column: navigation, selection, skip — returns the picked task."""
    project = ctx.project
    options = {f"{item.comment_id} · {' / '.join(item.reasons)}": item for item in project.reviews}
    labels = list(options)

    current = st.session_state.get(SELECT_KEY)
    if current not in labels:
        st.session_state[SELECT_KEY] = labels[0]
        current = labels[0]

    nav_left, nav_right = st.columns(2)
    if nav_left.button("← 上一条", width="stretch", disabled=len(labels) < 2):
        index = labels.index(current)
        st.session_state[SELECT_KEY] = labels[max(index - 1, 0)]
    if nav_right.button("下一条 →", width="stretch", disabled=len(labels) < 2):
        index = labels.index(current)
        st.session_state[SELECT_KEY] = labels[min(index + 1, len(labels) - 1)]

    record = options[st.session_state[SELECT_KEY]]
    st.selectbox("待复核队列", labels, key=SELECT_KEY)

    skipped = len(project.skipped_reviews)
    skip_col, restore_col = st.columns(2)
    if skip_col.button("跳过此条（不再提醒）", width="stretch"):
        if record.comment_id not in project.skipped_reviews:
            project.skipped_reviews.append(record.comment_id)
        project.reviews = [item for item in project.reviews if item.comment_id != record.comment_id]
        ctx.store.save(project)
        st.rerun()
    if restore_col.button(
        f"恢复已跳过的 {skipped} 条", width="stretch", disabled=not skipped, type="primary" if skipped else "secondary"
    ):
        _restore_skipped(ctx)
        st.rerun()

    st.markdown("**入队原因**")
    for reason in record.reasons:
        st.write(f"- {reason}")
    with st.expander("AI 原判断（只读）", expanded=False):
        st.json(record.original, expanded=True)
    return record


def render_review_panel(ctx: AppContext) -> None:
    project = ctx.project
    history = len(project.review_history)
    pending = len(project.reviews)
    skipped = len(project.skipped_reviews)
    summary = f"人工复核 · 待处理 {pending} · 已留痕 {history}"
    if skipped:
        summary += f" · 已跳过 {skipped}"
    st.caption(summary)

    _render_history(project)

    if not project.reviews:
        if skipped:
            if st.button(f"恢复已跳过的 {skipped} 条复核项", width="stretch"):
                _restore_skipped(ctx)
                st.rerun()
        st.caption("没有待复核项。模型重跑后若结果变化，相关评论会重新入队，旧留痕仍保留。")
        return

    queue_col, edit_col = st.columns([1, 2], gap="large")
    with queue_col:
        record = _render_queue(ctx)
    with edit_col:
        _render_form(ctx, record)
