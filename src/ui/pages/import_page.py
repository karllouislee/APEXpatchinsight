"""Step 1 — pull the official notes and shape the confirmed change list."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core.models import PatchChange
from ...integrations.ea_fetcher import FetchError
from ...integrations.siliconflow_client import SiliconFlowError
from ...services import article_service, change_history
from ...services.demo_data import build_demo_project
from ..state import AppContext

CHANGE_COLUMNS = [
    "target", "category", "change_direction", "change_summary",
    "design_goal", "aliases", "parse_confidence", "confirmed", "删除", "ability_or_system",
]


def _render_sources(ctx: AppContext) -> None:
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.caption("自动获取")
        if st.button("查找最新 Designer’s Notes", width="stretch"):
            try:
                with st.spinner("正在低频访问 EA 官方新闻页…"):
                    ctx.project.article = article_service.import_latest_article()
                    ctx.project.is_demo = False
                    ctx.project.demo_disclaimer = ""
                st.success("已获取官方文章。")
            except (FetchError, ValueError) as exc:
                st.error(str(exc))

        manual_url = st.text_input("或粘贴官方文章 URL", placeholder="https://www.ea.com/...")
        if st.button("导入该 URL", width="stretch", disabled=not manual_url):
            try:
                with st.spinner("正在获取并解析…"):
                    ctx.project.article = article_service.import_article_url(manual_url)
                    ctx.project.is_demo = False
                    ctx.project.demo_disclaimer = ""
                st.success("文章导入成功。")
            except (FetchError, ValueError) as exc:
                st.error(str(exc))

    with right:
        st.caption("或先体验")
        if st.button("加载内置演示项目", type="primary", width="stretch"):
            ctx.replace_project(build_demo_project(ctx.settings.demo_dir))
            st.session_state.raw_comments = []
            st.success("已加载虚构演示项目。")
            st.rerun()
        st.caption("演示项目包含完整改动、评论与分析结果，无需 API Key 即可浏览全流程。")


def _render_article(ctx: AppContext) -> None:
    article = ctx.project.article
    st.caption(f"{article.title} · {article.published_at or '发布日期未识别'}")
    with st.expander("查看解析后的章节", expanded=False):
        for section in article.sections:
            if section.get("section_type") == "ability":
                st.markdown(f"&nbsp;&nbsp;&nbsp;└ **{section.get('heading', '技能')}**", unsafe_allow_html=True)
            else:
                st.markdown(f"**{section.get('heading', '正文')}**")
            if section.get("parent_heading"):
                st.caption(f"所属英雄：{section['parent_heading']}")
            for item in [*section.get("paragraphs", []), *section.get("items", [])]:
                st.write(item)


def _render_editor(ctx: AppContext) -> None:
    changes = ctx.project.changes
    if not changes:
        st.info("还没有改动清单。导入文章后可结构化，或直接手动新增。")
    edited = st.data_editor(
        pd.DataFrame(_rows(changes), columns=CHANGE_COLUMNS),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "parse_confidence": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.01),
            "confirmed": st.column_config.CheckboxColumn(),
            "删除": st.column_config.CheckboxColumn(),
        },
    )

    save_col, confirm_col = st.columns([1, 1])
    with save_col:
        if st.button("保存改动清单", width="stretch"):
            ctx.project.changes = article_service.apply_editor_rows(changes, _iter_rows(edited))
            st.success("已保存。改动以目标名称标识，重名条目会按目标聚合统计。")
    with confirm_col:
        if st.button("确认全部改动", type="primary", width="stretch", disabled=not ctx.project.changes):
            article_service.confirm_all(ctx.project.changes)
            st.success("全部改动已确认，可进入评论收集。")

    if st.button("把目标名换成中文", disabled=not ctx.project.changes, width="stretch"):
        changes_now = ctx.project.changes
        before = {change.target for change in changes_now}
        article_service.localize_targets(changes_now, ctx.alias_dict)
        renamed = sum(1 for change in changes_now if change.target not in before)
        st.success(f"已转换 {renamed} 个目标名；英文名保留为别名，已有映射不受影响。" if renamed else "没有可转换的目标名。")

    with st.expander("合并重复改动 / 历史清单", expanded=False):
        merge_ids = st.multiselect("选择要合并的目标（保留第一个）", sorted({c.target for c in ctx.project.changes}))
        if st.button("合并所选", disabled=len(merge_ids) < 2):
            ctx.project.changes = article_service.merge_changes(ctx.project.changes, merge_ids)
            st.success("已合并；保存清单后生效。")
        _render_history(ctx)


def _rows(changes: list[PatchChange]) -> list[dict]:
    return [{
        "target": c.target,
        "category": c.category,
        "change_direction": c.change_direction,
        "change_summary": c.change_summary,
        "design_goal": c.design_goal,
        "aliases": " | ".join(c.aliases),
        "parse_confidence": c.parse_confidence,
        "confirmed": c.confirmed,
        "删除": False,
        "ability_or_system": c.ability_or_system,
    } for c in changes]


def _render_history(ctx: AppContext) -> None:
    name = st.text_input(
        "历史名称",
        value=ctx.project.article.title if ctx.project.article else "版本改动",
        key="change_history_name",
    )
    if st.button("保存到历史", disabled=not ctx.project.changes):
        path = change_history.save_change_history(name, ctx.project.changes)
        st.success(f"已保存：{path}")

    files = change_history.list_change_history()
    if not files:
        st.caption("尚未保存历史清单。")
        return
    selected = st.selectbox("选择历史清单", files, format_func=lambda item: item.stem)
    if st.button("加载所选历史"):
        ctx.project.changes = change_history.load_change_history(selected)
        st.success(f"已加载 {len(ctx.project.changes)} 项历史改动。")
        st.rerun()


def _iter_rows(frame: pd.DataFrame):
    for _, row in frame.iterrows():
        yield row.to_dict()


def _render_structuring(ctx: AppContext) -> None:
    if not ctx.project.article:
        return
    if st.button(
        "AI 总结并分类版本改动",
        disabled=not ctx.settings.text_ready,
        type="primary",
        width="stretch",
    ):
        settings = ctx.settings
        operation = "版本改动总结分类"
        ticket = ctx.monitor.start(operation, model=settings.text_model)
        if ticket is None:
            st.error("API 调用已被会话限额阻止，请查看侧边栏控制台。")
            return
        try:
            with st.spinner("AI 正在合并重复描述、识别英雄与技能并分类…"):
                ctx.project.changes = article_service.structure_with_model(ctx.project.article, ctx.client, ctx.alias_dict)
            ctx.monitor.finish(ticket, operation, "成功", f"生成 {len(ctx.project.changes)} 项改动", settings.text_model)
            st.success(f"已总结为 {len(ctx.project.changes)} 项改动，请人工确认。")
        except SiliconFlowError as exc:
            ctx.monitor.finish(ticket, operation, "失败", str(exc), settings.text_model)
            st.error(str(exc))


def render(ctx: AppContext) -> None:
    confirmed = sum(1 for change in ctx.project.changes if change.confirmed)
    metrics = st.columns(3)
    metrics[0].metric("改动条目", len(ctx.project.changes))
    metrics[1].metric("已确认", f"{confirmed}/{len(ctx.project.changes)}")
    metrics[2].metric("文章", "已导入" if ctx.project.article else "未导入")

    if not ctx.project.article and not ctx.project.changes:
        _render_sources(ctx)
        return

    left, right = st.columns([1, 2], gap="large")
    with left:
        _render_sources(ctx)
        if ctx.project.article:
            _render_article(ctx)
            _render_structuring(ctx)
        if not ctx.settings.text_ready:
            st.caption("AI 结构化需要 API Key；也可直接在右侧表格手动维护改动。")
    with right:
        _render_editor(ctx)
