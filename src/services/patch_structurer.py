from __future__ import annotations

import re

from ..core.models import Article, PatchChange
from ..integrations.siliconflow_client import SiliconFlowClient, load_prompt


def structure_with_ai(article: Article, client: SiliconFlowClient) -> list[PatchChange]:
    payload = {"title": article.title, "url": article.url, "sections": article.sections}
    return client.text_json(load_prompt("patch_structure_prompt.txt"), payload, list[PatchChange])


def structure_deterministic(article: Article) -> list[PatchChange]:
    changes: list[PatchChange] = []
    verbs = re.compile(r"(increased|decreased|reduced|raised|lowered|changed|now|from\s+\d|to\s+\d|增加|降低|提高|调整|削弱|增强)", re.I)
    for section in article.sections:
        heading = str(section.get("heading", "未分类"))
        entries = list(section.get("items", [])) or list(section.get("paragraphs", []))
        parent_heading = str(section.get("parent_heading") or "").strip()
        is_ability_section = section.get("section_type") == "ability" and bool(parent_heading)
        target = parent_heading or heading
        ability_or_system = heading if is_ability_section else ""
        for entry in entries:
            summary = str(entry).strip()
            if len(summary) < 8 or not verbs.search(summary):
                continue
            before_after = re.findall(r"(?:from|由)\s*([^,，;；]+?)\s*(?:to|至|到)\s*([^,，;；。]+)", summary, re.I)
            values = [{"before": a.strip(), "after": b.strip()} for a, b in before_after[:3]]
            changes.append(PatchChange(
                section=heading, category="待人工确认", target=heading,
                change_direction="调整", change_summary=summary, exact_values=values,
                source_heading=heading, source_excerpt=summary[:240], aliases=[heading], parse_confidence=0.52,
                inference_notes=["规则解析结果；设计目标与原始问题未由官方文本明确确认。"],
            ))
            if is_ability_section:
                change = changes[-1]
                change.section = parent_heading
                change.target = target
                change.ability_or_system = ability_or_system
                change.change_summary = f"{target} - {ability_or_system}: {summary}"
                change.source_heading = f"{target} - {ability_or_system}"
                change.aliases = [target, ability_or_system]
    return changes

