from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

ProblemDomain = Literal["平衡", "Bug", "服务器与性能", "外挂与公平环境", "匹配与排位", "交互与体验", "商业化", "与版本无关", "无法判断"]
DirectionAttitude = Literal["支持改动方向", "反对改动方向", "对方向没有明确态度", "无法判断"]
IntensityAttitude = Literal["力度不足", "力度适中", "力度过大", "不适用", "无法判断"]
OverallStance = Literal["支持", "反对", "条件性支持", "需要继续观察", "仅描述现象", "玩梗或无有效信息", "与当前改动无关", "无法判断"]
RootIssueStatus = Literal["原问题已缓解", "原问题部分缓解", "原问题仍未解决", "产生了新问题", "无法判断"]
InformationQuality = Literal["高", "中", "低"]

AnalysisStage = Literal["未开始", "已归类", "已完成"]
# Two-stage analysis. Stage 1 only decides *what* a comment talks about, so the
# project gets a topic-heat reading before any attitude is judged; stage 2 then
# walks one change item at a time.
STAGE_PENDING = "未开始"
STAGE_TOPIC = "已归类"
STAGE_DONE = "已完成"

# Output budget for the two free-text fields on CommentAnalysis. These are the
# only unbounded strings the model emits, so they are where output tokens leak.
# The analysis prompt asks for the same limits; the model clamps as a backstop.
MAX_REASONING_SUMMARY_CHARS = 40
MAX_EVIDENCE_QUOTE_CHARS = 24
MAX_PROBLEM_REASONS = 2
MAX_PROBLEM_REASON_CHARS = 12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Enum coercion -----------------------------------------------------------
# LLMs rarely reproduce Literal vocabularies exactly ('游戏平衡' vs '平衡',
# '支持' vs '支持改动方向'). Normalize near-miss values BEFORE validation so a
# single sloppy label cannot kill a whole paid API batch.

ChoiceRules = list[tuple[tuple[str, ...], str]]


def normalize_choice(value: Any, rules: ChoiceRules, fallback: str) -> str:
    """Map a free-form model label to the closest allowed Literal value.

    ``rules`` is an ordered list of (keywords, canonical) pairs; the first
    pair whose any keyword is contained in the input wins. Put negative/
    specific keywords before generic ones ('不支持' before '支持').
    """
    if not isinstance(value, str):
        return fallback
    text = value.strip()
    canonical = {choice for _, choice in rules}
    if text in canonical:
        return text
    lowered = text.lower()
    for keywords, choice in rules:
        if any(keyword.lower() in lowered for keyword in keywords):
            return choice
    return fallback


DOMAIN_RULES: ChoiceRules = [
    (("外挂", "作弊", "公平环境", "封号", "封禁", "宏孩儿"), "外挂与公平环境"),
    (("服务器", "性能", "延迟", "掉线", "卡顿", "帧率", "fps"), "服务器与性能"),
    (("匹配", "排位", "天梯", "mmr", "elo"), "匹配与排位"),
    (("商业化", "氪金", "皮肤", "付费", "收费", "商城", "内购", "通行证"), "商业化"),
    (("bug", "故障", "崩溃", "闪退", "报错", "异常", "卡死"), "Bug"),
    (("交互", "体验", "界面", "ui", "操作", "手感"), "交互与体验"),
    (("平衡", "数值", "机制", "强度", "削弱", "加强", "nerf", "buff"), "平衡"),
    (("无关",), "与版本无关"),
]

DIRECTION_RULES: ChoiceRules = [
    (("不支持", "反对", "抵制", "不认可", "负面", "差评"), "反对改动方向"),
    (("支持", "赞成", "赞同", "认可", "合理", "正面", "肯定"), "支持改动方向"),
    (("中立", "没有明确", "不明确", "观望", "无所谓"), "对方向没有明确态度"),
]

INTENSITY_RULES: ChoiceRules = [
    (("不足", "不够", "偏弱", "太轻", "较轻", "低"), "力度不足"),
    (("过大", "过度", "过头", "太狠", "过猛", "太强", "过高"), "力度过大"),
    (("适中", "中等", "合适", "恰当", "刚好", "适度"), "力度适中"),
    (("不适用", "不涉及", "无关"), "不适用"),
]

STANCE_RULES: ChoiceRules = [
    (("条件",), "条件性支持"),
    (("观察", "观望"), "需要继续观察"),
    (("玩梗", "无有效", "复读", "灌水"), "玩梗或无有效信息"),
    (("无关",), "与当前改动无关"),
    (("描述", "现象", "陈述"), "仅描述现象"),
    (("不支持", "反对", "差评"), "反对"),
    (("支持", "赞同", "赞成", "点赞"), "支持"),
]

ROOT_STATUS_RULES: ChoiceRules = [
    (("部分",), "原问题部分缓解"),
    (("新问题", "产生", "引入", "带来"), "产生了新问题"),
    (("未解决", "没解决", "没有解决", "仍未", "依旧", "依然"), "原问题仍未解决"),
    (("已解决", "已缓解", "解决", "缓解", "修复"), "原问题已缓解"),
]

QUALITY_RULES: ChoiceRules = [
    (("高", "详细", "具体"), "高"),
    (("低", "少", "模糊"), "低"),
    (("中", "一般", "普通"), "中"),
]


class ExactValue(BaseModel):
    # Preserve relative measurements without inventing endpoints.
    raw_text: str = ''

    @model_validator(mode='before')
    @classmethod
    def preserve_text_value(cls, value):
        if isinstance(value, str):
            return {'raw_text': value}
        return value

    before: str | None = None
    after: str | None = None

    @field_validator("before", "after", mode="before")
    @classmethod
    def coerce_scalar_values(cls, value):
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return str(value).strip()
        return value


class PatchChange(BaseModel):
    # A change is identified by its target name, not by a synthetic id: that is
    # what both the patch notes and the community actually talk about.
    section: str = "未分类"
    category: str = "其他"
    entity_type: str = "其他"
    target: str = Field(default="", validation_alias=AliasChoices("target", "object", "legend"))
    hero: str | None = None
    ability_or_system: str = Field(default="", validation_alias=AliasChoices("ability_or_system", "ability", "skill", "system"))
    change_direction: str = "调整"
    change_summary: str = Field(default="", validation_alias=AliasChoices("change_summary", "summary", "change", "description"))
    design_goal: str = ""
    original_problem: str = ""
    exact_values: list[ExactValue] = Field(default_factory=list)
    source_heading: str = ""
    source_excerpt: str = ""
    aliases: list[str] = Field(default_factory=list)
    parse_confidence: float = Field(default=0.5, ge=0, le=1)
    inference_notes: list[str] = Field(default_factory=list)
    confirmed: bool = False

    @property
    def change_key(self) -> str:
        """Stable identity: the target name, qualified by the ability when set.

        Several changes routinely share one target (all four Bloodhound
        abilities), so the ability is part of the key. Derived only from stored
        fields, never from the live alias dictionary — editing slang must not
        silently re-key analyses that already exist.
        """
        target = (self.target or "").strip() or "未识别对象"
        ability = (self.ability_or_system or "").strip()
        return f"{target} · {ability}" if ability else target

    @model_validator(mode="before")
    @classmethod
    def coerce_model_payload(cls, value):
        """Normalize PatchChange-specific LLM near misses before validation."""
        if not isinstance(value, dict):
            return value
        data = dict(value)

        def first_text(keys: tuple[str, ...]) -> str | None:
            for key in keys:
                candidate = data.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            return None

        def first_invalid(keys: tuple[str, ...]):
            for key in keys:
                if key in data and data[key] is not None and not isinstance(data[key], str):
                    return data[key]
            return None

        review_notes: list[str] = []
        target = first_text(("target", "object", "legend", "hero"))
        if target:
            data["target"] = target
        else:
            invalid_target = first_invalid(("target", "object", "legend", "hero"))
            if invalid_target is not None:
                data["target"] = invalid_target
            else:
                data["target"] = "未识别对象"
                review_notes.append("模型未提供改动对象 target，需人工确认。")

        summary = first_text(("change_summary", "summary", "change", "description"))
        summary = summary or first_text(("source_excerpt",))
        if summary:
            data["change_summary"] = summary
        else:
            invalid_summary = first_invalid(("change_summary", "summary", "change", "description"))
            if invalid_summary is not None:
                data["change_summary"] = invalid_summary
            else:
                data["change_summary"] = "未提供改动摘要"
                review_notes.append("模型未提供改动摘要，需人工确认。")

        defaults = {
            "section": "未分类",
            "category": "其他",
            "entity_type": "其他",
            "ability_or_system": "",
            "change_direction": "调整",
            "design_goal": "",
            "original_problem": "",
            "source_heading": "",
            "source_excerpt": "",
            "exact_values": [],
            "parse_confidence": 0.5,
            "confirmed": False,
        }
        for key, default in defaults.items():
            if data.get(key) is None:
                data[key] = list(default) if isinstance(default, list) else default
        if isinstance(data.get("exact_values"), dict):
            data["exact_values"] = [data["exact_values"]]
        if data.get("hero") == "":
            data["hero"] = None

        category = str(data.get("category") or "")
        if data.get("entity_type") == "其他":
            if first_text(("hero",)) or any(word in category for word in ("英雄", "传奇")):
                data["entity_type"] = "英雄"
            else:
                for keyword, entity_type in (
                    ("武器", "武器"), ("装备", "装备"), ("地图", "地图"),
                    ("模式", "模式"), ("系统", "系统"), ("Bug", "Bug"), ("修复", "Bug"),
                ):
                    if keyword.casefold() in category.casefold():
                        data["entity_type"] = entity_type
                        break
        if data.get("entity_type") == "英雄" and not first_text(("hero",)):
            if isinstance(data.get("target"), str) and data["target"] != "未识别对象":
                data["hero"] = data["target"]

        if review_notes:
            notes = data.get("inference_notes")
            if notes is None or notes == "":
                notes = []
            elif isinstance(notes, str):
                notes = [notes]
            elif isinstance(notes, list):
                notes = list(notes)
            data["inference_notes"] = notes + review_notes if isinstance(notes, list) else notes
            data["confirmed"] = False
            try:
                data["parse_confidence"] = min(float(data.get("parse_confidence", 0.5)), 0.35)
            except (TypeError, ValueError):
                data["parse_confidence"] = 0.35
        return data
    @field_validator("inference_notes", "aliases", mode="before")
    @classmethod
    def coerce_string_lists(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return value


class Article(BaseModel):
    title: str
    url: str
    published_at: str | None = None
    fetched_at: str = Field(default_factory=utc_now)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    text: str = ""


class RawComment(BaseModel):
    # ``screenshot_filename`` is accepted for corpora saved before screenshots
    # were dropped from the product.
    model_config = ConfigDict(populate_by_name=True)

    comment_id: str = ""
    local_index: int
    platform: str
    content: str
    likes: int | None = None
    is_reply: bool = False
    reply_context: str | None = None
    is_complete: bool = True
    language: str = "zh"
    source_file: str = Field(default="", validation_alias=AliasChoices("source_file", "screenshot_filename"))
    source_type: str = "csv"
    source_url: str = ""
    source_comment_key: str = ""
    published_at: str = ""


class CleanComment(RawComment):
    original_content: str = ""
    cleaned_content: str = ""
    is_valid: bool = True
    invalid_reason: str | None = None
    duplicate_of: str | None = None
    suspected_duplicate: bool = False
    manual_keywords: list[str] = Field(default_factory=list)

    @field_validator("manual_keywords", mode="before")
    @classmethod
    def coerce_manual_keywords(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        return value

class CommentAnalysis(BaseModel):
    """One comment's classification.

    Only the fields that need language understanding are model-produced; the
    rest are derived deterministically (see :func:`derive_derived_fields`),
    which keeps the LLM output small and the taxonomy internally consistent.
    """

    comment_id: str
    # Where this row sits in the two-stage run. Legacy rows (produced by the old
    # one-shot prompt) are complete, so an absent key means 已完成 rather than
    # 未开始 — otherwise every existing analysis would go back into the queue.
    analysis_stage: AnalysisStage = STAGE_PENDING
    # Target names, not change ids — these are what the model can actually read
    # out of a comment, and they survive re-structuring the change list.
    primary_target: str | None = None
    secondary_targets: list[str] = Field(default_factory=list)
    problem_domain: ProblemDomain = "无法判断"
    problem_reason: list[str] = Field(default_factory=list)
    direction_attitude: DirectionAttitude = "无法判断"
    intensity_attitude: IntensityAttitude = "无法判断"
    overall_stance: OverallStance = "无法判断"
    root_issue_status: RootIssueStatus = "无法判断"
    information_quality: InformationQuality = "中"
    analysis_confidence: float = Field(default=0.5, ge=0, le=1)
    reasoning_summary: str = ""
    evidence_quote: str = ""
    suspected_sarcasm: bool = False

    @field_validator("analysis_stage", mode="before")
    @classmethod
    def coerce_stage(cls, value):
        return normalize_choice(value, [((STAGE_TOPIC,), STAGE_TOPIC), ((STAGE_DONE,), STAGE_DONE)], STAGE_PENDING)

    @model_validator(mode="before")
    @classmethod
    def default_legacy_stage(cls, value):
        """Rows saved before the two-stage split carry no stage; treat them as done."""
        if isinstance(value, dict) and "analysis_stage" not in value:
            data = dict(value)
            data["analysis_stage"] = STAGE_DONE
            return data
        return value

    @field_validator("problem_reason", "secondary_targets", mode="before")
    @classmethod
    def coerce_string_lists(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            # Models routinely emit "数值膨胀、机动性过高" where the schema wants
            # a list. Splitting keeps both items instead of mangling them into
            # one, which is what a plain length clamp would do.
            parts = [part.strip() for part in re.split(r"[、，,；;/]+", value)]
            return [part for part in parts if part]
        return value

    @field_validator("reasoning_summary", "evidence_quote", mode="before")
    @classmethod
    def clip_free_text(cls, value):
        """Keep the two free-text fields inside the budget the prompt asks for.

        Clamping beats rejecting: a verbose model should not cost the whole
        batch, and truncation keeps ``evidence_quote`` a prefix of the original
        so quote verification still passes.
        """
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("reasoning_summary", mode="after")
    @classmethod
    def limit_reasoning_summary(cls, value: str) -> str:
        return value[:MAX_REASONING_SUMMARY_CHARS]

    @field_validator("evidence_quote", mode="after")
    @classmethod
    def limit_evidence_quote(cls, value: str) -> str:
        return value[:MAX_EVIDENCE_QUOTE_CHARS]

    @field_validator("problem_reason", mode="after")
    @classmethod
    def limit_problem_reasons(cls, value: list[str]) -> list[str]:
        return [item[:MAX_PROBLEM_REASON_CHARS] for item in value[:MAX_PROBLEM_REASONS]]

    @field_validator("problem_domain", mode="before")
    @classmethod
    def coerce_domain(cls, value):
        return normalize_choice(value, DOMAIN_RULES, "无法判断")

    @field_validator("direction_attitude", mode="before")
    @classmethod
    def coerce_direction(cls, value):
        return normalize_choice(value, DIRECTION_RULES, "无法判断")

    @field_validator("intensity_attitude", mode="before")
    @classmethod
    def coerce_intensity(cls, value):
        return normalize_choice(value, INTENSITY_RULES, "无法判断")

    @field_validator("overall_stance", mode="before")
    @classmethod
    def coerce_stance(cls, value):
        return normalize_choice(value, STANCE_RULES, "无法判断")

    @field_validator("root_issue_status", mode="before")
    @classmethod
    def coerce_root_status(cls, value):
        return normalize_choice(value, ROOT_STATUS_RULES, "无法判断")

    @field_validator("information_quality", mode="before")
    @classmethod
    def coerce_quality(cls, value):
        return normalize_choice(value, QUALITY_RULES, "中")


def derive_stance(direction: str, intensity: str, domain: str) -> str:
    """Overall stance from the two attitudes the model actually judges.

    Asking the model for a stance *and* the two attitudes behind it invites
    contradictions; deriving it keeps the taxonomy self-consistent.
    """
    if domain == "与版本无关":
        return "与当前改动无关"
    if direction == "支持改动方向":
        if intensity in {"力度不足", "力度过大"}:
            return "条件性支持"
        return "支持"
    if direction == "反对改动方向":
        return "反对"
    if direction == "对方向没有明确态度":
        return "仅描述现象"
    return "无法判断"


def derive_root_status(direction: str, intensity: str, domain: str) -> str:
    if domain == "Bug":
        return "产生了新问题"
    if direction == "支持改动方向" and intensity in {"力度适中", "不适用"}:
        return "原问题已缓解"
    if direction == "支持改动方向":
        return "原问题部分缓解"
    if direction == "反对改动方向":
        return "原问题仍未解决"
    return "无法判断"


def derive_information_quality(content: str) -> str:
    length = len((content or "").strip())
    return "高" if length >= 30 else "中" if length >= 12 else "低"


def derive_problem_reasons(domain: str, intensity: str) -> list[str]:
    reasons: list[str] = []
    if domain == "Bug":
        reasons.append("Bug或异常")
    if intensity == "力度不足":
        reasons.append("改动未触及核心问题")
    elif intensity == "力度过大":
        reasons.append("改动矫枉过正")
    return reasons


def apply_derived_fields(analysis: "CommentAnalysis", content: str) -> "CommentAnalysis":
    """Fill the fields the model is no longer asked to emit.

    Stance, root status and problem reasons describe an *attitude*, so they stay
    blank until stage 2 has judged one — a half-analysed row must not look like
    a considered verdict. Information quality is purely mechanical (length), so
    it is set at any stage.

    Runs after validation so a hand-edited value in the review panel is never
    overwritten — only fields still sitting on a default get derived.
    """
    if content:
        analysis.information_quality = derive_information_quality(content)
    if analysis.analysis_stage != STAGE_DONE:
        return analysis
    if analysis.overall_stance == "无法判断":
        analysis.overall_stance = derive_stance(
            analysis.direction_attitude, analysis.intensity_attitude, analysis.problem_domain
        )
    if analysis.root_issue_status == "无法判断":
        analysis.root_issue_status = derive_root_status(
            analysis.direction_attitude, analysis.intensity_attitude, analysis.problem_domain
        )
    if not analysis.problem_reason:
        analysis.problem_reason = derive_problem_reasons(analysis.problem_domain, analysis.intensity_attitude)
    return analysis


class ReviewRecord(BaseModel):
    comment_id: str
    reasons: list[str] = Field(default_factory=list)
    original: dict[str, Any] = Field(default_factory=dict)
    corrected: dict[str, Any] = Field(default_factory=dict)
    changed_fields: list[str] = Field(default_factory=list)
    modified_at: str | None = None


class ValidationRecord(BaseModel):
    comment_id: str
    text_accepted: bool | None = None
    mapping_accepted: bool | None = None
    attitude_accepted: bool | None = None
    domain_accepted: bool | None = None
    evidence_traceable: bool | None = None
    dedup_accepted: bool | None = None


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str = "demo-apex-patch"
    name: str = "Apex Patch Feedback Copilot"
    is_demo: bool = False
    demo_disclaimer: str = ""
    article: Article | None = None
    changes: list[PatchChange] = Field(default_factory=list)
    comments: list[CleanComment] = Field(default_factory=list)
    analyses: list[CommentAnalysis] = Field(default_factory=list)
    reviews: list[ReviewRecord] = Field(default_factory=list)
    # Comment ids the reviewer chose to skip. Survives queue rebuilds (the
    # queue is recomputed on every refresh) until the analysis is cleared or
    # the skips are restored by hand.
    skipped_reviews: list[str] = Field(default_factory=list)
    review_history: list[ReviewRecord] = Field(default_factory=list)
    validations: list[ValidationRecord] = Field(default_factory=list)
    insights: dict[str, Any] = Field(default_factory=dict)
    # Cached output of the review-learning step: {"digest": str, "rules": [str],
    # "updated_at": str}. Keyed by a fingerprint of the correction trail so new
    # reviews invalidate it automatically.
    review_lessons: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

