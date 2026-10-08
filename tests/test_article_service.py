"""Change-list editing rules extracted from the version import page.

Identity is the target name: no synthetic ids, and duplicate targets fold into
one another instead of being renumbered.
"""
from src.core.community_aliases import AliasDictionary
from src.core.models import PatchChange
from src.services.article_service import (
    all_confirmed,
    apply_editor_rows,
    confirm_all,
    localize_targets,
    merge_changes,
)


def _change(target: str, **kwargs) -> PatchChange:
    return PatchChange(target=target, change_summary=kwargs.pop("summary", "摘要"), **kwargs)


def _row(target: str, **overrides) -> dict:
    row = {
        "target": target, "category": "英雄", "change_direction": "削弱",
        "change_summary": "Q 冷却 +2s", "design_goal": "", "aliases": "挖机 | Wraith",
        "parse_confidence": 0.8, "confirmed": True, "删除": False, "ability_or_system": "Q",
    }
    row.update(overrides)
    return row


def test_apply_editor_rows_drops_deleted_rows():
    changes = [_change("恶灵"), _change("动力小子")]
    rows = [_row("恶灵"), _row("动力小子", 删除=True)]
    result = apply_editor_rows(changes, rows)
    assert [change.target for change in result] == ["恶灵"]
    assert result[0].aliases == ["挖机", "Wraith"]
    assert result[0].confirmed is True


def test_apply_editor_rows_keeps_the_existing_row_for_a_target():
    """Editing a row in place must not orphan the analyses already mapped to it."""
    existing = _change("恶灵", category="英雄削弱", summary="旧摘要", inference_notes=["手工标注"])
    result = apply_editor_rows([existing], [_row("恶灵", change_summary="新摘要")])
    # Same object, not a rebuilt one: analyses already mapped to 恶灵 stay attached.
    assert result[0] is existing
    assert result[0].change_summary == "新摘要"
    assert result[0].inference_notes == ["手工标注"]


def test_apply_editor_rows_creates_missing_rows():
    result = apply_editor_rows([], [_row("地平线", parse_confidence=None, confirmed=False, ability_or_system="")])
    assert len(result) == 1
    assert result[0].target == "地平线"
    assert result[0].parse_confidence == 0.5


def test_merge_changes_unions_aliases_and_keeps_the_first():
    changes = [_change("瓦尔基里", aliases=["瓦基"]), _change("挖机", aliases=["挖机"])]
    merged = merge_changes(changes, ["瓦尔基里", "挖机"])
    assert len(merged) == 1
    assert merged[0].target == "瓦尔基里"
    # target + every alias from the folded rows, de-duplicated and sorted
    assert merged[0].aliases == ["挖机", "瓦基", "瓦尔基里"]


def test_merge_changes_ignores_single_selection():
    changes = [_change("恶灵"), _change("动力小子")]
    assert merge_changes(changes, ["恶灵"]) == changes


def test_confirm_all_and_all_confirmed():
    changes = [_change("恶灵"), _change("动力小子")]
    assert all_confirmed(changes) is False
    confirm_all(changes)
    assert all_confirmed(changes) is True
    assert all_confirmed([]) is False


def test_localize_targets_switches_to_chinese_and_keeps_english_aliased():
    alias_dict = AliasDictionary({"legends": {"Bloodhound": {"zh": "寻血猎犬", "aliases": ["狗子"]}}})
    changes = [_change("Bloodhound")]

    localize_targets(changes, alias_dict)

    assert changes[0].target == "寻血猎犬"
    assert "Bloodhound" in changes[0].aliases
    # The English name stays matchable, so old analyses and the mapping both work.
    assert "寻血猎犬" in changes[0].aliases


def test_localize_targets_leaves_unknown_targets_alone():
    alias_dict = AliasDictionary({"legends": {"Bloodhound": {"zh": "寻血猎犬", "aliases": []}}})
    changes = [_change("星锚")]

    localize_targets(changes, alias_dict)

    assert changes[0].target == "星锚"


def test_localize_targets_tolerates_a_missing_dictionary():
    changes = [_change("Bloodhound")]
    assert localize_targets(changes, None)[0].target == "Bloodhound"
