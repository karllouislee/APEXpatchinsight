"""The two-stage request payloads must carry enough context and nothing else.

Stage 1 decides *what* a comment talks about; stage 2 decides *what it thinks*,
one target at a time. Both share the same guard rails: sequence numbers instead
of ids, an explicit output contract, and a reconciled quote.
"""
from src.core.models import CleanComment, PatchChange
from src.services.comment_analyzer import (
    ATTITUDE_KEYS,
    TOPIC_KEYS,
    analyze_attitude_batch,
    analyze_topic_batch,
    build_attitude_payload,
    build_topic_payload,
    change_brief,
    comment_rows,
)


def _topic_row(n: int, **overrides) -> dict:
    row = {"n": n, "tg": "地平线", "m": "平衡", "q": "力度不足", "c": 0.8}
    row.update(overrides)
    return row


def _attitude_row(n: int, **overrides) -> dict:
    row = {"n": n, "d": "反对改动方向", "i": "力度不足", "q": "力度不足", "c": 0.8, "s": False}
    row.update(overrides)
    return row


class FakeClient:
    """Records payloads and returns canned rows."""

    def __init__(self, rows):
        self.payloads = []
        self.rows = rows

    def text_json(self, prompt, payload, output_type):
        self.payloads.append(payload)
        return self.rows


def _comment(index, target: str | None = None, **overrides) -> CleanComment:
    values = dict(
        comment_id=f"COM-{index:04d}",
        source_file="a.csv",
        local_index=index,
        platform="B站",
        content="方向对但力度不足",
        cleaned_content="方向对但力度不足",
        likes=32,
        is_reply=True,
        reply_context="上一条在讨论地平线",
        manual_keywords=["反讽", "地平线"],
    )
    values.update(overrides)
    return CleanComment(**values)


# --- shared payload shape ----------------------------------------------------


def test_comment_rows_use_sequence_numbers_not_ids():
    rows, _ = comment_rows([_comment(1), _comment(2)])
    assert [row["n"] for row in rows] == [1, 2]
    assert all("comment_id" not in row for row in rows)


def test_comment_rows_carry_context_and_skip_empty_fields():
    rows, _ = comment_rows([_comment(1)])
    assert rows[0]["t"] == "方向对但力度不足"
    assert rows[0]["p"] == "B站"
    assert rows[0]["lk"] == 32
    assert rows[0]["r"] == "上一条在讨论地平线"
    assert rows[0]["kw"] == ["反讽", "地平线"]


def test_empty_fields_are_omitted_instead_of_sent_as_null():
    rows, _ = comment_rows([_comment(1, likes=None, reply_context=None, manual_keywords=[], platform="")])
    assert set(rows[0]) == {"n", "t"}


def test_shared_source_file_is_hoisted_out_of_the_rows():
    rows, shared = comment_rows([_comment(1), _comment(2)])
    assert shared == "a.csv"
    assert all("f" not in row for row in rows)


def test_change_brief_collapses_several_ability_rows_into_one_target():
    """Four Bloodhound rows would force the model to re-decide which ability a
    comment meant — repeated reasoning that buys nothing."""
    changes = [
        PatchChange(target="寻血猎犬", ability_or_system="战术技能", change_direction="削弱", change_summary="扫描冷却加长"),
        PatchChange(target="寻血猎犬", ability_or_system="终极技能", change_direction="削弱", change_summary="移速降低"),
    ]
    brief = change_brief(changes)

    assert len(brief) == 1
    assert brief[0]["tg"] == "寻血猎犬"
    assert brief[0]["dir"] == "削弱"
    assert "战术技能" in brief[0]["sum"] and "终极技能" in brief[0]["sum"]


def test_change_brief_omits_direction_when_a_target_has_conflicting_rows():
    changes = [
        PatchChange(target="寻血猎犬", change_direction="削弱", change_summary="a"),
        PatchChange(target="寻血猎犬", change_direction="增强", change_summary="b"),
    ]
    assert "dir" not in change_brief(changes)[0]


def test_change_brief_uses_chinese_target_names_when_the_dictionary_knows_them():
    from src.core.community_aliases import AliasDictionary

    alias_dict = AliasDictionary({"legends": {"Bloodhound": {"zh": "寻血猎犬", "aliases": ["狗子"]}}})
    assert change_brief([PatchChange(target="Bloodhound", change_summary="x")], alias_dict)[0]["tg"] == "寻血猎犬"


# --- stage 1: topic ----------------------------------------------------------


def test_topic_payload_carries_every_target_and_the_comments():
    changes = [PatchChange(target="地平线", change_summary="冷却加长")]
    payload = build_topic_payload([_comment(1)], changes, {"地平线": ["地平线"]})

    assert set(payload) == {"changes", "aliases", "comments", "source_file"}
    assert payload["changes"][0]["tg"] == "地平线"
    assert payload["comments"][0]["n"] == 1


def test_stage1_produces_a_classified_but_unjudged_analysis():
    client = FakeClient([_topic_row(1)])
    change = PatchChange(target="地平线", change_summary="冷却加长")

    result = analyze_topic_batch([_comment(1)], [change], client)

    assert len(result) == 1
    row = result[0]
    assert row.comment_id == "COM-0001"
    assert row.primary_target == "地平线"
    assert row.analysis_stage == "已归类"
    # No attitude yet: stage 2 has not run, and the derived stance must not
    # pretend it has.
    assert row.direction_attitude == "无法判断"
    assert row.overall_stance == "无法判断"
    assert row.root_issue_status == "无法判断"


def test_stage1_contract_breach_is_raised_not_silently_defaulted():
    """The regression this guards: the model omitted fields, every one had a
    default, and the whole batch silently landed on '无法判断'."""
    client = FakeClient([{"n": 1, "tg": "地平线", "stance": "负面"}])

    try:
        analyze_topic_batch([_comment(1)], [PatchChange(target="地平线")], client)
    except Exception as exc:  # noqa: BLE001
        assert "输出契约" in str(exc)
    else:
        raise AssertionError("整批缺失契约字段必须报错，而不是静默落到默认值。")


def test_a_single_sloppy_stage1_row_is_tolerated():
    rows = [_topic_row(n) for n in range(1, 5)]
    rows[0].pop("q")  # 1 of 4 is within the tolerance
    client = FakeClient(rows)

    result = analyze_topic_batch([_comment(n) for n in range(1, 5)], [PatchChange(target="地平线")], client)
    assert len(result) == 4


def test_stage1_sequence_mismatch_is_rejected():
    client = FakeClient([_topic_row(1), _topic_row(3)])

    try:
        analyze_topic_batch([_comment(1), _comment(2)], [PatchChange(target="地平线")], client)
    except Exception as exc:  # noqa: BLE001
        assert "序号不匹配" in str(exc)
    else:
        raise AssertionError("序号集合不匹配必须报错。")


# --- stage 2: attitude -------------------------------------------------------


def test_attitude_payload_sends_only_the_one_target():
    changes = [
        PatchChange(target="地平线", change_summary="冷却加长"),
        PatchChange(target="恶灵", change_summary="位移调整"),
    ]
    payload = build_attitude_payload([_comment(1)], "地平线", changes)

    assert payload["target"] == "地平线"
    assert payload["change"]["tg"] == "地平线"
    # The other target's row never travels with an attitude request.
    assert "恶灵" not in str(payload["change"])


def test_unmapped_bucket_sends_a_null_target_and_no_change_row():
    changes = [PatchChange(target="地平线", change_summary="冷却加长")]
    payload = build_attitude_payload([_comment(1)], None, changes)

    assert payload["target"] is None
    assert payload["change"] is None


def test_stage2_attitude_keeps_the_stage1_target_and_domain():
    client = FakeClient([_attitude_row(1)])
    change = PatchChange(target="地平线", change_summary="冷却加长")

    result = analyze_attitude_batch([_comment(1)], "地平线", [change], client)

    row = result[0]
    assert row.analysis_stage == "已完成"
    assert row.primary_target == "地平线"
    assert row.direction_attitude == "反对改动方向"


def test_stage2_contract_and_sequence_checks():
    client = FakeClient([{"n": 1, "d": "反对改动方向", "stance": "负面"}])
    try:
        analyze_attitude_batch([_comment(1)], "地平线", [PatchChange(target="地平线")], client)
    except Exception as exc:  # noqa: BLE001
        assert "输出契约" in str(exc)
    else:
        raise AssertionError("整批缺失契约字段必须报错。")

    client = FakeClient([_attitude_row(2)])
    try:
        analyze_attitude_batch([_comment(1)], "地平线", [PatchChange(target="地平线")], client)
    except Exception as exc:  # noqa: BLE001
        assert "序号不匹配" in str(exc)
    else:
        raise AssertionError("序号集合不匹配必须报错。")


# --- prompts -----------------------------------------------------------------


def test_prompts_request_only_their_own_stage():
    from src.integrations.prompt_store import read_prompt

    topic = read_prompt("comment_topic_prompt.txt")
    attitude = read_prompt("comment_attitude_prompt.txt")

    # Stage 1 must not ask for attitude, stage 2 must not re-ask for the target.
    for derived in ("d", "i", "s"):
        assert f'"{derived}"' not in topic
    assert '"tg"' not in attitude
    for key in TOPIC_KEYS:
        assert f'"{key}"' in topic
    for key in ATTITUDE_KEYS:
        assert f'"{key}"' in attitude


def test_prompts_carry_the_review_lessons_slot():
    from src.integrations.prompt_store import read_prompt

    for name in ("comment_topic_prompt.txt", "comment_attitude_prompt.txt"):
        assert "{REVIEW_LESSONS}" in read_prompt(name)
