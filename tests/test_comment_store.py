import json

from src.integrations.comment_store import clear_comment_store, load_comment_store, merge_extracted_comments, save_comment_store
from src.core.models import CleanComment, RawComment


def make_raw(comment_id: str, content: str) -> RawComment:
    return RawComment(comment_id=comment_id, local_index=1, platform="taptap", content=content, source_file="a.csv")


def test_merge_assigns_incremental_ids_without_renumbering_existing():
    existing = [make_raw("COM-0001", "旧评论一"), make_raw("COM-0002", "旧评论二")]
    extracted = [make_raw("", "新评论一"), make_raw("", "新评论二")]
    combined = merge_extracted_comments(existing, extracted)
    assert [c.comment_id for c in combined] == ["COM-0001", "COM-0002", "COM-0003", "COM-0004"]


def test_merge_continues_after_max_id_even_with_gaps():
    existing = [make_raw("COM-0001", "a"), make_raw("COM-0007", "b")]
    extracted = [make_raw("", "c")]
    combined = merge_extracted_comments(existing, extracted)
    assert combined[-1].comment_id == "COM-0008"


def test_store_roundtrip(tmp_path):
    raw = [make_raw("COM-0001", "内容")]
    cleaned = [CleanComment(**{**raw[0].model_dump(), "cleaned_content": "内容"})]
    save_comment_store(tmp_path, raw, cleaned, "2026-08-03T00:00:00")
    loaded = load_comment_store(tmp_path)
    assert loaded["raw_comments"][0]["comment_id"] == "COM-0001"
    assert loaded["raw_comments"][0]["source_file"] == "a.csv"
    assert loaded["comments"][0].cleaned_content == "内容"
    assert loaded["updated_at"] == "2026-08-03T00:00:00"


def test_load_missing_or_corrupt_store_returns_empty(tmp_path):
    assert load_comment_store(tmp_path)["comments"] == []
    (tmp_path / "comments_store.json").write_text("{not json", encoding="utf-8")
    assert load_comment_store(tmp_path)["comments"] == []


def test_legacy_screenshot_filename_still_loads_into_source_file(tmp_path):
    """Corpora saved before screenshots were dropped must still open."""
    store = tmp_path / "comments_store.json"
    store.write_text(
        json.dumps(
            {
                "raw_comments": [
                    {
                        "comment_id": "COM-0001",
                        "local_index": 1,
                        "platform": "B站",
                        "content": "旧语料",
                        "screenshot_filename": "legacy_shot.png",
                    }
                ],
                "comments": [],
                "updated_at": "t",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_comment_store(tmp_path)
    legacy = RawComment.model_validate(loaded["raw_comments"][0])
    assert legacy.source_file == "legacy_shot.png"


def test_clear_store(tmp_path):
    save_comment_store(tmp_path, [], [], "t")
    clear_comment_store(tmp_path)
    assert load_comment_store(tmp_path)["comments"] == []
