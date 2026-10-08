from src.core.comment_cleaner import clean_comments
from src.core.deduplicator import canonical_comments, deduplicate_comments
from src.core.models import RawComment


def test_exact_and_fuzzy_duplicates_preserve_sources():
    items = [
        RawComment(comment_id="COM-0001", source_file="a.csv", local_index=1, platform="A", content="这个改动方向是对的，但是力度不够"),
        RawComment(comment_id="COM-0002", source_file="b.csv", local_index=1, platform="A", content="这个改动方向是对的,但是力度不够"),
    ]
    result = deduplicate_comments(clean_comments(items), threshold=88)
    assert result[1].duplicate_of == "COM-0001"
    assert result[0].source_file == "a.csv"
    assert len(canonical_comments(result)) == 1

