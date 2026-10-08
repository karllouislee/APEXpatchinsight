"""Human corrections must become prompt guidance, not just an audit row."""
from src.core.models import Project, ReviewRecord
from src.core.review_lessons import (
    build_lessons,
    correction_digest,
    correction_summary,
    deterministic_lessons,
    iter_corrections,
)
from src.services.review_learning import cached_rules, clear_cache, lesson_block


def _record(field: str, old, new, text: str = "砍了跟没砍一样") -> ReviewRecord:
    original = {
        "comment": {"cleaned_content": text},
        "analysis": {"primary_target": None, "direction_attitude": "无法判断", "suspected_sarcasm": False, field: old},
    }
    corrected = {**original, "analysis": {**original["analysis"], field: new}}
    return ReviewRecord(
        comment_id="COM-0001",
        reasons=["测试"],
        original=original,
        corrected=corrected,
        changed_fields=[f"analysis.{field}"],
        modified_at="2026-09-04T10:00:00+00:00",
    )


def test_corrections_are_read_out_of_the_audit_trail():
    record = _record("direction_attitude", "对方向没有明确态度", "反对改动方向")
    corrections = iter_corrections([record])
    assert len(corrections) == 1
    assert corrections[0].field == "direction_attitude"
    assert corrections[0].old == "对方向没有明确态度"
    assert corrections[0].new == "反对改动方向"
    assert corrections[0].example == "砍了跟没砍一样"


def test_booleans_and_empty_values_read_as_chinese_labels():
    corrections = iter_corrections([_record("primary_target", None, "寻血猎犬")])
    assert corrections[0].old == "未识别"
    assert corrections[0].new == "寻血猎犬"

    corrections = iter_corrections([_record("suspected_sarcasm", False, True)])
    assert corrections[0].old == "否"
    assert corrections[0].new == "是"


def test_a_single_correction_is_not_yet_a_pattern():
    lessons = build_lessons([_record("direction_attitude", "对方向没有明确态度", "反对改动方向")])
    assert lessons == []


def test_repeated_corrections_become_a_rule_with_examples():
    records = [
        _record("direction_attitude", "对方向没有明确态度", "反对改动方向", "这改动有啥用"),
        _record("direction_attitude", "对方向没有明确态度", "反对改动方向", "等于没改"),
        _record("direction_attitude", "对方向没有明确态度", "反对改动方向", "完全没影响"),
    ]
    lessons = build_lessons(records)
    assert len(lessons) == 1
    assert lessons[0].count == 3
    # Two examples only: the block has to stay inside the prompt budget.
    assert len(lessons[0].examples) == 2
    assert "人工由「对方向没有明确态度」改为「反对改动方向」（3 例）" in lessons[0].render()


def test_lessons_block_is_empty_without_review_history():
    assert deterministic_lessons(Project()) == ([], "")


def test_lessons_block_is_prompt_injectable():
    project = Project(review_history=[
        _record("intensity_attitude", "力度适中", "力度不足"),
        _record("intensity_attitude", "力度适中", "力度不足"),
    ])
    lessons, block = deterministic_lessons(project)
    assert len(lessons) == 1
    assert block.startswith("【人工复核经验】")
    assert "力度不足" in block


def test_digest_changes_when_new_corrections_arrive():
    project = Project(review_history=[_record("problem_domain", "平衡", "Bug")])
    before = correction_digest(project)
    project.review_history.append(_record("problem_domain", "平衡", "Bug"))
    assert correction_digest(project) != before


def test_summary_counts_are_stable_for_the_ui():
    project = Project(review_history=[
        _record("problem_domain", "平衡", "Bug"),
        _record("problem_domain", "平衡", "Bug"),
    ])
    assert correction_summary(project) == {"复核记录": 2, "修正字段": 2, "归纳规律": 1}


class StubClient:
    def __init__(self, rules=None, fail=False):
        self.rules = rules
        self.fail = fail
        self.calls = 0

    def text_json(self, prompt, payload, output_type):
        self.calls += 1
        if self.fail:
            from src.integrations.siliconflow_client import SiliconFlowError
            raise SiliconFlowError("上游不可用")
        return output_type.model_validate({"rules": self.rules or ["遇到“没感觉”应判为力度不足"]})


def _reviewed_project() -> Project:
    return Project(review_history=[
        _record("intensity_attitude", "力度适中", "力度不足"),
        _record("intensity_attitude", "力度适中", "力度不足"),
    ])


def test_lesson_block_falls_back_to_rules_without_a_client():
    block, source = lesson_block(_reviewed_project())
    assert source == "rules"
    assert "【人工复核经验】" in block


def test_lesson_block_uses_the_model_and_caches_the_result():
    project = _reviewed_project()
    client = StubClient()

    first, source = lesson_block(project, client)
    assert source == "model"
    assert "没感觉" in first
    assert client.calls == 1

    # Cache keyed on the correction digest: no second request for the same trail.
    second, _ = lesson_block(project, client)
    assert second == first
    assert client.calls == 1
    assert cached_rules(project) == ["遇到“没感觉”应判为力度不足"]


def test_new_corrections_invalidate_the_cache():
    project = _reviewed_project()
    client = StubClient(rules=["规则 v1"])
    lesson_block(project, client)
    project.review_history.append(_record("intensity_attitude", "力度适中", "力度不足"))

    lesson_block(project, client)
    assert client.calls == 2


def test_a_failed_summarisation_never_blocks_the_run():
    project = _reviewed_project()
    block, source = lesson_block(project, StubClient(fail=True))
    assert source == "rules"
    assert "【人工复核经验】" in block


def test_clear_cache_drops_the_rules():
    project = _reviewed_project()
    lesson_block(project, StubClient())
    clear_cache(project)
    assert cached_rules(project) == []
