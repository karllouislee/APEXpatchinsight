"""Statistics are aggregated per target, not per synthetic change id."""
from src.core.aggregation import aggregate, group_terms, target_groups
from src.core.models import CleanComment, CommentAnalysis, PatchChange


def comment(index: int) -> CleanComment:
    return CleanComment(comment_id=f"COM-{index:04d}", source_file="demo.csv", local_index=index, platform="A", content="反馈文字", original_content="反馈文字", cleaned_content="反馈文字")


def test_transparent_support_and_controversy_rules():
    change = PatchChange(target="目标", change_summary="调整")
    comments = [comment(i) for i in range(1, 6)]
    analyses = [CommentAnalysis(comment_id=c.comment_id, primary_target="目标", direction_attitude="支持改动方向" if i < 3 else "反对改动方向", information_quality="高") for i, c in enumerate(comments)]
    stats = aggregate([change], comments, analyses)
    item = stats["targets"]["目标"]
    assert item["direction_support"] == {"numerator": 3, "denominator": 5, "rate": 0.6}
    assert item["controversy"] == "高"
    assert item["discussion_heat"]["denominator"] == 5


def test_acceptance_rate_counts_every_related_comment():
    """接受率的分母是全部相关评论，方向支持率的分母只算方向明确的。"""
    change = PatchChange(target="目标", change_summary="调整")
    comments = [comment(i) for i in range(1, 6)]
    directions = ["支持改动方向", "支持改动方向", "反对改动方向", "对方向没有明确态度", "无法判断"]
    analyses = [
        CommentAnalysis(comment_id=c.comment_id, primary_target="目标", direction_attitude=direction)
        for c, direction in zip(comments, directions)
    ]

    item = aggregate([change], comments, analyses)["targets"]["目标"]

    assert item["acceptance_rate"] == {"numerator": 2, "denominator": 5, "rate": 0.4}
    assert item["direction_support"] == {"numerator": 2, "denominator": 3, "rate": 2 / 3}


def test_less_than_five_is_insufficient_evidence():
    change = PatchChange(target="目标", change_summary="调整")
    comments = [comment(i) for i in range(1, 5)]
    analyses = [CommentAnalysis(comment_id=c.comment_id, primary_target="目标") for c in comments]
    assert aggregate([change], comments, analyses)["targets"]["目标"]["controversy"] == "证据不足"


def test_several_ability_rows_share_one_target_without_double_counting():
    """A comment naming only the legend belongs to that legend once, not once per ability."""
    changes = [
        PatchChange(target="寻血猎犬", ability_or_system="战术技能", change_summary="冷却加长"),
        PatchChange(target="寻血猎犬", ability_or_system="终极技能", change_summary="伤害降低"),
    ]
    comments = [comment(i) for i in range(1, 4)]
    analyses = [CommentAnalysis(comment_id=c.comment_id, primary_target="寻血猎犬") for c in comments]

    stats = aggregate(changes, comments, analyses)

    assert list(stats["targets"]) == ["寻血猎犬"]
    assert stats["targets"]["寻血猎犬"]["related_count"] == 3
    assert stats["matched_comment_count"] == 3
    # Three comments counted once each, not six.
    assert sum(item["related_count"] for item in stats["targets"].values()) == 3


def test_english_and_chinese_names_both_resolve():
    change = PatchChange(target="寻血猎犬", aliases=["Bloodhound"], change_summary="调整")
    comments = [comment(1), comment(2)]
    analyses = [
        CommentAnalysis(comment_id="COM-0001", primary_target="寻血猎犬"),
        CommentAnalysis(comment_id="COM-0002", primary_target="Bloodhound"),
    ]

    assert aggregate([change], comments, analyses)["targets"]["寻血猎犬"]["related_count"] == 2


def test_target_groups_keep_insertion_order():
    changes = [
        PatchChange(target="A", change_summary="1"),
        PatchChange(target="B", change_summary="2"),
        PatchChange(target="A", change_summary="3"),
    ]
    groups = target_groups(changes)
    assert list(groups) == ["A", "B"]
    assert len(groups["A"]) == 2


def test_group_terms_union_abilities_and_aliases():
    group = [PatchChange(target="寻血猎犬", ability_or_system="战术技能", aliases=["狗子"], change_summary="x")]
    assert group_terms(group) == {"寻血猎犬", "战术技能", "狗子"}
