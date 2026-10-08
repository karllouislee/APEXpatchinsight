from __future__ import annotations

from rapidfuzz.fuzz import ratio

from .models import CleanComment


def deduplicate_comments(comments: list[CleanComment], threshold: float = 91.0) -> list[CleanComment]:
    canonical: list[CleanComment] = []
    for comment in comments:
        comment.duplicate_of = None
        comment.suspected_duplicate = False
        if not comment.is_valid:
            canonical.append(comment)
            continue
        match: CleanComment | None = None
        exact = False
        for existing in canonical:
            if not existing.is_valid or existing.duplicate_of:
                continue
            if comment.cleaned_content == existing.cleaned_content:
                match, exact = existing, True
                break
            if ratio(comment.cleaned_content, existing.cleaned_content) >= threshold:
                match = existing
                break
        if match:
            comment.duplicate_of = match.comment_id
            comment.suspected_duplicate = not exact
        canonical.append(comment)
    return canonical


def canonical_comments(comments: list[CleanComment]) -> list[CleanComment]:
    return [comment for comment in comments if comment.is_valid and not comment.duplicate_of]

