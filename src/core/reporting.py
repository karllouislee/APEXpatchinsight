from __future__ import annotations

import csv
import io
import json
from typing import Any

from .models import Project
from .validation import validation_metrics

# 参考评论最多带几条：报告要短，摘要有说服力就够。
SUPPORT_COMMENT_LIMIT = 3
SUPPORT_QUOTE_LIMIT = 160
DETERMINATE_DIRECTIONS = {"支持改动方向", "反对改动方向", "对方向没有明确态度"}


def generate_markdown(project: Project, stats: dict[str, Any]) -> str:
    lines = [
        f"# {project.name}", "",
        "> 演示数据" if project.is_demo else "> 数据来源：本项目导入的社区评论。",
        "", "## 数据概览", "",
        f"- 有效评论：{stats.get('valid_comment_count', 0)}",
        f"- 已分析评论：{stats.get('analyzed_comment_count', 0)}",
        f"- 成功映射改动：{stats.get('matched_comment_count', 0)}",
        "", "## 改动反馈", "",
    ]
    for target, metrics in stats.get("targets", {}).items():
        heat = metrics.get("discussion_heat", {})
        support = metrics.get("direction_support", {})
        lines.extend([
            f"### {target}", "",
            "官方改动：" + ("；".join(metrics.get("summaries", [])) or "（未提供摘要）"), "",
            f"讨论热度：{heat.get('numerator', 0)}/{heat.get('denominator', 0)} ({_pct(heat.get('rate'))})",
            f"方向支持率：{support.get('numerator', 0)}/{support.get('denominator', 0)} ({_pct(support.get('rate'))})",
            f"争议程度：{metrics.get('controversy', '证据不足')}；依据：{'；'.join(metrics.get('controversy_basis', []))}",
            f"证据质量：{metrics.get('evidence_quality', '证据不足')}", "",
        ])
        insight = project.insights.get(target) if project.insights else None
        if insight:
            lines.extend([f"验证方向：{insight.get('validation_direction', '')}", f"局限：{insight.get('limitations', '')}", ""])
    return "\n".join(lines)


def _verdict_phrase(support: int, oppose: int) -> str:
    """One plain sentence for where the determinate opinions land."""
    judged = support + oppose
    if not judged:
        return "方向结论无法确定"
    share = support / judged
    if share >= 0.7:
        return "玩家普遍支持该改动方向"
    if share <= 0.3:
        return "玩家普遍反对该改动方向"
    return "玩家对该改动方向意见分裂"


def _support_comments(
    project: Project,
    representative_ids: list[str],
    analyses_by_id: dict[str, Any],
) -> list[tuple[Any, Any]]:
    """Up to three reference comments, determinate directions first."""
    comment_lookup = {comment.comment_id: comment for comment in project.comments}
    determinate: list[tuple[Any, Any]] = []
    fallback: list[tuple[Any, Any]] = []
    for cid in representative_ids:
        comment = comment_lookup.get(cid)
        if comment is None:
            continue
        analysis = analyses_by_id.get(cid)
        pair = (comment, analysis)
        if analysis and analysis.direction_attitude in DETERMINATE_DIRECTIONS:
            determinate.append(pair)
        else:
            fallback.append(pair)
    return (determinate + fallback)[:SUPPORT_COMMENT_LIMIT]


def analysis_results_markdown(project: Project, stats: dict[str, Any]) -> str:
    """Export the analysis results of the determinate change items.

    「确定条目」= targets with at least one determinate direction verdict.
    Each item gets its verdict, the rates behind it, and up to three
    reference comments as supporting evidence. Targets without any
    determinate direction are listed at the end, one line each.
    """
    analyses_by_id = {analysis.comment_id: analysis for analysis in project.analyses}
    targets = stats.get("targets", {})
    determinate = {
        target: item
        for target, item in targets.items()
        if item.get("direction_support", {}).get("denominator", 0) > 0
    }
    pending = {target: item for target, item in targets.items() if target not in determinate}

    lines = [
        f"# {project.name} · 分析结果",
        "",
        "> 演示数据" if project.is_demo
        else "> 数据来源：本项目导入的社区评论。",
        "",
        f"共 {len(targets)} 个改动对象，其中 {len(determinate)} 个方向结论确定，"
        f"覆盖 {sum(item.get('related_count', 0) for item in determinate.values())} 条相关评论。",
        "",
    ]

    for target, item in sorted(determinate.items(), key=lambda pair: -pair[1].get("related_count", 0)):
        support = item.get("direction_support", {})
        acceptance = item.get("acceptance_rate", {})
        verdict = _verdict_phrase(support.get("numerator", 0), support.get("denominator", 0) - support.get("numerator", 0))
        lines.extend([
            f"## {target}",
            "",
            "官方改动：" + ("；".join(item.get("summaries", [])) or "（未提供摘要）"),
            f"相关评论：{item.get('related_count', 0)} 条 · 争议程度：{item.get('controversy', '证据不足')} · "
            f"证据质量：{item.get('evidence_quality', '证据不足')}",
            "",
            f"**结论：{verdict}。**"
            f"方向支持率 {support.get('numerator', 0)}/{support.get('denominator', 0)}（{_pct(support.get('rate'))}，明确观点中支持占比）；"
            f"接受率 {acceptance.get('numerator', 0)}/{acceptance.get('denominator', 0)}"
            f"（{_pct(acceptance.get('rate'))}，全部相关评论中明确支持占比）。",
            "",
        ])

        pairs = _support_comments(project, item.get("representative_comment_ids", []), analyses_by_id)
        if pairs:
            lines.append("参考评论：")
            lines.append("")
            for comment, analysis in pairs:
                quote = comment.cleaned_content
                if len(quote) > SUPPORT_QUOTE_LIMIT:
                    quote = quote[:SUPPORT_QUOTE_LIMIT] + "…"
                direction = analysis.direction_attitude if analysis else "未分析"
                lines.append(f"> {quote}")
                lines.append(f">")
                lines.append(f"> —— {comment.platform} · 方向：{direction}")
                lines.append("")
        else:
            lines.extend(["（没有可引用的相关评论。）", ""])

    if pending:
        lines.extend([
            "## 方向结论未确定的条目", "",
        ])
        for target, item in pending.items():
            lines.append(
                f"- {target}：{item.get('related_count', 0)} 条相关评论，方向均无法判断，不给出结论。"
            )
        lines.append("")

    lines.extend([
        "## 样本局限", "",
        "评论文件与截图样本存在平台构成、导出范围、主动选择、上下文缺失和重复曝光偏差；评论频率不能解释为问题严重度。",
        "",
    ])
    return "\n".join(lines)


def analyses_csv(project: Project) -> str:
    comment_lookup = {comment.comment_id: comment for comment in project.comments}
    rows = []
    for analysis in project.analyses:
        comment = comment_lookup.get(analysis.comment_id)
        rows.append({
            "comment_id": analysis.comment_id, "content": comment.cleaned_content if comment else "",
            "platform": comment.platform if comment else "", "来源文件": comment.source_file if comment else "",
            "source_type": comment.source_type if comment else "", "source_url": comment.source_url if comment else "",
            "published_at": comment.published_at if comment else "", "source_comment_key": comment.source_comment_key if comment else "",
            **analysis.model_dump(mode="json"),
        })
    return _csv(rows)


def matrix_csv(project: Project, stats: dict[str, Any]) -> str:
    rows = []
    for target, metrics in stats.get("targets", {}).items():
        rows.append({"target": target, "改动条目": " | ".join(metrics.get("change_keys", [])), **metrics})
    return _csv(rows)


def validations_csv(project: Project) -> str:
    return _csv([record.model_dump(mode="json") for record in project.validations])


def project_json(project: Project) -> str:
    return json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    flat = [{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in rows]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in flat for key in row)))
    writer.writeheader()
    writer.writerows(flat)
    return stream.getvalue()


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"
