"""Export panel — every artefact the project can hand off."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ...core.reporting import (
    analyses_csv,
    analysis_results_markdown,
    generate_markdown,
    matrix_csv,
    project_json,
    validations_csv,
)
from ..state import AppContext


def render_export_panel(ctx: AppContext, stats: dict[str, Any]) -> None:
    project = ctx.project
    st.caption("导出内容不含 API Key；CSV 与 JSON 保留 comment_id、来源文件与行号。")
    left, right = st.columns([1, 1])
    with left:
        st.download_button(
            "分析结果报告（确定条目）", analysis_results_markdown(project, stats),
            "analysis_results.md", "text/markdown",
            help="只导出方向结论确定的改动对象：结论、支持率/接受率，以及最多 3 条参考评论作支撑。",
            width="stretch",
        )
        st.download_button("Markdown 报告", generate_markdown(project, stats), "apex_patch_report.md", "text/markdown", width="stretch")
        st.download_button("评论分析 CSV", analyses_csv(project), "comment_analysis.csv", "text/csv", width="stretch")
        st.download_button("改动矩阵 CSV", matrix_csv(project, stats), "change_matrix.csv", "text/csv", width="stretch")
    with right:
        st.download_button("人工验证 CSV", validations_csv(project), "validation_results.csv", "text/csv", width="stretch")
        st.download_button("完整项目 JSON", project_json(project), "apex_patch_project.json", "application/json", width="stretch")
