from src.core.models import CleanComment, CommentAnalysis, ReviewRecord
from src.core.review_manager import build_review_queue, record_correction


def test_record_correction_tracks_comment_and_analysis_fields():
    comment = CleanComment(comment_id="COM-0001", source_file="a.csv", local_index=1, platform="B站", content="原文", cleaned_content="原文")
    analysis = CommentAnalysis(comment_id="COM-0001", problem_domain="平衡")
    record = ReviewRecord(
        comment_id="COM-0001",
        reasons=["分析置信度低于 0.70"],
        original={"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")},
    )
    corrected_comment = comment.model_copy(update={"cleaned_content": "修正文", "content": "修正文"})
    corrected_analysis = analysis.model_copy(update={"problem_domain": "Bug"})

    saved = record_correction(record, {
        "comment": corrected_comment.model_dump(mode="json"),
        "analysis": corrected_analysis.model_dump(mode="json"),
    })

    assert "comment.cleaned_content" in saved.changed_fields
    assert "comment.content" in saved.changed_fields
    assert "analysis.problem_domain" in saved.changed_fields
    assert saved.modified_at


def test_invalid_and_duplicate_comments_never_enter_the_queue():
    """Analysis skips them, so they must not pile up as 'unanalysed' noise."""
    clean = CleanComment(
        comment_id="COM-0001", local_index=1, platform="B站",
        content="力度不足", cleaned_content="力度不足",
    )
    invalid = clean.model_copy(update={"comment_id": "COM-0002", "is_valid": False})
    duplicate = clean.model_copy(update={"comment_id": "COM-0003", "duplicate_of": "COM-0001"})

    # No analysis at all: only the analysable comment may be queued.
    queue = build_review_queue([clean, invalid, duplicate], [])
    assert [record.comment_id for record in queue] == ["COM-0001"]


def test_reviewer_skipped_comments_stay_out_of_the_queue():
    """A skip decision must survive the queue being rebuilt from scratch."""
    first = CleanComment(
        comment_id="COM-0001", local_index=1, platform="B站",
        content="力度不足", cleaned_content="力度不足",
    )
    second = first.model_copy(update={"comment_id": "COM-0002"})

    queue = build_review_queue([first, second], [], skipped=["COM-0001"])
    assert [record.comment_id for record in queue] == ["COM-0002"]

    # Default (no skips) keeps both.
    assert len(build_review_queue([first, second], [])) == 2


def test_undecided_domain_alone_does_not_queue_a_comment():
    """问题类型 cannot be fixed in the review form, so it must not queue."""
    from src.core.models import STAGE_DONE

    clean = CleanComment(
        comment_id="COM-0001", local_index=1, platform="B站",
        content="力度不足", cleaned_content="力度不足",
    )
    judged = CommentAnalysis(
        comment_id="COM-0001",
        analysis_stage=STAGE_DONE,
        problem_domain="无法判断",
        direction_attitude="支持改动方向",
        analysis_confidence=0.9,
    )

    assert build_review_queue([clean], [judged]) == []
