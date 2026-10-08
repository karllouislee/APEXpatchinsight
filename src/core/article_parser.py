from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import Article

ABILITY_HEADINGS = {"passive", "tactical", "ultimate", "new upgrades"}


def parse_article(html: str, url: str, fallback_title: str = "EA Designer’s Notes") -> Article:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style, nav, footer, noscript"):
        node.decompose()
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = _clean(title_node.get_text(" ", strip=True)) if title_node else fallback_title
    published = None
    time_node = soup.select_one("time[datetime]") or soup.select_one("time")
    if time_node:
        published = time_node.get("datetime") or _clean(time_node.get_text(" ", strip=True))
    root = soup.select_one("article") or soup.select_one("main") or soup.body or soup
    sections: list[dict[str, object]] = []
    current = {"heading": "正文", "parent_heading": None, "section_type": "content", "paragraphs": [], "items": []}
    last_hero_heading: str | None = None
    for node in root.find_all(["h2", "h3", "h4", "p", "li"], recursive=True):
        text = _clean(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name in {"h2", "h3", "h4"}:
            if current["paragraphs"] or current["items"] or current.get("section_type") == "hero_or_group":
                sections.append(current)
            normalized_heading = _normalize_heading(text)
            is_ability = normalized_heading in ABILITY_HEADINGS
            if is_ability and last_hero_heading:
                current = {
                    "heading": text,
                    "parent_heading": last_hero_heading,
                    "section_type": "ability",
                    "paragraphs": [],
                    "items": [],
                }
            else:
                current = {
                    "heading": text,
                    "parent_heading": None,
                    "section_type": "hero_or_group",
                    "paragraphs": [],
                    "items": [],
                }
                if not is_ability:
                    last_hero_heading = text
        elif node.name == "li":
            current["items"].append(text)
        else:
            current["paragraphs"].append(text)
    if current["paragraphs"] or current["items"] or current.get("section_type") == "hero_or_group":
        sections.append(current)
    text = "\n".join(
        [str(s["heading"])] + [str(p) for p in s["paragraphs"]] + [f"- {i}" for i in s["items"]]
        for s in sections
    ) if False else "\n".join(
        part for section in sections for part in ([str(section["heading"])] + list(section["paragraphs"]) + [f"- {i}" for i in section["items"]])
    )
    return Article(title=title, url=url, published_at=published, sections=sections, text=text)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_heading(value: str) -> str:
    return _clean(value).casefold().rstrip(":：")

