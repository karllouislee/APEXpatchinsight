"""Version bookkeeping plus a smoke check that the shell still wires every step."""
from pathlib import Path

from src import __version__
from src.ui.app_shell import PAGES
from src.ui.components.stepper import STEPS


def _ui_sources() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(Path("src/ui").rglob("*.py")))


def test_current_version_is_recorded_in_changelog():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog


def test_every_pipeline_step_has_a_renderer():
    assert set(PAGES) == {step.title for step in STEPS}
    assert all(callable(render) for render in PAGES.values())


def test_pipeline_follows_the_main_line():
    assert [step.title for step in STEPS] == ["提取更新内容", "评论收集", "分析评论", "统计结果"]


def test_shell_exposes_close_button_version_and_api_console():
    sources = _ui_sources()
    assert '"关闭应用"' in sources
    assert "close_application_requested" in sources
    assert "v{version}" in sources
    assert '"API 调用控制台"' in sources
    assert '"AI 总结并分类版本改动"' in sources
    assert "allow_client_call" in sources
