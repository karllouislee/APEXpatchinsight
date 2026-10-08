from __future__ import annotations

from collections import Counter
from typing import Any

from .models import CleanComment, CommentAnalysis, PatchChange

QUALITY_WEIGHT = {"高": 1.0, "中": 0.6, "低": 0.2}


def safe_ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": (numerator / denominator if denominator else None)}


def target_groups(changes: list[PatchChange]) -> dict[str, list[PatchChange]]:
    """Group the change list by the name the community actually uses.

    Players say "寻血猎犬被砍了", not "CHG-019 被砍了" — and they rarely name
    the ability, so a comment about a legend maps to that legend, not to one
    arbitrary ability row. Grouping by target is therefore both what the model
    can reliably determine and what stops one comment from being counted once
    per ability row.
    """
    groups: dict[str, list[PatchChange]] = {}
    for change in changes:
        key = (change.target or "").strip() or "未识别对象"
        groups.setdefault(key, []).append(change)
    return groups


def change_terms(change: PatchChange) -> set[str]:
    """Every surface form a stored analysis might carry for one change row."""
    candidates = [(change.target or "").strip(), (change.ability_or_system or "").strip()]
    candidates.extend(str(term or "").strip() for term in change.aliases)
    return {term for term in candidates if term}


def group_terms(group: list[PatchChange]) -> set[str]:
    """Every surface form that identifies any row of a target group."""
    terms: set[str] = set()
    for change in group:
        terms |= change_terms(change)
    return terms


def _is_related(analysis: CommentAnalysis, terms: set[str]) -> bool:
    if (analysis.primary_target or "").strip() in terms:
        return True
    return any((term or "").strip() in terms for term in analysis.secondary_targets)


def aggregate(changes: list[PatchChange], comments: list[CleanComment], analyses: list[CommentAnalysis]) -> dict[str, Any]:
    valid_comments = [c for c in comments if c.is_valid and not c.duplicate_of]
    analysis_by_id = {a.comment_id: a for a in analyses}
    valid_analyses = [analysis_by_id[c.comment_id] for c in valid_comments if c.comment_id in analysis_by_id]
    matched = [a for a in valid_analyses if a.primary_target]
    global_domains = Counter(a.problem_domain for a in valid_analyses)
    platform_counts = Counter(c.platform for c in valid_comments)
    by_target: dict[str, Any] = {}
    for target, group in target_groups(changes).items():
        terms = group_terms(group)
        related = [a for a in valid_analyses if _is_related(a, terms)]
        related_ids = {a.comment_id for a in related}
        related_comments = [c for c in valid_comments if c.comment_id in related_ids]
        direction = Counter(a.direction_attitude for a in related)
        intensity = Counter(a.intensity_attitude for a in related)
        stance = Counter(a.overall_stance for a in related)
        root = Counter(a.root_issue_status for a in related)
        support = direction["支持改动方向"]
        oppose = direction["反对改动方向"]
        unresolved = root["原问题仍未解决"]
        root_judged = sum(v for k, v in root.items() if k != "无法判断")
        platforms = Counter(c.platform for c in related_comments)
        quality_average = sum(QUALITY_WEIGHT[a.information_quality] for a in related) / len(related) if related else None
        quality = "证据不足" if quality_average is None else "高" if quality_average >= 0.75 else "中" if quality_average >= 0.45 else "低"
        controversy, basis = controversy_level(related, platforms)
        reasons = Counter(reason for a in related for reason in a.problem_reason)
        by_target[target] = {
            "target": target,
            "change_keys": [change.change_key for change in group],
            "summaries": [change.change_summary for change in group if change.change_summary],
            "category": group[0].category,
            "change_direction": " / ".join(sorted({change.change_direction for change in group if change.change_direction})),
            "related_count": len(related),
            "discussion_heat": safe_ratio(len(related), len(valid_analyses)),
            "direction_support": safe_ratio(support, support + oppose),
            "direction_oppose": safe_ratio(oppose, support + oppose),
            # 接受率：明确支持的评论占全部相关评论的比例。原问题状态来自改动
            # 设计而非评论内容，「未解决率」撑不起判断，改用这个。
            "acceptance_rate": safe_ratio(support, len(related)),
            "intensity_insufficient": safe_ratio(intensity["力度不足"], len(related)),
            "intensity_excessive": safe_ratio(intensity["力度过大"], len(related)),
            "root_unresolved": safe_ratio(unresolved, root_judged),
            "new_problem_rate": safe_ratio(root["产生了新问题"], root_judged),
            "controversy": controversy,
            "controversy_basis": basis,
            "evidence_quality": quality,
            "evidence_quality_average": quality_average,
            "direction_distribution": dict(direction),
            "intensity_distribution": dict(intensity),
            "stance_distribution": dict(stance),
            "root_distribution": dict(root),
            "platform_distribution": dict(platforms),
            "problem_reasons": dict(reasons),
            "representative_comment_ids": [a.comment_id for a in sorted(related, key=lambda x: (QUALITY_WEIGHT[x.information_quality], x.analysis_confidence), reverse=True)[:5]],
        }
    return {
        "valid_comment_count": len(valid_comments),
        "analyzed_comment_count": len(valid_analyses),
        "matched_comment_count": len(matched),
        "change_match_rate": safe_ratio(len(matched), len(valid_analyses)),
        "high_controversy_count": sum(1 for item in by_target.values() if item["controversy"] == "高"),
        "problem_domain_distribution": dict(global_domains),
        "platform_distribution": dict(platform_counts),
        "targets": by_target,
    }


def controversy_level(analyses: list[CommentAnalysis], platforms: Counter) -> tuple[str, list[str]]:
    count = len(analyses)
    if count < 5:
        return "证据不足", [f"有效相关评论仅 {count} 条，少于 5 条。"]
    directions = Counter(a.direction_attitude for a in analyses)
    intensities = Counter(a.intensity_attitude for a in analyses)
    reasons: list[str] = []
    if directions["支持改动方向"] / count >= 0.2 and directions["反对改动方向"] / count >= 0.2:
        reasons.append("支持与反对方向均达到相关评论的 20%。")
    if intensities["力度不足"] / count >= 0.2 and intensities["力度过大"] / count >= 0.2:
        reasons.append("力度不足与力度过大均达到相关评论的 20%。")
    if reasons:
        return "高", reasons
    explicit = directions["支持改动方向"] + directions["反对改动方向"]
    dominant = max(directions["支持改动方向"], directions["反对改动方向"])
    split_intensity = intensities["力度不足"] and intensities["力度过大"]
    if explicit and dominant / explicit > 0.7 and not split_intensity:
        return "低", ["超过 70% 的明确方向观点一致，且力度意见未明显分裂。"]
    if min(directions["支持改动方向"], directions["反对改动方向"]) > 0:
        return "中", ["存在明确少数意见，但仍有相对主流方向。"]
    return "中", ["未触发高或低争议规则，按规则归为中。"]
