from src.core.article_parser import parse_article


def test_article_parser_extracts_title_sections_and_items():
    html = """<html><head><title>Fallback</title></head><body><article>
    <h1>Designer’s Notes</h1><time datetime="2026-01-01"></time>
    <h2>Legend Changes</h2><p>Context paragraph.</p><ul><li>Cooldown increased from 20 to 25.</li></ul>
    </article></body></html>"""
    article = parse_article(html, "https://www.ea.com/test")
    assert article.title == "Designer’s Notes"
    assert article.published_at == "2026-01-01"
    assert article.sections[0]["heading"] == "Legend Changes"
    assert "Cooldown increased" in article.text

