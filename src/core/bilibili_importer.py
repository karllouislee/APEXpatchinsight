"""Privacy-preserving import for CSV files exported by Bilibili comment tools."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import RawComment


class BilibiliImportError(ValueError):
    pass


@dataclass(frozen=True)
class BilibiliImportResult:
    comments: list[RawComment]
    total_rows: int
    skipped_rows: int
    truncated: bool
    source_id: str


CONTENT_COLUMNS = ("评论内容", "content", "context", "message", "评论")
COMMENT_ID_COLUMNS = ("评论ID", "rpid", "comment_id")
PARENT_ID_COLUMNS = ("上级评论ID", "parent", "parent_id")
LIKE_COLUMNS = ("点赞数", "like", "likes")
TIME_COLUMNS = ("评论时间", "reply_time", "ctime", "published_at")
MAX_CSV_BYTES = 20 * 1024 * 1024
_BVID_PATTERN = re.compile(r"^BV[0-9A-Za-z]{10}$", re.IGNORECASE)


def _decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BilibiliImportError("CSV 编码无法识别，请导出 UTF-8 CSV。")


def _find_column(fieldnames: list[str], aliases: tuple[str, ...], required: bool = False) -> str | None:
    normalized = {name.strip().lstrip("\ufeff").casefold(): name for name in fieldnames if name}
    for alias in aliases:
        if alias.casefold() in normalized:
            return normalized[alias.casefold()]
    if required:
        raise BilibiliImportError(f"CSV 缺少必要列：{' / '.join(aliases)}")
    return None


def _safe_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _has_parent(value: object) -> bool:
    return str(value or "").strip().casefold() not in {"", "0", "none", "null", "nan"}


def _validated_source_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"bilibili.com", "www.bilibili.com"}:
        raise BilibiliImportError("来源链接仅允许 https://www.bilibili.com/ 页面。")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0].casefold() == "video" and _BVID_PATTERN.fullmatch(path_parts[1]):
        return f"https://www.bilibili.com/video/{path_parts[1]}"
    clean_path = "/" + "/".join(path_parts) if path_parts else "/"
    return f"https://www.bilibili.com{clean_path}"


def parse_bilibili_csv(
    data: bytes,
    filename: str,
    *,
    row_limit: int = 1000,
    source_url: str = "",
) -> BilibiliImportResult:
    if not data:
        raise BilibiliImportError("CSV 文件为空。")
    if len(data) > MAX_CSV_BYTES:
        raise BilibiliImportError("CSV 文件超过 20 MB，请先分批导出或拆分后再导入。")
    if not 1 <= row_limit <= 5000:
        raise BilibiliImportError("单次导入上限必须在 1–5000 条之间。")

    text = _decode_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise BilibiliImportError("CSV 没有表头。")

    content_col = _find_column(fieldnames, CONTENT_COLUMNS, required=True)
    comment_id_col = _find_column(fieldnames, COMMENT_ID_COLUMNS)
    parent_id_col = _find_column(fieldnames, PARENT_ID_COLUMNS)
    like_col = _find_column(fieldnames, LIKE_COLUMNS)
    time_col = _find_column(fieldnames, TIME_COLUMNS)
    source_url = _validated_source_url(source_url)

    rows = list(reader)
    parent_text: dict[str, str] = {}
    if comment_id_col:
        for row in rows:
            source_comment_id = str(row.get(comment_id_col) or "").strip()
            content = str(row.get(content_col) or "").strip()
            if source_comment_id and content:
                parent_text[source_comment_id] = content

    digest = hashlib.sha256(data).hexdigest()
    source_id = f"BILI-{digest[:12]}"
    anonymous_filename = f"bilibili_{digest[:12]}.csv"
    output: list[RawComment] = []
    skipped = 0
    for csv_row, row in enumerate(rows, start=2):
        content = str(row.get(content_col) or "").strip()
        if not content:
            skipped += 1
            continue
        if len(output) >= row_limit:
            break

        parent_id = str(row.get(parent_id_col) or "").strip() if parent_id_col else ""
        source_comment_id = str(row.get(comment_id_col) or "").strip() if comment_id_col else ""
        if source_comment_id:
            # Bilibili comment IDs are stable across later/incremental exports. Hash
            # the ID directly so re-exporting a larger CSV does not duplicate rows.
            source_fingerprint = f"bilibili:rpid:{source_comment_id}"
        else:
            # Files without IDs can only be deduplicated within the same export.
            source_fingerprint = f"{source_id}:row:{csv_row}:{content}"
        source_key = hashlib.sha256(source_fingerprint.encode("utf-8")).hexdigest()[:20]
        output.append(RawComment(
            local_index=csv_row,
            platform="B站",
            content=content,
            likes=_safe_int(row.get(like_col)) if like_col else None,
            is_reply=_has_parent(parent_id),
            reply_context=parent_text.get(parent_id) if _has_parent(parent_id) else None,
            is_complete=True,
            language="zh",
            source_file=anonymous_filename,
            source_type="csv",
            source_url=source_url,
            source_comment_key=source_key,
            published_at=str(row.get(time_col) or "").strip() if time_col else "",
        ))

    if not output:
        raise BilibiliImportError("CSV 中没有可导入的评论内容。")
    available = sum(1 for row in rows if str(row.get(content_col) or "").strip())
    return BilibiliImportResult(
        comments=output,
        total_rows=len(rows),
        skipped_rows=skipped,
        truncated=available > len(output),
        source_id=source_id,
    )
