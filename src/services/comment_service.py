"""Comment pipeline: CSV import, cleaning, dedup, and manual corrections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..core.bilibili_importer import parse_bilibili_csv
from ..core.comment_cleaner import clean_comments
from ..core.deduplicator import deduplicate_comments
from ..core.models import CleanComment, Project, RawComment
from ..core.text_utils import split_keywords
from ..integrations.comment_store import merge_extracted_comments
from .comment_analyzer import batch_count


@dataclass(frozen=True)
class BilibiliImport:
    comments: list[RawComment]
    total_rows: int
    skipped_rows: int
    truncated: bool

    @property
    def is_empty(self) -> bool:
        return not self.comments


def import_bilibili_csv(data: bytes, filename: str, row_limit: int, source_url: str = "") -> BilibiliImport:
    result = parse_bilibili_csv(data, filename, row_limit=row_limit, source_url=source_url)
    return BilibiliImport(
        comments=list(result.comments),
        total_rows=result.total_rows,
        skipped_rows=result.skipped_rows,
        truncated=result.truncated,
    )


def new_comments_only(existing_raw: list[RawComment], incoming: list[RawComment]) -> list[RawComment]:
    seen = {item.source_comment_key for item in existing_raw if item.source_comment_key}
    return [item for item in incoming if item.source_comment_key not in seen]


def merge_raw_comments(existing_raw: list[RawComment], extracted: list[RawComment]) -> list[RawComment]:
    """Append new comments with fresh, stable ids.

    Existing comments keep their ids so analyses and review records stay valid
    when another CSV is imported into the same corpus.
    """
    return merge_extracted_comments(existing_raw, extracted)


def rebuild_clean_comments(
    raw: list[RawComment],
    previous: dict[str, CleanComment],
    preserve_text: bool = True,
) -> list[CleanComment]:
    """Clean + dedupe a raw corpus while carrying manual edits forward.

    ``preserve_text`` keeps the reviewer's corrections instead of the text
    that came back from the import.
    """
    comments = clean_comments(raw)
    for comment in comments:
        before = previous.get(comment.comment_id)
        if before is None:
            continue
        comment.manual_keywords = list(before.manual_keywords)
        if preserve_text:
            comment.cleaned_content = before.cleaned_content
            comment.content = before.content
            comment.is_valid = before.is_valid
    return deduplicate_comments(comments)


def demote_demo_project(project: Project) -> bool:
    """Drop the fictional demo payload before real data is mixed in.

    Returns ``True`` when a demo project was demoted, which also means the
    caller should discard any raw comments left over from the demo corpus.
    """
    if not project.is_demo:
        return False
    project.is_demo = False
    project.demo_disclaimer = ""
    project.comments = []
    project.analyses = []
    project.reviews = []
    project.skipped_reviews = []
    project.changes = []
    project.article = None
    return True


def apply_comment_corrections(comments: list[CleanComment], rows: Iterable[dict[str, Any]]) -> list[CleanComment]:
    """Apply the data-editor grid rows back onto the stored comments."""
    lookup = {comment.comment_id: comment for comment in comments}
    for row in rows:
        comment = lookup.get(str(row.get("comment_id")))
        if comment is None:
            continue
        comment.cleaned_content = str(row.get("原文") or "")
        comment.content = comment.cleaned_content
        comment.is_valid = bool(row.get("有效"))
        reply_context = str(row.get("回复上下文") or "").strip()
        comment.reply_context = reply_context or None
        comment.manual_keywords = split_keywords(row.get("人工关键词"))
    return deduplicate_comments(list(lookup.values()))


def estimate_text_calls(candidates: list[CleanComment], batch_size: int = 20) -> int:
    return batch_count(len(candidates), batch_size)


def source_file_count(comments: list[CleanComment]) -> int:
    """How many distinct imported files the current corpus came from."""
    return len({comment.source_file for comment in comments if comment.source_file})
