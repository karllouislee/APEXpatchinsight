"""Step 2 — import comment CSVs and clean them before analysis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core.bilibili_importer import BilibiliImportError
from ...core.community_aliases import load_aliases
from ...services import comment_service
from ..state import AppContext, KEY_CONFIRM_CLEAR

COMMENT_COLUMNS = [
    "comment_id", "原文", "平台", "来源文件", "发布时间", "回复",
    "回复上下文", "点赞", "人工关键词", "有效", "无效原因", "重复于", "疑似重复",
]
DISABLED_COLUMNS = [
    "comment_id", "平台", "来源文件", "发布时间", "回复", "点赞",
    "无效原因", "重复于", "疑似重复",
]


def _render_import(ctx: AppContext) -> None:
    csv_file = st.file_uploader("选择 B站评论 CSV", type=["csv"], key="bilibili_comment_csv")
    source_url = st.text_input(
        "来源页面（可选，仅允许 bilibili.com）",
        placeholder="https://www.bilibili.com/video/BV...",
        key="bilibili_source_url",
    )
    settings_col, limit_col = st.columns([1, 1])
    authorized = settings_col.checkbox(
        "我确认有权处理该评论数据", key="bilibili_authorized"
    )
    row_limit = limit_col.number_input(
        "本次最多导入", min_value=20, max_value=5000, value=200, step=100, key="bilibili_row_limit",
    )

    if st.button(
        "匿名化导入",
        disabled=csv_file is None or not authorized,
        type="primary",
        width="stretch",
    ):
        _run_import(ctx, csv_file, source_url, int(row_limit))

    with st.expander("导入说明", expanded=False):
        st.markdown(
            "支持 **bilibili-comment-crawler** 与新版 Edge 扩展导出的 CSV。"
            "只保留正文、点赞、时间与回复关系；用户名、UID、头像、IP属地等不会写入项目。"
        )


def _run_import(ctx: AppContext, csv_file, source_url: str, row_limit: int) -> None:
    try:
        imported = comment_service.import_bilibili_csv(
            csv_file.getvalue(), csv_file.name, row_limit=row_limit, source_url=source_url
        )
    except BilibiliImportError as exc:
        st.error(f"导入失败：{exc}")
        return

    fresh = comment_service.new_comments_only(ctx.raw_models, imported.comments)
    if not fresh:
        st.info("该 CSV 中的评论已经导入，无需重复处理。")
        return

    if comment_service.demote_demo_project(ctx.project):
        ctx.set_raw_models([])

    previous = {comment.comment_id: comment for comment in ctx.project.comments}
    combined = comment_service.merge_raw_comments(ctx.raw_models, fresh)
    ctx.set_raw_models(combined)
    ctx.project.comments = comment_service.rebuild_clean_comments(combined, previous, preserve_text=True)
    ctx.persist_comments()
    ctx.store.save(ctx.project)

    summary = f"已导入 {len(fresh)} 条评论"
    if imported.skipped_rows:
        summary += f"，跳过 {imported.skipped_rows} 条空内容"
    if imported.truncated:
        summary += f"，已按上限截取 {row_limit} 条"
    st.success(summary + "。")
    st.rerun()


def _rows(project) -> list[dict]:
    return [{
        "comment_id": c.comment_id,
        "原文": c.cleaned_content,
        "平台": c.platform,
        "来源文件": c.source_file,
        "发布时间": c.published_at,
        "回复": "是" if c.is_reply else "否",
        "回复上下文": c.reply_context or "",
        "点赞": c.likes,
        "人工关键词": "，".join(c.manual_keywords),
        "有效": c.is_valid,
        "无效原因": c.invalid_reason,
        "重复于": c.duplicate_of,
        "疑似重复": c.suspected_duplicate,
    } for c in project.comments]


def _render_table(ctx: AppContext) -> None:
    edited = st.data_editor(
        pd.DataFrame(_rows(ctx.project), columns=COMMENT_COLUMNS),
        width="stretch",
        hide_index=True,
        column_config={
            "原文": st.column_config.TextColumn(width="large"),
            "回复上下文": st.column_config.TextColumn(width="medium"),
            "人工关键词": st.column_config.TextColumn(
                help="人工补充黑称、缩写、反讽或模板标签；用逗号分隔。"
            ),
            "有效": st.column_config.CheckboxColumn(),
        },
        disabled=DISABLED_COLUMNS,
    )

    left, right = st.columns([1, 1])
    with left:
        if st.button("保存人工修正", width="stretch"):
            ctx.project.comments = comment_service.apply_comment_corrections(
                ctx.project.comments, _iter_rows(edited)
            )
            ctx.persist_comments()
            st.success("已保存并重新执行去重。")
    with right:
        _render_clear_controls(ctx)


def _render_clear_controls(ctx: AppContext) -> None:
    if st.session_state.get(KEY_CONFIRM_CLEAR):
        if st.button("再次点击确认清空全部评论", type="primary", width="stretch"):
            ctx.clear_comments()
            st.session_state[KEY_CONFIRM_CLEAR] = False
            st.success("评论库已清空。")
            st.rerun()
    elif st.button("清空评论库…", width="stretch"):
        st.session_state[KEY_CONFIRM_CLEAR] = True
        st.rerun()


def _iter_rows(frame: pd.DataFrame):
    for _, row in frame.iterrows():
        yield row.to_dict()


def render(ctx: AppContext) -> None:
    restored = ctx.consume_restore_notice()
    if restored:
        st.info(f"已恢复上次会话的 {restored} 条评论，可继续追加导入。")

    if not ctx.project.comments:
        _render_import(ctx)
        st.info("还没有评论。导入 CSV 后可进入「分析评论」，或先加载演示项目体验完整流程。")
        return

    candidates = ctx.analysis_candidates
    source_files = comment_service.source_file_count(ctx.project.comments)
    stats = st.columns(4)
    stats[0].metric("评论总数", len(ctx.project.comments))
    stats[1].metric("有效评论", len(candidates))
    stats[2].metric("CSV 来源", source_files)
    stats[3].metric("社区词典", f"{load_aliases(ctx.settings.workspace_dir).entry_count} 项")

    left, right = st.columns([1, 2], gap="large")
    with left:
        _render_import(ctx)
    with right:
        _render_table(ctx)
