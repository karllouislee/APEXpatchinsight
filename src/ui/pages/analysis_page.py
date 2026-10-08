"""Step 3 — two-stage analysis, then review of the edge cases.

Stage 1 classifies every comment into a change topic and stops for a heat
reading; stage 2 walks the change items one at a time and judges attitude. Each
stage is its own button, its own progress bar and its own stop control, so the
two halves of the question (在说谁 / 怎么看) stay separately restartable.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core.analytics import format_rate
from ...core.models import STAGE_DONE
from ...core.review_lessons import correction_summary
from ...integrations.siliconflow_client import SiliconFlowError
from ...services import analysis_service
from ...services.comment_analyzer import MAX_ATTITUDE_BATCH_SIZE, batch_count
from ...services.review_learning import cached_rules, clear_cache, lesson_block
from ..components.review_panel import render_review_panel
from ..state import AppContext, KEY_CONFIRM_CLEAR_ANALYSIS, KEY_CONFIRM_RESET_ATTITUDE

BATCH_SIZE = 20
STAGE_TOPIC = "话题归类"
STAGE_ATTITUDE = "态度分析"

LESSON_SOURCE_LABEL = {"model": "模型归纳", "rules": "规则归纳", "none": "暂无"}


# --- stage runners -----------------------------------------------------------


def _advance_topic_run(ctx: AppContext, run: dict) -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    total = progress["total"]
    pending = progress["topic_pending"]
    done_batches = int(run.get("done", 0))
    batch_total = max(1, batch_count(run["total"], BATCH_SIZE))
    tokens = ctx.monitor.token_totals()

    st.progress(
        progress["classified"] / total if total else 1.0,
        text=f"第 1 步 · 话题归类 {progress['classified']}/{total}",
    )
    st.caption(
        f"第 {min(done_batches + 1, batch_total)}/{batch_total} 批 · "
        f"输入 {tokens['prompt']:,} / 输出 {tokens['completion']:,} / 思考 {tokens['reasoning']:,} tokens"
    )
    st.button("停止归类（保留已完成部分）", on_click=ctx.stop_analysis_run, width="stretch")

    if not run["active"]:
        _finish_run(ctx, STAGE_TOPIC, "stopped")
        return

    try:
        with st.spinner(f"正在归类第 {min(done_batches + 1, batch_total)}/{batch_total} 批…"):
            lessons, _source = lesson_block(ctx.project, ctx.client if ctx.settings.text_ready else None)
            analysis_service.analyze_next_topic_batch(
                ctx.project, ctx.client, ctx.alias_dict, BATCH_SIZE, lessons=lessons
            )
    except SiliconFlowError as exc:
        _finish_run(ctx, STAGE_TOPIC, "error", message=str(exc))
        return

    run["done"] = done_batches + 1
    analysis_service.rebuild_review_queue(ctx.project)
    ctx.store.save(ctx.project)

    if not analysis_service.topic_pending(ctx.project):
        _finish_run(ctx, STAGE_TOPIC, "done")
        return
    st.rerun()


def _advance_attitude_run(ctx: AppContext, run: dict) -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    buckets = analysis_service.attitude_buckets(ctx.project)
    pending = sum(len(items) for items in buckets.values())
    done_batches = int(run.get("done", 0))
    batch_total = max(1, batch_count(run["total"], MAX_ATTITUDE_BATCH_SIZE))
    tokens = ctx.monitor.token_totals()
    bucket_count = len(buckets)

    st.progress(
        progress["judged"] / progress["total"] if progress["total"] else 1.0,
        text=f"第 2 步 · 态度分析 {progress['judged']}/{progress['total']}",
    )
    st.caption(
        f"剩余 {bucket_count} 个改动对象 · 第 {min(done_batches + 1, batch_total)}/{batch_total} 批 · "
        f"输入 {tokens['prompt']:,} / 输出 {tokens['completion']:,} / 思考 {tokens['reasoning']:,} tokens"
    )
    st.button("停止分析（保留已完成部分）", on_click=ctx.stop_analysis_run, width="stretch")

    if not run["active"]:
        _finish_run(ctx, STAGE_ATTITUDE, "stopped")
        return

    try:
        with st.spinner("正在逐个改动对象分析态度…"):
            lessons, _source = lesson_block(ctx.project, ctx.client if ctx.settings.text_ready else None)
            target, _fresh = analysis_service.analyze_next_attitude_batch(
                ctx.project, ctx.client, ctx.alias_dict, MAX_ATTITUDE_BATCH_SIZE, lessons=lessons
            )
    except SiliconFlowError as exc:
        _finish_run(ctx, STAGE_ATTITUDE, "error", message=str(exc))
        return

    run["done"] = done_batches + 1
    analysis_service.rebuild_review_queue(ctx.project)
    ctx.store.save(ctx.project)

    if not analysis_service.attitude_buckets(ctx.project):
        _finish_run(ctx, STAGE_ATTITUDE, "done")
        return
    st.rerun()


def _finish_run(ctx: AppContext, stage: str, status: str, message: str = "") -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    analysis_service.rebuild_review_queue(ctx.project)
    ctx.store.save(ctx.project)
    done = progress["judged"] if stage == STAGE_ATTITUDE else progress["classified"]
    ctx.finish_analysis_run(status, done, progress["total"], message)
    st.rerun()


def _render_result(ctx: AppContext) -> None:
    result = ctx.consume_analysis_result()
    if not result:
        return
    status, analyzed, total = result["status"], result["analyzed"], result["total"]
    if status == "done":
        st.success(f"已完成 {analyzed}/{total} 条，生成 {len(ctx.project.reviews)} 条复核任务。")
    elif status == "stopped":
        st.warning(f"已停止：本轮完成 {analyzed}/{total} 条，结果已保存，可随时继续。")
    else:
        st.error(f"已中断：本轮完成 {analyzed}/{total} 条，已分析的结果已保存。{result['message']}")


# --- stage 1 controls --------------------------------------------------------


def _render_topic_stage(ctx: AppContext) -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    left, right = st.columns([3, 1])
    with left:
        st.metric("话题归类", f"{progress['classified']}/{progress['total']}", "已归类 / 有效评论")
    with right:
        if st.button(
            "① 归类话题" if progress["topic_pending"] else "话题已归类",
            disabled=not ctx.settings.text_ready or not progress["topic_pending"],
            type="primary",
            width="stretch",
        ):
            ctx.start_analysis_run(STAGE_TOPIC, progress["topic_pending"], BATCH_SIZE)
            st.rerun()

    if progress["topic_pending"]:
        st.caption(f"待归类 {progress['topic_pending']} 条 · 每批 {BATCH_SIZE} 条 · 每批结束即保存")
    elif not ctx.settings.text_ready:
        st.caption("文本模型未就绪：请在侧边栏填写 API Key 与模型。")


# --- stage 2 controls --------------------------------------------------------


def _render_attitude_stage(ctx: AppContext) -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    buckets = analysis_service.attitude_buckets(ctx.project)
    pending = sum(len(items) for items in buckets.values())
    ready = bool(ctx.project.changes) and progress["classified"] > 0

    left, right = st.columns([3, 1])
    with left:
        st.metric("态度分析", f"{progress['judged']}/{progress['classified']}", "已判定 / 已归类")
    with right:
        if st.button(
            "② 分析态度" if pending else "态度已分析",
            disabled=not ctx.settings.text_ready or not ready or not pending,
            width="stretch",
        ):
            ctx.start_analysis_run(STAGE_ATTITUDE, pending, MAX_ATTITUDE_BATCH_SIZE)
            st.rerun()

    if not progress["classified"]:
        st.caption("先完成第 1 步话题归类，才能按改动对象逐个分析态度。")
        return
    if pending:
        names = "、".join(_bucket_label(target) for target in list(buckets)[:4])
        more = f" 等 {len(buckets)} 个" if len(buckets) > 4 else ""
        st.caption(f"待分析 {pending} 条 · {len(buckets)} 个改动对象（{names}{more}）· 每个对象单独请求")
    else:
        st.caption("全部已归类评论都完成了态度分析。")


def _bucket_label(target: str | None) -> str:
    return target or analysis_service.UNMAPPED


# --- topic heat --------------------------------------------------------------


def _render_topic_heat(ctx: AppContext) -> None:
    """The reading stage 1 exists to produce, shown before any attitude is judged."""
    stats = ctx.recalculate()
    targets = stats.get("targets", {})
    if not targets:
        return
    judged = sum(1 for a in ctx.project.analyses if a.analysis_stage == STAGE_DONE)
    st.caption("改动对象 × 相关评论数（话题热度）" + ("" if judged else " · 态度分析尚未开始"))
    rows = []
    for target, item in sorted(targets.items(), key=lambda pair: -pair[1].get("related_count", 0)):
        rows.append({
            "改动对象": target,
            "相关评论": item.get("related_count", 0),
            "问题类型": item.get("category", ""),
            "态度判定": "已开始" if judged else "待第 2 步",
            "方向支持率": format_rate(item.get("direction_support", {})) if judged else "—",
        })
    frame = pd.DataFrame(rows)
    peak = int(frame["相关评论"].max() or 1) if len(frame) else 1
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={"相关评论": st.column_config.ProgressColumn(min_value=0, max_value=peak)},
    )


# --- restart -----------------------------------------------------------------


def _render_restart(ctx: AppContext) -> None:
    progress = analysis_service.analysis_progress(ctx.project)
    if not progress["classified"] and not progress["topic_pending"]:
        return
    with st.expander("重新开始分析", expanded=False):
        confirming_clear = st.session_state.get(KEY_CONFIRM_CLEAR_ANALYSIS)
        confirming_reset = st.session_state.get(KEY_CONFIRM_RESET_ATTITUDE)

        if confirming_clear:
            st.warning(
                f"将删除 {progress['classified']} 条分析结果、{len(ctx.project.reviews)} 条待复核任务"
                f"与 {len(ctx.project.skipped_reviews)} 条跳过记录。"
                "评论、人工复核历史与抽样验证记录会保留。"
            )
            left, right = st.columns(2)
            if left.button("确认清空全部分析", type="primary", width="stretch"):
                counts = ctx.clear_analysis()
                st.success(f"已清空 {counts['analyses']} 条分析结果，可重新开始。")
                st.rerun()
            if right.button("取消", width="stretch"):
                st.session_state[KEY_CONFIRM_CLEAR_ANALYSIS] = False
                st.rerun()
        elif confirming_reset:
            st.warning(
                f"将保留话题归类结果，重新分析 {progress['classified'] - progress['attitude_pending']} 条评论的态度。"
                "方向总结与待复核队列会一并清空。"
            )
            left, right = st.columns(2)
            if left.button("确认只重跑态度", type="primary", width="stretch"):
                counts = analysis_service.reset_attitude(ctx.project)
                ctx.store.save(ctx.project)
                st.success(f"已重置 {counts['attitude_reset']} 条态度判定。")
                st.rerun()
            if right.button("取消", width="stretch"):
                st.session_state[KEY_CONFIRM_RESET_ATTITUDE] = False
                st.rerun()
        else:
            left, right = st.columns(2)
            if left.button("清空全部分析…", width="stretch"):
                st.session_state[KEY_CONFIRM_CLEAR_ANALYSIS] = True
                st.rerun()
            if right.button("只重跑态度分析…", width="stretch"):
                st.session_state[KEY_CONFIRM_RESET_ATTITUDE] = True
                st.rerun()


# --- cross table and lessons -------------------------------------------------


def _render_cross_table(ctx: AppContext) -> None:
    """Compact change × stance cross table — the first read on any corpus."""
    stats = ctx.recalculate()
    rows = []
    for target, item in stats.get("targets", {}).items():
        distribution = item.get("direction_distribution", {})
        rows.append({
            "改动对象": target,
            "相关评论": item.get("related_count", 0),
            "支持": distribution.get("支持改动方向", 0),
            "反对": distribution.get("反对改动方向", 0),
            "无法判断": distribution.get("无法判断", 0),
            "争议": item.get("controversy", "证据不足"),
        })
    if not rows:
        return
    frame = pd.DataFrame(rows)
    peak = int(frame["相关评论"].max() or 1) if len(frame) else 1
    support_peak = int(frame["支持"].max() or 1) if len(frame) else 1
    oppose_peak = int(frame["反对"].max() or 1) if len(frame) else 1
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={
            "相关评论": st.column_config.ProgressColumn(min_value=0, max_value=peak),
            "支持": st.column_config.ProgressColumn(min_value=0, max_value=support_peak),
            "反对": st.column_config.ProgressColumn(min_value=0, max_value=oppose_peak),
        },
    )
    judged = int(frame["支持"].sum() + frame["反对"].sum())
    total = int(frame["相关评论"].sum())
    if total:
        st.caption(
            f"方向可判定率 {judged / total:.0%}（{judged}/{total}）——"
            "该比例过低通常说明提示词输出契约失效，而不是玩家真的没有态度。"
        )


def _render_lessons(ctx: AppContext) -> None:
    """What the model has been told to learn from past human corrections."""
    summary = correction_summary(ctx.project)
    if not summary["复核记录"]:
        return
    rules = cached_rules(ctx.project)
    with st.expander(
        f"人工复核学习 · {summary['归纳规律']} 条规律 · {LESSON_SOURCE_LABEL['model' if rules else 'rules']}",
        expanded=False,
    ):
        cols = st.columns(3)
        cols[0].metric("复核记录", summary["复核记录"])
        cols[1].metric("修正字段", summary["修正字段"])
        cols[2].metric("归纳规律", summary["归纳规律"])
        if rules:
            st.caption("这些规则会注入后续每一批分析：")
            for rule in rules:
                st.write(f"- {rule}")
        else:
            st.caption("还没有生成模型归纳；规则归纳会在分析时自动注入。")
        refresh_col, clear_col = st.columns(2)
        if refresh_col.button(
            "重新归纳为规则",
            disabled=not ctx.settings.text_ready or not summary["归纳规律"],
            width="stretch",
        ):
            try:
                with st.spinner("正在把人工修正归纳为规则…"):
                    _block, source = lesson_block(ctx.project, ctx.client, refresh=True)
                st.success(f"已归纳（{LESSON_SOURCE_LABEL.get(source, source)}）。")
                ctx.store.save(ctx.project)
            except SiliconFlowError as exc:
                st.error(str(exc))
        if clear_col.button("清除已有规则", disabled=not rules, width="stretch"):
            clear_cache(ctx.project)
            ctx.store.save(ctx.project)
            st.rerun()


def render(ctx: AppContext) -> None:
    run = ctx.analysis_run
    if run:
        if run.get("stage") == STAGE_ATTITUDE:
            _advance_attitude_run(ctx, run)
        else:
            _advance_topic_run(ctx, run)
        return

    _render_result(ctx)
    _render_topic_stage(ctx)

    if analysis_service.topic_pending(ctx.project):
        _render_restart(ctx)
        return

    _render_attitude_stage(ctx)
    _render_topic_heat(ctx)
    _render_restart(ctx)

    if ctx.project.analyses:
        st.divider()
        _render_cross_table(ctx)
        _render_lessons(ctx)

        st.divider()
        render_review_panel(ctx)
