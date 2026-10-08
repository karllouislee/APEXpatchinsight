from src.core.article_parser import parse_article
from src.core.settings import DEFAULT_REASONING_EFFORT, get_settings
from src.core.models import Article
from src.services.patch_structurer import structure_deterministic


def test_settings_read_environment_at_instantiation(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "fresh-key")
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "https://fresh.example/v1")
    monkeypatch.setenv("SILICONFLOW_TEXT_MODEL", "text-fresh")
    monkeypatch.setenv("SILICONFLOW_REASONING_EFFORT", "max")
    settings = get_settings()
    assert settings.api_key == "fresh-key"
    assert settings.text_ready
    assert settings.reasoning_effort == "max"
    assert set(settings.safe_status) == {"API Key", "文本模型"}


def test_settings_default_to_reasoning_glm_flash(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_TEXT_MODEL", raising=False)
    monkeypatch.delenv("SILICONFLOW_REASONING_EFFORT", raising=False)
    settings = get_settings()
    assert "GLM-5.3-Flash" in settings.text_model
    assert settings.reasoning_effort == DEFAULT_REASONING_EFFORT


def test_deterministic_change_keeps_hero_and_skill_together():
    article = Article(
        title="Example",
        url="https://example.invalid",
        sections=[
            {
                "heading": "Tactical",
                "parent_heading": "Horizon",
                "section_type": "ability",
                "items": ["Cooldown increased from 20 to 25 seconds."],
                "paragraphs": [],
            }
        ],
    )
    changes = structure_deterministic(article)
    assert len(changes) == 1
    assert changes[0].target == "Horizon"
    assert changes[0].ability_or_system == "Tactical"
    assert changes[0].source_heading == "Horizon - Tactical"


def test_parser_marks_standard_skill_headings_under_hero():
    html = "<h2>Horizon</h2><h3>Passive</h3><p>Gravity Lift changed.</p>"
    article = parse_article(html, "https://example.invalid")
    assert article.sections[1]["parent_heading"] == "Horizon"
    assert article.sections[1]["section_type"] == "ability"
