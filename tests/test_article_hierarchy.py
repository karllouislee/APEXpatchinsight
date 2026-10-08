from src.core.article_parser import parse_article


def test_ability_headings_remain_under_the_same_hero():
    html = """
    <article>
      <h2>Legend Changes</h2>
      <h3>Horizon</h3>
      <h4>Passive</h4><p>Passive adjustment.</p>
      <h4>Tactical</h4><p>Tactical adjustment.</p>
      <h4>Ultimate</h4><p>Ultimate adjustment.</p>
      <h4>New Upgrades</h4><p>Upgrade adjustment.</p>
      <h3>Vantage</h3><p>Hero-level adjustment.</p>
    </article>
    """
    article = parse_article(html, "https://www.ea.com/test")
    abilities = {section["heading"]: section for section in article.sections if section.get("section_type") == "ability"}

    assert set(abilities) == {"Passive", "Tactical", "Ultimate", "New Upgrades"}
    assert all(section["parent_heading"] == "Horizon" for section in abilities.values())
    assert any(section["heading"] == "Horizon" for section in article.sections)
