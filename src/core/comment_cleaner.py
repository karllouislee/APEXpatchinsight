from __future__ import annotations

import re
import unicodedata

from .models import CleanComment, RawComment

URL_ONLY = re.compile(r"^\s*https?://\S+\s*$", re.I)
EMOJI_OR_SYMBOLS = re.compile(r"^[\W_]+$", re.UNICODE)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{2,}", "\n", value)
    return value.strip()


def clean_comment(comment: RawComment) -> CleanComment:
    original = comment.content or ""
    cleaned = normalize_text(original)
    reason = None
    valid = True
    if not cleaned:
        valid, reason = False, "空评论"
    elif URL_ONLY.fullmatch(cleaned):
        valid, reason = False, "纯链接"
    elif EMOJI_OR_SYMBOLS.fullmatch(cleaned):
        valid, reason = False, "纯表情或符号"
    elif len(cleaned) < 4:
        valid, reason = False, "极短低信息评论"
    payload = comment.model_dump()
    payload.update(content=cleaned, original_content=original, cleaned_content=cleaned, is_valid=valid, invalid_reason=reason)
    return CleanComment.model_validate(payload)


def clean_comments(comments: list[RawComment]) -> list[CleanComment]:
    output = [clean_comment(comment) for comment in comments]
    next_id = 1
    for comment in output:
        if not comment.comment_id:
            comment.comment_id = f"COM-{next_id:04d}"
        next_id += 1
    return output

