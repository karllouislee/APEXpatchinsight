import pytest
from pydantic import ValidationError

from src.core.models import PatchChange


def test_patch_change_coerces_model_string_lists():
    change = PatchChange.model_validate({
        "hero": "Bloodhound",
        "skill": "Passive",
        "summary": "Changed passive behavior.",
        "aliases": "BH",
        "inference_notes": "No numeric value was provided.",
    })
    assert change.aliases == ["BH"]
    assert change.inference_notes == ["No numeric value was provided."]


def test_patch_change_recovers_non_null_aliases_hidden_by_null_hero():
    change = PatchChange.model_validate({
        "hero": None,
        "object": "R-99",
        "summary": "弹匣容量降低。",
        "category": "武器",
        "change_id": None,  # legacy key: accepted and ignored
        "section": None,
        "ability_or_system": None,
        "change_direction": None,
        "design_goal": None,
        "original_problem": None,
        "source_heading": None,
        "source_excerpt": None,
        "exact_values": None,
        "parse_confidence": None,
        "confirmed": None,
        "aliases": None,
        "inference_notes": None,
    })

    assert change.target == "R-99"
    assert change.hero is None
    assert change.entity_type == "武器"
    assert change.section == "未分类"
    assert change.change_direction == "调整"
    assert change.exact_values == []
    assert change.parse_confidence == 0.5
    assert change.confirmed is False


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"target": None, "hero": "Horizon"}, "Horizon"),
        ({"hero": None, "object": "R-301"}, "R-301"),
        ({"target": "", "legend": "Wraith"}, "Wraith"),
    ],
)
def test_patch_change_uses_first_non_empty_target_alias(payload, expected):
    change = PatchChange.model_validate({**payload, "description": "改动摘要"})
    assert change.target == expected


def test_patch_change_marks_missing_target_and_summary_for_review():
    change = PatchChange.model_validate({
        "hero": None,
        "target": None,
        "summary": None,
        "parse_confidence": 0.92,
    })

    assert change.target == "未识别对象"
    assert change.change_summary == "未提供改动摘要"
    assert change.confirmed is False
    assert change.parse_confidence == 0.35
    assert any("target" in note for note in change.inference_notes)


def test_patch_change_accepts_single_exact_value_object_and_numbers():
    change = PatchChange.model_validate({
        "target": "R-99",
        "summary": None,
        "source_excerpt": "伤害从 11 调整为 12。",
        "exact_values": {"before": 11, "after": 12},
    })

    assert change.change_summary == "伤害从 11 调整为 12。"
    assert change.exact_values[0].before == "11"
    assert change.exact_values[0].after == "12"


def test_patch_change_keeps_non_null_invalid_structures_strict():
    with pytest.raises(ValidationError):
        PatchChange.model_validate({
            "target": {"name": "R-99"},
            "summary": "改动摘要",
            "exact_values": "invalid",
        })