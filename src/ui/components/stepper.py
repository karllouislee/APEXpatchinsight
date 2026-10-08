"""Main-line step navigation.

The app is a pipeline, not a toolbox: 提取更新内容 → 评论收集 → 分析评论 →
统计结果. This strip keeps that order visible at all times, shows how far the
current project has got, and doubles as the only navigation control — so there
is one obvious way through the product instead of a menu of unrelated screens.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ...services.analysis_service import analysis_progress
from ..state import AppContext, KEY_STEP

STATUS_GLYPHS = {"done": "✓", "active": "●", "todo": "○"}


@dataclass(frozen=True)
class Step:
    title: str
    hint: str


STEPS = (
    Step("提取更新内容", "导入官方更新说明并确认改动"),
    Step("评论收集", "导入授权 CSV，清洗去重"),
    Step("分析评论", "批量映射改动并复核边界样本"),
    Step("统计结果", "查看矩阵与卡片，导出结论"),
)


def _counts(ctx: AppContext) -> list[str]:
    """One short, live figure per step — the number you need before moving on."""
    project = ctx.project
    progress = analysis_progress(project)
    if not progress["total"]:
        summary = "待分析"
    elif progress["judged"] < progress["total"]:
        summary = f"{progress['judged']}/{progress['total']} 已判定"
    elif project.reviews:
        summary = f"{len(project.reviews)} 条待复核"
    else:
        summary = "可导出"
    return [
        f"{len(project.changes)} 项改动" if project.changes else "待提取",
        f"{len(project.comments)} 条评论" if project.comments else "待导入",
        f"{progress['classified']}/{progress['total']} 已归类" if progress["total"] else "待分析",
        summary,
    ]


def _analyzed_total(ctx: AppContext) -> tuple[int, int]:
    progress = analysis_progress(ctx.project)
    return progress["classified"], progress["total"]


def _statuses(ctx: AppContext) -> list[str]:
    project = ctx.project
    progress = analysis_progress(project)
    confirmed = sum(1 for change in project.changes if change.confirmed)
    return [
        "done" if project.changes and confirmed == len(project.changes) else ("active" if project.changes else "todo"),
        "done" if project.comments else "todo",
        "done" if progress["total"] and progress["judged"] == progress["total"] else ("active" if project.comments else "todo"),
        "done" if progress["judged"] and not project.reviews else "todo",
    ]


def current_step() -> str:
    return st.session_state.get(KEY_STEP) or STEPS[0].title


def render_stepper(ctx: AppContext) -> str:
    """Render the pipeline strip and return the step the user is on."""
    selected = current_step()
    counts = _counts(ctx)
    statuses = _statuses(ctx)

    columns = st.columns(len(STEPS))
    for column, step, count, status in zip(columns, STEPS, counts, statuses):
        glyph = STATUS_GLYPHS[status]
        column.button(
            f"{glyph} {step.title} · {count}",
            key=f"step::{step.title}",
            width="stretch",
            type="primary" if step.title == selected else "secondary",
            help=step.hint,
            on_click=_goto,
            args=(step.title,),
        )

    done = sum(1 for status in statuses if status == "done")
    st.progress(done / len(STEPS), text=f"流程进度 {done}/{len(STEPS)} 步")
    return selected


def _goto(title: str) -> None:
    st.session_state[KEY_STEP] = title
