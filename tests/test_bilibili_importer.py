import pytest

from src.core.bilibili_importer import BilibiliImportError, parse_bilibili_csv


CSV_TEXT = """序号,上级评论ID,评论ID,用户ID,用户名,评论内容,评论时间,回复数,点赞数,IP属地,头像
1,0,1001,9001,测试用户,削弱方向是对的但力度不够,2026-08-09 12:00:00,1,32,广东,https://example/avatar.jpg
2,1001,1002,9002,另一个用户,确实还没有削到核心问题,2026-08-09 12:01:00,0,8,北京,https://example/avatar2.jpg
"""


def test_import_extension_csv_anonymizes_and_resolves_reply_context():
    result = parse_bilibili_csv(
        ("\ufeff" + CSV_TEXT).encode("utf-8"),
        "示例评论.csv",
        source_url="https://www.bilibili.com/video/BV1234567890/?vd_source=secret#reply",
    )

    assert len(result.comments) == 2
    root, reply = result.comments
    assert root.content == "削弱方向是对的但力度不够"
    assert root.likes == 32
    assert root.source_type == "csv"
    assert root.source_file.endswith(".csv")
    assert root.source_comment_key and "1001" not in root.source_comment_key
    assert len(root.source_comment_key) == 20
    assert root.source_url == "https://www.bilibili.com/video/BV1234567890"
    assert root.source_file.startswith("bilibili_")
    assert "示例评论" not in root.source_file
    assert root.local_index == 2
    assert reply.local_index == 3
    assert reply.is_reply is True
    assert reply.reply_context == root.content
    dumped = str([item.model_dump(mode="json") for item in result.comments])
    assert "测试用户" not in dumped
    assert "9001" not in dumped
    assert "广东" not in dumped
    assert "avatar.jpg" not in dumped


def test_import_is_stable_across_incremental_exports_and_respects_row_limit():
    data = CSV_TEXT.encode("utf-8")
    expanded = (CSV_TEXT + "3,0,1003,9003,新用户,新增评论,2026-08-09 12:02:00,0,1,上海,avatar\\n").encode("utf-8")
    first = parse_bilibili_csv(data, "comments.csv", row_limit=1)
    second = parse_bilibili_csv(expanded, "comments-later.csv", row_limit=1)

    assert first.source_id != second.source_id
    assert first.comments[0].source_comment_key == second.comments[0].source_comment_key
    assert first.truncated is True
    assert len(first.comments) == 1


def test_import_rejects_non_bilibili_source_url_and_missing_content():
    with pytest.raises(BilibiliImportError):
        parse_bilibili_csv(CSV_TEXT.encode("utf-8"), "comments.csv", source_url="https://example.com/video")
    with pytest.raises(BilibiliImportError):
        parse_bilibili_csv("评论ID,用户名\n1,abc\n".encode("utf-8"), "comments.csv")


def test_import_rejects_files_larger_than_20_mb():
    with pytest.raises(BilibiliImportError, match="20 MB"):
        parse_bilibili_csv(b"x" * (20 * 1024 * 1024 + 1), "too-large.csv")