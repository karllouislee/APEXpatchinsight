"""Domain helpers that used to live inline in app.py."""
from src.core.analytics import format_rate, refresh_reviews
from src.core.models import CleanComment, CommentAnalysis, PatchChange, Project, ReviewRecord
from src.core.text_utils import normalize_for_quote, split_keywords


def _comment(cid: str = "COM-0001") -> CleanComment:
    return CleanComment(comment_id=cid, source_file="a.csv", local_index=1, platform="B站", content="改得还行")


def test_split_keywords_accepts_both_commas():
    assert split_keywords("挖机，狗子, 轮椅") == ["挖机", "狗子", "轮椅"]
    assert split_keywords("") == []
    assert split_keywords(None) == []


def test_normalize_for_quote_ignores_width_and_space():
    assert normalize_for_quote("ＡＢ 　Ｃ") == normalize_for_quote("abc")


def test_format_rate_handles_missing_denominator():
    assert format_rate({"rate": None}) == "—"
    assert format_rate({"rate": 0.5}) == "50.0%"


def test_refresh_reviews_drops_already_resolved_records():
    comment = _comment()
    analysis = CommentAnalysis(comment_id=comment.comment_id)
    project = Project(changes=[], comments=[comment], analyses=[analysis])
    stats = refresh_reviews(project)
    assert stats["valid_comment_count"] == 1
    queued_ids = {record.comment_id for record in project.reviews}
    assert comment.comment_id in queued_ids

    # A reviewer saved exactly this state → the task leaves the queue.
    record = project.reviews[0]
    record.modified_at = "2026-01-01T00:00:00+00:00"
    record.corrected = {
        "comment": comment.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
    }
    project.review_history.append(record)
    refresh_reviews(project)
    assert project.reviews == []


def test_refresh_reviews_keeps_skipped_comments_out_of_the_queue():
    """Skips persist across queue rebuilds until they are restored by hand."""
    comment = _comment()
    project = Project(changes=[], comments=[comment], analyses=[])
    refresh_reviews(project)
    assert [record.comment_id for record in project.reviews] == [comment.comment_id]

    project.skipped_reviews = [comment.comment_id]
    refresh_reviews(project)
    assert project.reviews == []

    project.skipped_reviews = []
    refresh_reviews(project)
    assert [record.comment_id for record in project.reviews] == [comment.comment_id]


def test_refresh_reviews_requeues_when_text_changes_after_review():
    comment = _comment()
    project = Project(changes=[], comments=[comment], analyses=[])
    refresh_reviews(project)
    record = project.reviews[0]
    record.modified_at = "2026-01-01T00:00:00+00:00"
    record.corrected = {"comment": comment.model_dump(mode="json"), "analysis": None}
    project.review_history.append(record)

    comment.cleaned_content = "人工改过的文本"
    refresh_reviews(project)
    assert [item.comment_id for item in project.reviews] == [comment.comment_id]


def test_review_history_survives_requeue():
    comment = _comment()
    project = Project(changes=[], comments=[comment], analyses=[])
    refresh_reviews(project)
    history = ReviewRecord(comment_id=comment.comment_id, modified_at="2026-01-01T00:00:00+00:00")
    project.review_history.append(history)
    refresh_reviews(project)
    assert project.review_history == [history]
