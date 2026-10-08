"""HTML fragments for the results page.

Streamlit's native widgets cannot express a compact stacked bar or a
quote-with-stance card, so those are rendered as small, escaped HTML strings.
Every value is passed through :func:`escape` before interpolation.
"""
from __future__ import annotations

from html import escape
from typing import Any

from ..core.models import CleanComment, CommentAnalysis
from .theme import CONTROVERSY_STYLE, STANCE_COLORS

QUOTE_LIMIT = 300


def stacked_bar(dist: dict[str, int], colors: dict[str, str], order: list[str]) -> str:
    total = sum(int(dist.get(key, 0)) for key in order)
    if not total:
        return '<div style="color:#94a3b8;font-size:12px;">暂无数据</div>'
    segments = "".join(
        f'<div style="width:{int(dist.get(key, 0)) / total * 100:.2f}%;background:{colors.get(key, "#94a3b8")};" '
        f'title="{escape(key)}：{int(dist.get(key, 0))} 条"></div>'
        for key in order
        if int(dist.get(key, 0))
    )
    legend = "　".join(
        f'<span style="color:{colors.get(key, "#64748b")}">■</span> {escape(key)} {dist[key]}'
        for key in order
        if dist.get(key)
    )
    return (
        f'<div style="display:flex;height:14px;border-radius:4px;overflow:hidden;border:1px solid #e2e8f0;'
        f'margin:4px 0 2px;background:#f8fafc;">{segments}</div>'
        f'<div style="font-size:11px;color:#475569;line-height:1.6;">{legend}</div>'
    )


def summary_line(item: dict[str, Any]) -> str:
    parts = [f"<b>{item.get('related_count', 0)}</b> 条相关评论"]
    support = item.get("direction_support", {})
    if support.get("rate") is not None:
        parts.append(
            f"方向支持率 <b>{support['rate']:.0%}</b>"
            f"（{support.get('numerator', 0)}/{support.get('denominator', 0)}）"
        )
    acceptance = item.get("acceptance_rate", {})
    if acceptance.get("rate") is not None:
        parts.append(f"接受率 <b>{acceptance['rate']:.0%}</b>")
    reasons = item.get("problem_reasons", {})
    if reasons:
        top_reason = max(reasons, key=reasons.get)
        parts.append(f"讨论焦点：{escape(top_reason)}（{reasons[top_reason]} 次）")
    return " · ".join(parts)


def target_card(item: dict[str, Any]) -> str:
    """One card per target.

    Takes the aggregate metrics dict rather than a :class:`PatchChange` because
    a target can cover several change rows — the statistics belong to the
    target, and the display layer should not have to re-derive that.
    """
    target = item.get("target", "未识别对象")
    controversy = item.get("controversy", "证据不足")
    badge_color, badge_bg = CONTROVERSY_STYLE.get(controversy, CONTROVERSY_STYLE["证据不足"])
    evidence_quality = item.get("evidence_quality", "证据不足")
    basis = escape("；".join(item.get("controversy_basis", [])) or "—")
    summary = escape("　".join(item.get("summaries", [])) or "（未提供改动摘要）")
    meta = " · ".join(filter(None, [item.get("category", ""), item.get("change_direction", "")]))
    return (
        '<div style="background:white;border:1px solid #dce2e9;border-radius:10px;padding:14px 18px 8px;margin:12px 0 4px;">'
        '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-weight:600;font-size:15px;color:#0f172a;">{escape(target)}</span>'
        f'<span style="background:{badge_bg};color:{badge_color};border:1px solid {badge_color};'
        f'border-radius:12px;padding:1px 10px;font-size:12px;">{controversy}争议</span>'
        f'<span style="background:#f1f5f9;color:#475569;border-radius:12px;padding:1px 10px;font-size:12px;">证据质量 {evidence_quality}</span>'
        f'<span style="color:#64748b;font-size:12px;margin-left:auto;">{escape(meta)}</span>'
        "</div>"
        f'<div style="color:#334155;font-size:13px;margin:8px 0 4px;">{summary}</div>'
        f'<div style="color:#0f172a;font-size:13px;margin:4px 0;">{summary_line(item)}</div>'
        f'<div style="color:#64748b;font-size:11px;margin-bottom:4px;">争议依据：{basis}</div>'
        "</div>"
    )


def representative_quote(comment: CleanComment, analysis: CommentAnalysis | None) -> str:
    stance = analysis.overall_stance if analysis else ""
    stance_color = STANCE_COLORS.get(stance, "#64748b")
    quote = escape(comment.cleaned_content)
    quote = quote if len(quote) <= QUOTE_LIMIT else quote[:QUOTE_LIMIT] + "…"
    position_label = f"CSV 第 {comment.local_index} 行"
    stance_html = f' · <span style="color:{stance_color};font-weight:600;">{escape(stance)}</span>' if stance else ""
    return (
        '<div style="border-left:3px solid #cbd5e1;background:#f8fafc;padding:8px 12px;margin:6px 0;'
        'font-size:13px;color:#1f2a37;border-radius:0 6px 6px 0;">'
        f'<div style="color:#64748b;font-size:11px;margin-bottom:4px;">{escape(comment.comment_id)} · '
        f"{escape(comment.platform)} · {escape(position_label)}{stance_html}</div>"
        f"{quote}</div>"
    )


def insight_box(insight: dict[str, Any]) -> str:
    return (
        '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;'
        'margin:8px 0;font-size:13px;color:#1e3a5f;">'
        f'<b>下一版本验证方向：{escape(insight.get("validation_direction", ""))}</b><br/>'
        f'观察：{escape(insight.get("observation", ""))}<br/>'
        f'局限：{escape(insight.get("limitations", ""))}</div>'
    )
