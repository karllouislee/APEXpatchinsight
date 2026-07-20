from __future__ import annotations

import re
from collections.abc import Sequence
from .models import CandidateScore, Expert, RouteResponse, RouteRequest, Skill

_STOPWORDS = {"的", "了", "并", "和", "一个", "帮我", "请", "进行", "生成"}

# 英文 capability/tag 到中文同义词的映射，让英文标签也能匹配中文任务文本
_SYNONYMS: dict[str, list[str]] = {
    "data": ["数据"],
    "coding": ["代码", "编程", "编写"],
    "debugging": ["调试", "排错", "bug"],
    "research": ["调研", "搜索", "研究"],
    "document": ["文档", "报告", "报表"],
    "visualization": ["可视化", "图表"],
    "browser": ["浏览器", "网页"],
    "web": ["网页", "网站", "web"],
    "ai": ["人工智能", "ai", "智能"],
}


def _tokens(text: str) -> set[str]:
    normalized = text.lower()
    words = set(re.findall(r"[a-z0-9_+#.-]+|[\u4e00-\u9fff]", normalized))
    return words - _STOPWORDS


def _score(item: Expert | Skill, task: str) -> CandidateScore:
    normalized_task = task.lower()
    tokens = _tokens(task)
    labels = set(item.tags) | set(item.capabilities)
    # English labels use token overlap; Chinese labels are matched as phrases.
    # Also check synonyms so English capabilities match Chinese task text.
    hits: set[str] = set()
    for label in labels:
        low = label.lower()
        if low in normalized_task or low in tokens:
            hits.add(label)
            continue
        for syn in _SYNONYMS.get(low, []):
            if syn in normalized_task:
                hits.add(label)
                break
    hits_sorted = sorted(hits)
    score = min(1.0, len(hits_sorted) / 3)
    reasons = [f"命中标签/能力：{', '.join(hits_sorted)}"] if hits_sorted else ["没有直接命中，作为兜底候选"]
    return CandidateScore(id=item.id, score=score, reasons=reasons)


class RuleRouter:
    def __init__(self, experts: Sequence[Expert], skills: Sequence[Skill]) -> None:
        self.experts = list(experts)
        self.skills = list(skills)

    def route(self, request: RouteRequest) -> RouteResponse:
        enabled_experts = [x for x in self.experts if x.risk_level != "high"]
        if not enabled_experts:
            enabled_experts = list(self.experts)
        expert_scores = sorted(((_score(x, request.task), x) for x in enabled_experts), key=lambda pair: pair[0].score, reverse=True)
        if request.preferred_expert:
            expert_scores.sort(key=lambda pair: pair[1].id != request.preferred_expert)
        selected_score, expert = expert_scores[0]
        allowed = {sid for sid in expert.skill_ids}
        skill_scores = sorted(
            ((_score(x, request.task), x) for x in self.skills
             if x.enabled and x.id in allowed and x.id not in set(request.excluded_skills)),
            key=lambda pair: pair[0].score,
            reverse=True,
        )
        required = set(request.required_skills)
        required_items = [(score, skill) for score, skill in skill_scores if skill.id in required]
        missing_required = required - {skill.id for _, skill in required_items}
        selected_skills = [skill for score, skill in skill_scores if score.score > 0][: request.max_skills]
        for _, skill in required_items:
            if skill not in selected_skills and len(selected_skills) < request.max_skills:
                selected_skills.append(skill)
        if not selected_skills and skill_scores and not missing_required:
            selected_skills = [skill_scores[0][1]]
        reasons = [f"选择专家：{expert.name}（{selected_score.reasons[0]}）"]
        reasons.append("Skill 按专家能力边界过滤，再按任务命中度排序")
        fallback = bool(missing_required)
        if missing_required:
            reasons.append(f"无法满足必需 Skill：{', '.join(sorted(missing_required))}")
        if request.preferred_expert:
            reasons.append(f"已应用显式专家偏好：{request.preferred_expert}")
        if request.constraints.get("no_external_write"):
            reasons.append("已启用 no_external_write 约束；本次不选择外部写入能力")
        confidence = selected_score.score if not fallback else min(selected_score.score, 0.3)
        return RouteResponse(
            task_id=request.task_id,
            expert=expert,
            skills=selected_skills,
            confidence=confidence,
            needs_confirmation=confidence < 0.7 or fallback,
            fallback=fallback,
            reasons=reasons,
            candidates=[score for score, _ in expert_scores],
        )
