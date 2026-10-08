"""Import Designer's Notes and turn the change list into a confirmed, editable table."""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from ..core.models import Article, PatchChange
from ..integrations.ea_fetcher import fetch_html, fetch_latest_designer_notes
from ..core.article_parser import parse_article
from ..services.patch_structurer import structure_deterministic, structure_with_ai


def import_latest_article() -> Article:
    candidate, html, url = fetch_latest_designer_notes()
    return parse_article(html, url, candidate.title)


def import_article_url(url: str) -> Article:
    html, final_url = fetch_html(url)
    return parse_article(html, final_url)


def structure_with_model(article: Article, client, alias_dict=None) -> list[PatchChange]:
    return localize_targets(structure_with_ai(article, client), alias_dict)


def structure_with_rules(article: Article, alias_dict=None) -> list[PatchChange]:
    return localize_targets(structure_deterministic(article), alias_dict)


def localize_targets(changes: list[PatchChange], alias_dict) -> list[PatchChange]:
    """Show and match targets under their Chinese names.

    Community discussion is almost entirely in Chinese, so "Bloodhound" is
    stored as "寻血猎犬" with the English name kept in ``aliases`` — which stays
    resolvable for mapping without leaking "CHG-019"-style ids anywhere. This
    runs once at import so editing the slang dictionary later cannot re-key
    analyses that already exist.
    """
    for change in changes:
        if alias_dict is None:
            break
        name = alias_dict.chinese_name(change.target)
        if not name or name == change.target:
            continue
        for term in (change.target, name):
            if term and term not in change.aliases:
                change.aliases.append(term)
        change.target = name
    return changes


DEFAULT_VALUES: dict[str, Any] = {
    "target": "待填写",
    "category": "其他",
    "change_direction": "调整",
    "change_summary": "待填写",
    "design_goal": "",
    "ability_or_system": "",
    "parse_confidence": 0.5,
}


def apply_editor_rows(changes: list[PatchChange], rows: Iterable[dict[str, Any]]) -> list[PatchChange]:
    """Rebuild the change list from the data-editor grid.

    Rows flagged for deletion are dropped; every surviving row is matched to an
    existing change by its target name so editing a row in place keeps the
    analyses already attached to it.
    """
    existing: dict[str, PatchChange] = {}
    for change in changes:
        existing.setdefault(change.target, change)
    updated: list[PatchChange] = []
    for row in rows:
        if bool(row.get("删除", False)):
            continue
        target = str(row.get("target") or DEFAULT_VALUES["target"]).strip()
        change = existing.get(target) or PatchChange(
            target=target,
            change_summary=DEFAULT_VALUES["change_summary"],
        )
        change.target = target
        change.category = str(row.get("category") or DEFAULT_VALUES["category"])
        change.change_direction = str(row.get("change_direction") or DEFAULT_VALUES["change_direction"])
        change.change_summary = str(row.get("change_summary") or DEFAULT_VALUES["change_summary"])
        change.design_goal = str(row.get("design_goal") or "")
        change.aliases = [part.strip() for part in str(row.get("aliases") or "").split("|") if part.strip()]
        change.ability_or_system = str(row.get("ability_or_system") or "")
        change.parse_confidence = float(row.get("parse_confidence") or DEFAULT_VALUES["parse_confidence"])
        change.confirmed = bool(row.get("confirmed", False))
        updated.append(change)
    return updated


def merge_changes(changes: list[PatchChange], targets: Sequence[str]) -> list[PatchChange]:
    """Fold duplicate target rows into the first, unioning aliases and excerpts."""
    if len(targets) < 2:
        return changes
    wanted = set(targets)
    selected = [change for change in changes if change.target in wanted]
    if len(selected) < 2:
        return changes
    primary = selected[0]
    primary.aliases = sorted({term for change in selected for term in [change.target, *change.aliases]})
    primary.source_excerpt = "\n".join(filter(None, (change.source_excerpt for change in selected)))
    drop = wanted - {primary.target}
    return [change for change in changes if change.target not in drop]


def confirm_all(changes: list[PatchChange]) -> None:
    for change in changes:
        change.confirmed = True


def all_confirmed(changes: list[PatchChange]) -> bool:
    return bool(changes) and all(change.confirmed for change in changes)
