"""Comment pipeline helpers extracted from the screenshots page."""
from src.core.models import CleanComment, PatchChange, Project, RawComment
from src.services.comment_service import (
    estimate_text_calls,
    merge_raw_comments,
    new_comments_only,
    rebuild_clean_comments,
)


def _raw(**kwargs) -> RawComment:
    payload = {
        "comment_id": kwargs.pop("comment_id", ""),
        "source_file": "a.csv",
        "local_index": 1,
        "platform": "B站",
        "content": kwargs.pop("content", "这改动不错"),
        **kwargs,
    }
    return RawComment(**payload)


def test_merge_raw_comments_keeps_existing_ids():
    existing = [_raw(comment_id="COM-0001")]
    combined = merge_raw_comments(existing, [_raw(), _raw()])
    assert [item.comment_id for item in combined] == ["COM-0001", "COM-0002", "COM-0003"]


def test_new_comments_only_filters_by_source_key():
    existing = [_raw(source_comment_key="k1")]
    incoming = [_raw(source_comment_key="k1"), _raw(source_comment_key="k2")]
    assert [item.source_comment_key for item in new_comments_only(existing, incoming)] == ["k2"]


def test_rebuild_clean_comments_preserves_manual_edits():
    previous = CleanComment(
        comment_id="COM-0001", source_file="a.csv", local_index=1, platform="B站",
        content="人工修正文本", cleaned_content="人工修正文本", manual_keywords=["挖机"], is_valid=False,
    )
    raw = [_raw(comment_id="COM-0001", content="机器识别文本")]
    rebuilt = rebuild_clean_comments(raw, {"COM-0001": previous}, preserve_text=True)
    assert rebuilt[0].cleaned_content == "人工修正文本"
    assert rebuilt[0].manual_keywords == ["挖机"]

    # Without preservation the freshly recognised text wins.
    rebuilt = rebuild_clean_comments(raw, {"COM-0001": previous}, preserve_text=False)
    assert rebuilt[0].cleaned_content == "机器识别文本"
    assert rebuilt[0].manual_keywords == ["挖机"]


def test_estimate_text_calls_rounds_up():
    assert estimate_text_calls([], 20) == 0
    assert estimate_text_calls([object()] * 1, 20) == 1
    assert estimate_text_calls([object()] * 21, 20) == 2


def test_demote_demo_project_clears_fictional_payload():
    from src.services.comment_service import demote_demo_project

    project = Project(is_demo=True, demo_disclaimer="虚构", changes=[PatchChange(target="目标")])
    assert demote_demo_project(project) is True
    assert project.is_demo is False
    assert project.changes == []
    assert demote_demo_project(project) is False
