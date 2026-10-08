"""Coercion tests: every input_value from the real 42-error production failure."""

from src.services.insight_generator import Insight
from src.core.models import CommentAnalysis


def make_analysis(**overrides):
    payload = {"comment_id": "COM-0001"}
    payload.update(overrides)
    return CommentAnalysis.model_validate(payload)


def test_problem_domain_near_misses():
    assert make_analysis(problem_domain="游戏平衡").problem_domain == "平衡"
    assert make_analysis(problem_domain="游戏机制").problem_domain == "平衡"
    assert make_analysis(problem_domain="游戏体验").problem_domain == "交互与体验"
    assert make_analysis(problem_domain="匹配机制").problem_domain == "匹配与排位"
    assert make_analysis(problem_domain="网络卡顿").problem_domain == "服务器与性能"
    assert make_analysis(problem_domain="莫名其妙").problem_domain == "无法判断"


def test_direction_attitude_near_misses():
    assert make_analysis(direction_attitude="支持").direction_attitude == "支持改动方向"
    assert make_analysis(direction_attitude="不支持").direction_attitude == "反对改动方向"
    assert make_analysis(direction_attitude="负面").direction_attitude == "反对改动方向"
    assert make_analysis(direction_attitude="中立").direction_attitude == "对方向没有明确态度"


def test_intensity_attitude_near_misses():
    assert make_analysis(intensity_attitude="中等").intensity_attitude == "力度适中"
    assert make_analysis(intensity_attitude="低").intensity_attitude == "力度不足"
    assert make_analysis(intensity_attitude="过猛").intensity_attitude == "力度过大"


def test_overall_stance_near_misses():
    assert make_analysis(overall_stance="中立").overall_stance == "无法判断"
    assert make_analysis(overall_stance="支持").overall_stance == "支持"
    assert make_analysis(overall_stance="有条件支持").overall_stance == "条件性支持"


def test_root_issue_status_near_misses():
    assert make_analysis(root_issue_status="已解决").root_issue_status == "原问题已缓解"
    assert make_analysis(root_issue_status="未解决").root_issue_status == "原问题仍未解决"
    assert make_analysis(root_issue_status="部分缓解").root_issue_status == "原问题部分缓解"


def test_problem_reason_string_coerced_to_list():
    # A model that joins several reasons into one string should still yield
    # separate items rather than a single mangled label.
    result = make_analysis(problem_reason="数值膨胀、机动性过高")
    assert result.problem_reason == ["数值膨胀", "机动性过高"]
    assert make_analysis(problem_reason=None).problem_reason == []
    assert make_analysis(problem_reason=["a", "b"]).problem_reason == ["a", "b"]


def test_canonical_values_pass_through_unchanged():
    analysis = make_analysis(
        problem_domain="外挂与公平环境",
        direction_attitude="反对改动方向",
        intensity_attitude="不适用",
        overall_stance="需要继续观察",
        root_issue_status="产生了新问题",
        information_quality="高",
    )
    assert analysis.problem_domain == "外挂与公平环境"
    assert analysis.direction_attitude == "反对改动方向"
    assert analysis.intensity_attitude == "不适用"
    assert analysis.overall_stance == "需要继续观察"
    assert analysis.root_issue_status == "产生了新问题"
    assert analysis.information_quality == "高"


def test_insight_coercion():
    insight = Insight.model_validate({
        "target": "C1", "observation": "o", "inference": "i",
        "validation_direction": "建议回调", "confidence": "较高",
        "limitations": "l", "evidence_comment_ids": "COM-0001",
    })
    assert insight.target == "C1"
    assert insight.validation_direction == "适度回调"
    assert insight.confidence == "高"
    assert insight.evidence_comment_ids == ["COM-0001"]


def test_insight_accepts_legacy_change_id_key():
    """Projects saved before targets replaced ids still load."""
    insight = Insight.model_validate({
        "change_id": "CHG-001", "observation": "o", "inference": "i",
        "validation_direction": "继续观察", "confidence": "中", "limitations": "l",
    })
    assert insight.target == "CHG-001"
