from pathlib import Path

from src.core.aggregation import aggregate
from src.core.models import CleanComment, CommentAnalysis, PatchChange, Project
from src.services.demo_data import DISCLAIMER, build_demo_project
from src.core.reporting import analyses_csv, analysis_results_markdown, generate_markdown, project_json


def test_demo_report_and_exports_are_traceable(tmp_path: Path):
    project = build_demo_project(tmp_path)
    stats = aggregate(project.changes, project.comments, project.analyses)
    report = generate_markdown(project, stats)
    assert DISCLAIMER in report
    assert "COM-" in analyses_csv(project)
    assert '"project_id"' in project_json(project)


def _project(tmp_path: Path) -> tuple[Project, dict]:
    change = PatchChange(target="地平线", change_summary="冷却加长", confirmed=True)
    comments = [
        CleanComment(comment_id=f"COM-{i:04d}", source_file="demo.csv", local_index=i,
                     platform="B站", content="反馈", cleaned_content=feedback)
        for i, feedback in enumerate(
            ["这次冷却加长很合理，早该改了", "支持这波调整，问题确实存在", "改了等于没改", "反正我是不玩地平线了", "地平线现在强度如何"],
            1,
        )
    ]
    directions = ["支持改动方向", "支持改动方向", "反对改动方向", "反对改动方向", "无法判断"]
    analyses = [
        CommentAnalysis(comment_id=c.comment_id, analysis_stage="已完成", primary_target="地平线",
                        direction_attitude=direction, analysis_confidence=0.9,
                        evidence_quote=feedback[:4])
        for c, feedback, direction in zip(comments, [c.cleaned_content for c in comments], directions)
    ]
    project = Project(project_id="p1", changes=[change], comments=comments, analyses=analyses)
    stats = aggregate(project.changes, project.comments, project.analyses)
    return project, stats


def test_analysis_results_export_covers_determinate_items_with_quotes(tmp_path: Path):
    project, stats = _project(tmp_path)

    report = analysis_results_markdown(project, stats)

    assert "# 地平线" in report
    assert "结论：玩家对该改动方向意见分裂" in report  # 2 支持 / 2 反对
    assert "方向支持率 2/4" in report
    assert "接受率 2/5" in report
    # Reference comments carry direction labels and are real comments;
    # determinate directions are preferred, so no 无法判断 quote gets picked.
    assert "方向：支持改动方向" in report
    assert "这次冷却加长很合理" in report
    assert "方向：无法判断" not in report


def test_analysis_results_export_lists_pending_items_without_verdicts(tmp_path: Path):
    project, stats = _project(tmp_path)
    # Every verdict becomes undecidable → no item is exportable as determinate.
    for analysis in project.analyses:
        analysis.direction_attitude = "无法判断"
    stats = aggregate(project.changes, project.comments, project.analyses)

    report = analysis_results_markdown(project, stats)

    assert "其中 0 个方向结论确定" in report
    assert "方向结论未确定的条目" in report
    assert "地平线：5 条相关评论" in report

