from app.catalog import EXPERTS, SKILLS
from app.models import RouteRequest
from app.router import RuleRouter


def test_data_task_selects_python_expert_and_data_skill() -> None:
    result = RuleRouter(EXPERTS, SKILLS).route(RouteRequest(task="分析销售数据并生成可视化报表"))
    assert result.expert.id == "python-fullstack"
    assert result.skills[0].id == "data-analysis"


def test_research_task_selects_researcher() -> None:
    result = RuleRouter(EXPERTS, SKILLS).route(RouteRequest(task="搜索并调研竞品市场信息"))
    assert result.expert.id == "researcher"
    assert result.skills[0].id == "web-research"


def test_skill_count_is_bounded() -> None:
    result = RuleRouter(EXPERTS, SKILLS).route(RouteRequest(task="写 Python 代码并分析数据", max_skills=1))
    assert len(result.skills) <= 1


def test_required_skill_missing_returns_fallback() -> None:
    result = RuleRouter(EXPERTS, SKILLS).route(
        RouteRequest(task="写一份报告", required_skills=["browser"])
    )
    assert result.fallback is True
    assert result.needs_confirmation is True
    assert "browser" in result.reasons[-1]


def test_excluded_skill_is_not_selected() -> None:
    result = RuleRouter(EXPERTS, SKILLS).route(
        RouteRequest(task="分析销售数据", excluded_skills=["data-analysis"])
    )
    assert all(skill.id != "data-analysis" for skill in result.skills)
