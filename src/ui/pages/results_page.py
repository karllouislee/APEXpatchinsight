"""Step 4 — the change feedback matrix, evidence cards, and exports."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core.analytics import format_rate
from ...services import analysis_service
from ..charts import insight_box, representative_quote, stacked_bar, target_card
from ..components.export_panel import render_export_panel
from ..state import AppContext, KEY_VALIDATION_SAMPLE
from ..theme import (
    CONTROVERSY_LEVELS,
    CONTROVERSY_ORDER,
    DIRECTION_COLORS,
    DIRECTION_ORDER,
    INTENSITY_COLORS,
    INTENSITY_ORDER,
    ROOT_COLORS,
    ROOT_ORDER,
)

SORT_MODES = ["相关评论数", "争议程度", "方向支持率"]


def _render_headline(ctx: AppContext, stats: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("有效评论", stats["valid_comment_count"])
    cols[1].metric(
        "改动匹配率",
        format_rate(stats["change_match_rate"]),
        f"{stats['matched_comment_count']}/{stats['analyzed_comment_count']}",
    )
    cols[2].metric("高争议改动", stats["high_controversy_count"])
    cols[3].metric("待人工复核", len(ctx.project.reviews))


def _render_matrix(ctx: AppContext, stats: dict) -> None:
    matrix = []
    for target, item in stats["targets"].items():
        matrix.append({
            "改动对象": target,
            "改动条目": len(item.get("change_keys", [])),
            "相关评论": item.get("related_count", 0),
            "方向支持率": format_rate(item.get("direction_support", {})),
            "接受率": format_rate(item.get("acceptance_rate", {})),
            "争议": item.get("controversy", "证据不足"),
            "证据质量": item.get("evidence_quality", "证据不足"),
        })
    matrix.sort(key=lambda row: row["相关评论"], reverse=True)
    frame = pd.DataFrame(matrix)
    peak = int(frame["相关评论"].max() or 1) if len(frame) else 1
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={"相关评论": st.column_config.ProgressColumn(min_value=0, max_value=peak)},
    )


def _sort_key(sort_mode: str):
    support_rate = lambda item: item.get("direction_support", {}).get("rate") or 0
    if sort_mode == "争议程度":
        return lambda pair: CONTROVERSY_ORDER.get(pair[1].get("controversy", "证据不足"), 3)
    if sort_mode == "方向支持率":
        return lambda pair: -support_rate(pair[1])
    return lambda pair: pair[1].get("related_count", 0)


def _render_cards(ctx: AppContext, stats: dict) -> None:
    filter_col, sort_col = st.columns([3, 1])
    levels = filter_col.multiselect(
        "争议级别", CONTROVERSY_LEVELS, default=list(CONTROVERSY_LEVELS), label_visibility="collapsed"
    )
    sort_mode = sort_col.selectbox("排序", SORT_MODES, label_visibility="collapsed")

    comment_lookup = {c.comment_id: c for c in ctx.project.comments}
    analysis_by_id = {a.comment_id: a for a in ctx.project.analyses}
    visible = [
        (target, item)
        for target, item in stats["targets"].items()
        if item.get("controversy", "证据不足") in levels
    ]
    visible.sort(key=_sort_key(sort_mode))
    if not visible:
        st.caption("当前筛选条件下没有改动卡片。")

    for target, item in visible:
        st.markdown(target_card(item), unsafe_allow_html=True)
        dist1, dist2, dist3 = st.columns(3)
        with dist1:
            st.caption("方向态度")
            st.markdown(stacked_bar(item.get("direction_distribution", {}), DIRECTION_COLORS, DIRECTION_ORDER), unsafe_allow_html=True)
        with dist2:
            st.caption("力度态度")
            st.markdown(stacked_bar(item.get("intensity_distribution", {}), INTENSITY_COLORS, INTENSITY_ORDER), unsafe_allow_html=True)
        with dist3:
            st.caption("原问题状态")
            st.markdown(stacked_bar(item.get("root_distribution", {}), ROOT_COLORS, ROOT_ORDER), unsafe_allow_html=True)

        representative_ids = item.get("representative_comment_ids", [])
        if representative_ids:
            st.caption("代表性评论")
            for cid in representative_ids:
                comment = comment_lookup.get(cid)
                if comment is None:
                    continue
                st.markdown(representative_quote(comment, analysis_by_id.get(cid)), unsafe_allow_html=True)

        insight = (ctx.project.insights or {}).get(target, {})
        if insight:
            st.markdown(insight_box(insight), unsafe_allow_html=True)


def _render_distributions(stats: dict) -> None:
    left, right = st.columns(2)
    left.caption("问题类型分布")
    left.bar_chart(pd.Series(stats["problem_domain_distribution"]))
    right.caption("平台样本分布")
    right.bar_chart(pd.Series(stats["platform_distribution"]))


def _render_insights(ctx: AppContext, stats: dict) -> None:
    project = ctx.project
    left, right = st.columns([1, 1])
    if left.button("按规则生成验证方向", width="stretch"):
        project.insights = analysis_service.deterministic_insight_payload(project, stats)
        st.success("已从程序统计生成受限验证方向。")
    if right.button("用文本模型生成方向", disabled=not ctx.settings.text_ready, width="stretch"):
        try:
            project.insights = analysis_service.ai_insight_payload(project, stats, ctx.client)
            st.success("方向总结已生成；程序统计未被模型修改。")
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the user
            st.error(str(exc))

    for target, insight in (project.insights or {}).items():
        if not insight:
            continue
        with st.expander(f"{target} · {insight.get('validation_direction')}", expanded=False):
            st.write("观察：", insight.get("observation"))
            st.write("证据：", ", ".join(insight.get("evidence_comment_ids", [])) or "无")
            st.write("推断：", insight.get("inference"))
            st.write("置信度：", insight.get("confidence"))
            st.write("局限：", insight.get("limitations"))


def _render_validation(ctx: AppContext) -> None:
    project = ctx.project
    size = st.radio("随机抽样量", [10, 30, 50], horizontal=True, label_visibility="collapsed")
    if st.button("生成随机验证样本"):
        ctx.validation_sample = analysis_service.sample_validation_ids(project.comments, size)

    if ctx.validation_sample:
        cid = st.selectbox("样本评论", ctx.validation_sample, label_visibility="collapsed")
        comment = next((c for c in project.comments if c.comment_id == cid), None)
        if comment is None:
            st.warning("该样本评论已不存在。")
            ctx.validation_sample = [item for item in ctx.validation_sample if item != cid]
            return
        st.write(comment.cleaned_content)
        values = {
            key: st.selectbox(label, ["未判断", "认可", "不认可"], key=f"val-{cid}-{key}")
            for key, label in VALIDATION_LABELS.items()
        }
        if st.button("保存该条验证"):
            encoded = {key: None if value == "未判断" else value == "认可" for key, value in values.items()}
            analysis_service.save_validation(project, cid, encoded)
            st.success("验证记录已保存；未判断项不进入分母。")

    st.dataframe(pd.DataFrame(analysis_service.validation_rows(project)), width="stretch", hide_index=True)


VALIDATION_LABELS = {
    "text_accepted": "原文认可",
    "mapping_accepted": "改动映射认可",
    "attitude_accepted": "态度分类认可",
    "domain_accepted": "问题类型认可",
    "evidence_traceable": "原文证据可追溯",
    "dedup_accepted": "去重结果认可",
}


def render(ctx: AppContext) -> None:
    stats = ctx.recalculate()

    if not ctx.project.changes:
        st.info("还没有改动清单，请先完成「提取更新内容」。")
        return
    if not stats["analyzed_comment_count"]:
        st.info("还没有分析结果，请先完成「分析评论」。")
        return

    _render_headline(ctx, stats)
    _render_matrix(ctx, stats)
    _render_cards(ctx, stats)

    with st.expander("方向总结", expanded=False):
        _render_insights(ctx, stats)
    with st.expander("抽样验证", expanded=False):
        _render_validation(ctx)
    with st.expander("导出", expanded=False):
        render_export_panel(ctx, stats)
    _render_distributions(stats)
