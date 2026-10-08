import pytest

from src.integrations.ea_fetcher import find_designer_notes, validate_ea_url


def test_domain_allowlist_and_designer_note_discovery():
    with pytest.raises(ValueError):
        validate_ea_url("https://evil.example/ea.com/story")
    html = '<a href="/games/apex/news/designer-notes"><span>Designer\'s Notes</span></a>'
    candidates = find_designer_notes(html)
    assert candidates[0].url.startswith("https://www.ea.com/")

