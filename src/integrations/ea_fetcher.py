from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ALLOWED_HOSTS = {"ea.com", "www.ea.com"}
NEWS_URL = "https://www.ea.com/games/apex-legends/apex-legends/news"
DESIGNER_KEYWORDS = ("designer’s notes", "designer's notes", "designers notes")


class FetchError(RuntimeError):
    pass


def validate_ea_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("仅允许 HTTPS 的 ea.com 或 www.ea.com 官方链接。")
    if parsed.username or parsed.password:
        raise ValueError("URL 不允许包含认证信息。")
    return url.strip()


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, backoff_factor=0.4, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "ApexPatchInsight/0.1 (+local research tool)"})
    return session


def fetch_html(url: str, timeout: tuple[float, float] = (5, 20)) -> tuple[str, str]:
    requested = validate_ea_url(url)
    try:
        response = _session().get(requested, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"EA 页面获取失败：{exc}") from exc
    final_url = validate_ea_url(response.url)
    if "text/html" not in response.headers.get("content-type", "text/html").lower():
        raise FetchError("EA 链接未返回 HTML 页面。")
    return response.text, final_url


@dataclass(frozen=True)
class NewsCandidate:
    title: str
    url: str
    date: str | None = None


def find_designer_notes(index_html: str, base_url: str = NEWS_URL) -> list[NewsCandidate]:
    soup = BeautifulSoup(index_html, "html.parser")
    candidates: dict[str, NewsCandidate] = {}
    for anchor in soup.select("a[href]"):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        aria = anchor.get("aria-label", "")
        combined = f"{title} {aria}".lower()
        href = urljoin(base_url, anchor.get("href", ""))
        if not any(key in combined for key in DESIGNER_KEYWORDS):
            continue
        try:
            href = validate_ea_url(href)
        except ValueError:
            continue
        parent = anchor.find_parent(["article", "li", "div"])
        time_node = parent.find("time") if parent else None
        date = (time_node.get("datetime") or time_node.get_text(" ", strip=True)) if time_node else None
        candidates[href] = NewsCandidate(title=title or aria or "Designer’s Notes", url=href, date=date)
    return sorted(candidates.values(), key=_date_key, reverse=True)


def _date_key(candidate: NewsCandidate) -> datetime:
    if not candidate.date:
        return datetime.min
    raw = candidate.date.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min


def fetch_latest_designer_notes() -> tuple[NewsCandidate, str, str]:
    index_html, final_index = fetch_html(NEWS_URL)
    candidates = find_designer_notes(index_html, final_index)
    if not candidates:
        raise FetchError("EA 新闻页中未找到标题包含 Designer’s Notes 的文章，请使用手动 URL。")
    selected = candidates[0]
    article_html, final_url = fetch_html(selected.url)
    return NewsCandidate(selected.title, final_url, selected.date), article_html, final_url

