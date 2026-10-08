from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

from ..core.models import QUALITY_RULES, ChoiceRules, CleanComment, PatchChange, normalize_choice
from ..integrations.siliconflow_client import SiliconFlowClient, load_prompt

Direction = Literal["继续观察", "保留当前方向", "适度回调", "调整改动机制", "优先修复Bug", "补充官方说明", "区分玩家水平进一步验证", "暂无足够证据"]

DIRECTION_SUGGESTION_RULES: ChoiceRules = [
    (("修复", "bug"), "优先修复Bug"),
    (("回调", "回退", "撤销"), "适度回调"),
    (("调整改动机制", "调整机制", "改机制"), "调整改动机制"),
    (("官方说明", "说明", "公告", "文档"), "补充官方说明"),
    (("分层", "玩家水平", "区分"), "区分玩家水平进一步验证"),
    (("保留", "维持", "保持"), "保留当前方向"),
    (("证据不足", "不足", "暂无"), "暂无足够证据"),
    (("观察",), "继续观察"),
]


class Insight(BaseModel):
    # Keyed by target name: that is the granularity at which the corpus is
    # aggregated, and the only label a reader recognises.
    target: str = Field(default="", validation_alias=AliasChoices("target", "change_id", "change_key"))
    observation: str
    evidence_comment_ids: list[str] = Field(default_factory=list)
    inference: str
    validation_direction: Direction
    internal_data_needed: list[str] = Field(default_factory=list)
    confidence: Literal["高", "中", "低"]
    limitations: str

    @field_validator("evidence_comment_ids", "internal_data_needed", mode="before")
    @classmethod
    def coerce_string_lists(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("validation_direction", mode="before")
    @classmethod
    def coerce_direction(cls, value):
        return normalize_choice(value, DIRECTION_SUGGESTION_RULES, "继续观察")

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value):
        return normalize_choice(value, QUALITY_RULES, "中")


def generate_with_ai(changes: list[PatchChange], aggregate_result: dict[str, Any], comments: list[CleanComment], client: SiliconFlowClient) -> list[Insight]:
    lookup = {comment.comment_id: comment for comment in comments}
    representatives = []
    for metrics in aggregate_result.get("targets", {}).values():
        for comment_id in metrics.get("representative_comment_ids", [])[:5]:
            if comment_id in lookup:
                representatives.append({"comment_id": comment_id, "text": lookup[comment_id].cleaned_content})
    payload = {
        "official_changes": [change.model_dump(mode="json") for change in changes],
        "program_statistics": aggregate_result,
        "representative_comments": representatives[:50],
        "sample_limitations": "社区截图为用户主动上传的便利样本，不能代表全部玩家。",
    }
    return client.text_json(load_prompt("validation_direction_prompt.txt"), payload, list[Insight])


def deterministic_insights(changes: list[PatchChange], aggregate_result: dict[str, Any]) -> list[Insight]:
    output: list[Insight] = []
    for target, metrics in aggregate_result.get("targets", {}).items():
        count = metrics.get("related_count", 0)
        ids = metrics.get("representative_comment_ids", [])
        if count < 5:
            observation = "当前社区样本不足以支持明确方向，建议继续收集反馈，并结合内部行为数据验证。"
            direction: Direction = "暂无足够证据"
            confidence = "低"
        elif metrics.get("new_problem_rate", {}).get("rate", 0) and metrics["new_problem_rate"]["rate"] >= 0.2:
            observation = "样本中出现了需要优先排查的新问题反馈。"
            direction = "优先修复Bug"
            confidence = "中"
        elif metrics.get("intensity_insufficient", {}).get("rate", 0) and metrics["intensity_insufficient"]["rate"] >= 0.4:
            observation = "样本较多认为改动方向可理解，但力度仍不足。"
            direction = "继续观察"
            confidence = "中"
        else:
            observation = "当前样本未形成足以支持具体回调的单一结论。"
            direction = "继续观察"
            confidence = "中"
        output.append(Insight(
            target=target, observation=observation, evidence_comment_ids=ids,
            inference="该判断仅用于形成下一轮验证假设，不替代游戏内行为数据。",
            validation_direction=direction,
            internal_data_needed=["按玩家水平分层的选取率与胜率", "技能使用频率", "异常与崩溃日志"],
            confidence=confidence, limitations="截图便利样本存在平台构成、选择与上下文缺失偏差。",
        ))
    return output

