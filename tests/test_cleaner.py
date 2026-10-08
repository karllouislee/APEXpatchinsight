from src.core.comment_cleaner import clean_comment, normalize_text
from src.core.models import RawComment


def raw(content: str) -> RawComment:
    return RawComment(source_file="a.csv", local_index=1, platform="论坛", content=content)


def test_normalize_and_invalid_rules():
    assert normalize_text("ＡＰＥＸ  \n\n 好") == "APEX\n好"
    assert clean_comment(raw("https://example.com")).is_valid is False
    assert clean_comment(raw("👍")).invalid_reason == "纯表情或符号"
    assert clean_comment(raw("这个改动方向合理")).is_valid is True

