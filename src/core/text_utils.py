"""Text helpers shared by cleaning, dedup, review, and analysis rules."""
from __future__ import annotations

import re
import unicodedata


def normalize_for_quote(value: str) -> str:
    """Fold a string for substring matching, ignoring width, case, and spacing."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).lower()


MIN_SALVAGED_QUOTE_CHARS = 4


def reconcile_quote(quote: str, source: str) -> str:
    """Return ``quote`` if it really occurs in ``source``, else the best salvage.

    Models occasionally pad or paraphrase a quote ("砍得好" → "这刀砍得好啊").
    Rejecting the whole batch over that would throw away a paid, otherwise
    correct classification, so the longest genuine substring is kept instead
    and only a fully hallucinated quote is dropped.
    """
    if not quote:
        return ""
    folded_quote = normalize_for_quote(quote)
    folded_source = normalize_for_quote(source)
    if not folded_quote or not folded_source:
        return ""
    if folded_quote in folded_source:
        return quote
    best = ""
    for start in range(len(folded_quote)):
        for end in range(len(folded_quote), start + len(best), -1):
            if folded_quote[start:end] in folded_source:
                if end - start > len(best):
                    best = folded_quote[start:end]
                break
    return best if len(best) >= MIN_SALVAGED_QUOTE_CHARS else ""


def split_keywords(value: str) -> list[str]:
    """Parse a comma-separated keyword box, accepting both , and ，."""
    if not value:
        return []
    return [part.strip() for part in str(value).replace("，", ",").split(",") if part.strip()]
