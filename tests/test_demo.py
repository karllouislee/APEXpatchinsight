from pathlib import Path

from src.services.demo_data import build_demo_project


def test_demo_has_required_scale_and_platforms(tmp_path: Path):
    project = build_demo_project(tmp_path)
    assert len(project.changes) == 3
    assert 40 <= len(project.comments) <= 60
    assert len({comment.platform for comment in project.comments}) == 2
    assert project.is_demo
