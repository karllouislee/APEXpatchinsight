"""Run the comment corpus through the text model in two stages.

**Stage 1 — topic classification.** One pass over the whole corpus asks only
*what* each comment talks about (target + problem type). That produces the topic
heat reading before anything else is spent, which is usually the first question
anyone asks. It is also the cheap half: five output fields, no attitude.

**Stage 2 — attitude, one change item at a time.** The corpus is then split by
the target stage 1 assigned, and each bucket is sent on its own with only that
target's change row. Two things improve at once: the model never has to
disambiguate a comment against thirteen unrelated changes (it was silently
doing that work on every row), and the request carries one change row instead
of the whole table. It also matches how a human would actually audit the
result — target by target.

Both stages reuse the same guard rails: sequence numbers instead of ids, an
explicit output contract checked before validation, and a reconciled quote.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, TypeAdapter

from ..core.aggregation import group_terms, target_groups
from ..core.community_aliases import AliasDictionary
from ..core.models import (
    STAGE_DONE,
    STAGE_TOPIC,
    CleanComment,
    CommentAnalysis,
    PatchChange,
    apply_derived_fields,
)
from ..core.text_utils import reconcile_quote
from ..integrations.siliconflow_client import SiliconFlowClient, SiliconFlowError, load_prompt

ALIAS_TABLE_TOKEN = "{ALIAS_TABLE}"
REVIEW_LESSONS_TOKEN = "{REVIEW_LESSONS}"
TOPIC_PROMPT_NAME = "comment_topic_prompt.txt"
ATTITUDE_PROMPT_NAME = "comment_attitude_prompt.txt"

MIN_BATCH_SIZE = 10
MAX_BATCH_SIZE = 20
# Attitude batches are small by construction — a bucket holds the comments for a
# single target — so they can go wider without the model losing its place.
MAX_ATTITUDE_BATCH_SIZE = 30

# Long prose is clipped: the model needs the gist, not the whole entry. A merged
# target can carry several ability rows, so its summary budget is larger.
CHANGE_FIELD_LIMITS = {"change_summary": 200, "target": 40}
DEFAULT_FIELD_LIMIT = 40

# A missing key means the model ignored the output contract. Tolerate a couple
# of sloppy rows, but a batch-wide breach is real money spent on nothing and
# must be surfaced instead of quietly landing as "无法判断".
TOPIC_KEYS = ("n", "tg", "m", "q", "c")
ATTITUDE_KEYS = ("n", "d", "i", "q", "c", "s")
BREACH_TOLERANCE = 0.3

_PARSED_TOPIC = TypeAdapter(list["TopicVerdict"])
_PARSED_ATTITUDE = TypeAdapter(list["AttitudeVerdict"])


def clamp_batch_size(batch_size: int, maximum: int = MAX_BATCH_SIZE) -> int:
    return max(MIN_BATCH_SIZE, min(int(batch_size or maximum), maximum))


def batch_count(total: int, batch_size: int = MAX_BATCH_SIZE) -> int:
    """How many requests a corpus of ``total`` comments will take."""
    size = clamp_batch_size(batch_size)
    return -(-int(total) // size)


def _clip(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _target_rows(changes: list[PatchChange], alias_dict: AliasDictionary | None) -> dict[str, dict[str, object]]:
    """One collapsed row per target, keyed by the name the corpus uses."""
    rows: dict[str, dict[str, object]] = {}
    for target, group in target_groups(changes).items():
        name = (alias_dict.chinese_name(target) if alias_dict is not None else target) or target
        row: dict[str, object] = {"tg": name}
        directions = sorted({change.change_direction for change in group if change.change_direction})
        if len(directions) == 1:
            row["dir"] = directions[0]
        summaries = [
            f"{change.ability_or_system}：{change.change_summary}" if change.ability_or_system else change.change_summary
            for change in group
            if change.change_summary
        ]
        if summaries:
            row["sum"] = _clip(" | ".join(summaries), CHANGE_FIELD_LIMITS["change_summary"])
        rows[name] = row
    return rows


def change_brief(changes: list[PatchChange], alias_dict: AliasDictionary | None = None) -> list[dict[str, object]]:
    """One row per target, carrying the fields that steer classification.

    Collapsing by target is what makes stage 1 affordable on a large corpus, and
    it removes a decision the model was making badly: with four Bloodhound rows
    it had to guess which ability a comment meant every single time.
    """
    return list(_target_rows(changes, alias_dict).values())


def comment_rows(batch: list[CleanComment]) -> tuple[list[dict[str, object]], str | None]:
    """Compact per-comment rows plus the source file shared by the whole batch.

    ``n`` is the row's 1-based position and is the only thing tying a verdict
    back to a comment. Empty fields are dropped rather than sent as ``null``.
    """
    files = {comment.source_file for comment in batch}
    shared = files.pop() if len(files) == 1 else None
    rows: list[dict[str, object]] = []
    for index, comment in enumerate(batch, start=1):
        row: dict[str, object] = {"n": index, "t": comment.cleaned_content}
        if comment.platform:
            row["p"] = comment.platform
        if comment.likes is not None:
            row["lk"] = comment.likes
        if comment.reply_context:
            row["r"] = comment.reply_context
        if comment.manual_keywords:
            row["kw"] = comment.manual_keywords
        if shared is None and comment.source_file:
            row["f"] = comment.source_file
        rows.append(row)
    return rows, shared


def build_topic_payload(
    batch: list[CleanComment],
    changes: list[PatchChange],
    aliases: dict[str, list[str]],
    alias_dict: AliasDictionary | None = None,
) -> dict[str, object]:
    rows, shared_file = comment_rows(batch)
    payload: dict[str, object] = {
        "changes": change_brief(changes, alias_dict),
        "aliases": aliases,
        "comments": rows,
    }
    if shared_file:
        payload["source_file"] = shared_file
    return payload


def build_attitude_payload(
    batch: list[CleanComment],
    target: str | None,
    changes: list[PatchChange],
    alias_dict: AliasDictionary | None = None,
) -> dict[str, object]:
    """One target, one change row, and only that target's comments."""
    rows, shared_file = comment_rows(batch)
    payload: dict[str, object] = {
        "target": target,
        "change": _target_rows(changes, alias_dict).get(target) if target else None,
        "comments": rows,
    }
    if shared_file:
        payload["source_file"] = shared_file
    return payload


def build_prompt(name: str, alias_dict: AliasDictionary | None, lessons: str = "") -> str:
    """System prompt with the slang table and any review lessons injected."""
    table = alias_dict.prompt_table() if alias_dict is not None else "（无可用别名词典）"
    prompt = load_prompt(name).replace(ALIAS_TABLE_TOKEN, table)
    return prompt.replace(REVIEW_LESSONS_TOKEN, lessons.strip())


def alias_lookup(changes: list[PatchChange], alias_dict: AliasDictionary | None) -> dict[str, list[str]]:
    """Chinese target name -> every surface form the model should accept."""
    aliases: dict[str, list[str]] = {}
    for target, group in target_groups(changes).items():
        name = alias_dict.chinese_name(target) if alias_dict is not None else target
        key = (name or target or "").strip()
        if not key:
            continue
        bucket = aliases.setdefault(key, [])
        # Every stored surface form for the whole group, so an English-only or
        # ability-only mention still resolves.
        for term in group_terms(group) | {target, name}:
            term = (term or "").strip()
            if term and term not in bucket:
                bucket.append(term)
        if alias_dict is not None:
            # Resolve slang (挖机/狗子) even when aliases were never filled in by hand.
            for term in alias_dict.aliases_for_target(target):
                if term not in bucket:
                    bucket.append(term)
    return aliases


class TopicVerdict(BaseModel):
    """Stage 1: what the comment is about."""

    n: int = -1
    tg: str | None = None
    m: str = "无法判断"
    q: str = ""
    c: float = Field(default=0.5, ge=0, le=1)


class AttitudeVerdict(BaseModel):
    """Stage 2: what the comment thinks about it."""

    n: int = -1
    d: str = "无法判断"
    i: str = "无法判断"
    q: str = ""
    c: float = Field(default=0.5, ge=0, le=1)
    s: bool = False


def _request(
    client: SiliconFlowClient,
    prompt_name: str,
    payload: dict,
    keys: tuple[str, ...],
    lessons: str,
    alias_dict: AliasDictionary | None,
) -> list[dict]:
    raw = client.text_json(build_prompt(prompt_name, alias_dict, lessons), payload, list[dict])
    _check_contract(raw, keys)
    return raw


def analyze_topic_batch(
    comments: list[CleanComment],
    changes: list[PatchChange],
    client: SiliconFlowClient,
    batch_size: int = MAX_BATCH_SIZE,
    alias_dict: AliasDictionary | None = None,
    lessons: str = "",
) -> list[CommentAnalysis]:
    """Classify one batch into targets. Leaves the attitude untouched."""
    size = clamp_batch_size(batch_size, MAX_BATCH_SIZE)
    batch = comments[:size]
    if not batch:
        return []
    payload = build_topic_payload(batch, changes, alias_lookup(changes, alias_dict), alias_dict)
    raw = _request(client, TOPIC_PROMPT_NAME, payload, TOPIC_KEYS, lessons, alias_dict)
    verdicts = _PARSED_TOPIC.validate_python(raw)

    by_seq = {index: comment for index, comment in enumerate(batch, start=1)}
    _check_sequences(by_seq, [verdict.n for verdict in verdicts])
    output: list[CommentAnalysis] = []
    for verdict in verdicts:
        comment = by_seq[verdict.n]
        analysis = CommentAnalysis(
            comment_id=comment.comment_id,
            analysis_stage=STAGE_TOPIC,
            primary_target=(verdict.tg or "").strip() or None,
            problem_domain=verdict.m,
            evidence_quote=reconcile_quote(verdict.q, comment.cleaned_content),
            analysis_confidence=verdict.c,
        )
        output.append(apply_derived_fields(analysis, comment.cleaned_content))
    return output


def analyze_attitude_batch(
    comments: list[CleanComment],
    target: str | None,
    changes: list[PatchChange],
    client: SiliconFlowClient,
    batch_size: int = MAX_ATTITUDE_BATCH_SIZE,
    alias_dict: AliasDictionary | None = None,
    lessons: str = "",
) -> list[CommentAnalysis]:
    """Judge attitude for one batch, all of which belong to ``target``.

    Only the attitude, quote, confidence and sarcasm flag are produced here. The
    target and problem domain came from stage 1 and are merged back by the
    caller (``analysis_service.merge_attitudes``) rather than being re-asked.
    """
    size = clamp_batch_size(batch_size, MAX_ATTITUDE_BATCH_SIZE)
    batch = comments[:size]
    if not batch:
        return []
    payload = build_attitude_payload(batch, target, changes, alias_dict)
    raw = _request(client, ATTITUDE_PROMPT_NAME, payload, ATTITUDE_KEYS, lessons, alias_dict)
    verdicts = _PARSED_ATTITUDE.validate_python(raw)

    by_seq = {index: comment for index, comment in enumerate(batch, start=1)}
    _check_sequences(by_seq, [verdict.n for verdict in verdicts])
    output: list[CommentAnalysis] = []
    for verdict in verdicts:
        comment = by_seq[verdict.n]
        analysis = CommentAnalysis(
            comment_id=comment.comment_id,
            analysis_stage=STAGE_DONE,
            primary_target=target,
            direction_attitude=verdict.d,
            intensity_attitude=verdict.i,
            evidence_quote=reconcile_quote(verdict.q, comment.cleaned_content),
            analysis_confidence=verdict.c,
            suspected_sarcasm=verdict.s,
        )
        output.append(analysis)
    return output


def _check_contract(rows: list[dict], keys: tuple[str, ...]) -> None:
    """Raise when the model dropped the output fields wholesale.

    This is the guard the previous prompt lacked. The model had invented keys
    and omitted contract fields; because every omitted field had a default,
    validation passed and the whole batch silently became "无法判断" — which is
    exactly the "人工复查率 95%" symptom.
    """
    if not rows:
        return
    missing = sum(1 for row in rows if any(key not in row for key in keys))
    if missing and missing / len(rows) > BREACH_TOLERANCE:
        raise SiliconFlowError(
            f"模型未按输出契约返回字段：{missing}/{len(rows)} 条缺少必需键（{'/'.join(keys)}）。"
        )


def _check_sequences(by_seq: dict[int, CleanComment], returned: list[int]) -> None:
    seen = set(returned)
    missing = sorted(set(by_seq) - seen)
    extra = sorted(seen - set(by_seq))
    if missing or extra:
        raise SiliconFlowError(
            f"模型返回的序号不匹配：缺少 {missing or '无'}，多出 {extra or '无'}。"
        )


__all__ = [
    "analyze_topic_batch",
    "analyze_attitude_batch",
    "heuristic_analysis",
    "TopicVerdict",
    "AttitudeVerdict",
]


def heuristic_analysis(comment: CleanComment, changes: list[PatchChange]) -> CommentAnalysis:
    """Demo-only fallback; never presented as a real model result."""
    text = comment.cleaned_content.lower()
    primary = None
    for change in changes:
        if any(alias and alias.lower() in text for alias in [change.target, *change.aliases]):
            primary = change.target
            break
    domain = "Bug" if any(k in text for k in ("bug", "崩溃", "卡死", "异常")) else "平衡"
    if any(k in text for k in ("服务器", "延迟", "掉线")):
        domain = "服务器与性能"
    elif any(k in text for k in ("匹配", "排位")):
        domain = "匹配与排位"
    elif any(k in text for k in ("外挂", "作弊")):
        domain = "外挂与公平环境"
    support = any(k in text for k in ("支持", "方向对", "合理", "赞成"))
    oppose = any(k in text for k in ("反对", "不该", "改错", "离谱"))
    direction = "支持改动方向" if support else "反对改动方向" if oppose else "对方向没有明确态度"
    intensity = (
        "力度不足" if any(k in text for k in ("不够", "没砍到", "力度不足"))
        else "力度过大" if any(k in text for k in ("过头", "太狠", "力度过大"))
        else "力度适中" if any(k in text for k in ("刚好", "适中"))
        else "不适用"
    )
    root = "产生了新问题" if domain == "Bug" else "原问题仍未解决" if "还" in text or intensity == "力度不足" else "无法判断"
    return CommentAnalysis(
        comment_id=comment.comment_id, primary_target=primary, problem_domain=domain,
        direction_attitude=direction, intensity_attitude=intensity,
        root_issue_status=root, analysis_confidence=0.62, analysis_stage=STAGE_DONE,
        reasoning_summary="演示模式的确定性规则标签，不代表真实模型判断。",
        evidence_quote=comment.cleaned_content[:80],
        suspected_sarcasm=any(k in text for k in ("呵呵", "真棒啊", "笑死")),
    )
