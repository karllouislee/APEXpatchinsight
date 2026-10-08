from __future__ import annotations

import random
from dataclasses import fields
from typing import Any

from .models import CleanComment, ValidationRecord

VALIDATION_FIELDS = ("text_accepted", "mapping_accepted", "attitude_accepted", "domain_accepted", "evidence_traceable", "dedup_accepted")


def sample_comments(comments: list[CleanComment], size: int, seed: int | None = None) -> list[CleanComment]:
    valid = [comment for comment in comments if comment.is_valid]
    rng = random.Random(seed)
    return rng.sample(valid, min(size, len(valid)))


def validation_metrics(records: list[ValidationRecord]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field in VALIDATION_FIELDS:
        judged = [getattr(record, field) for record in records if getattr(record, field) is not None]
        accepted = sum(value is True for value in judged)
        output[field] = {"accepted": accepted, "judged": len(judged), "rate": accepted / len(judged) if judged else None}
    return output

