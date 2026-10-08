"""The stepper is the only navigation, so its state must track the project."""
import streamlit as st

from src.core.models import STAGE_TOPIC, CleanComment, CommentAnalysis, PatchChange, Project
from src.ui.components.stepper import STEPS, _counts, _statuses, current_step
from src.ui.state import KEY_STEP


def _ctx(project):
    from src.ui.state import AppContext

    class Stub(AppContext):
        def __init__(self, project):  # bypass Streamlit bootstrap
            self._project = project

        @property
        def project(self):
            return self._project

    return Stub(project)


def _change(index: int, confirmed: bool) -> PatchChange:
    # A change missing target or summary is forced back to unconfirmed by the
    # model validator, so the fixture has to be complete.
    return PatchChange(
        target=f"目标{index}",
        change_summary="冷却时间调整",
        confirmed=confirmed,
    )


def _project(changes=0, confirmed=0, comments=0, analyses=0):
    return Project(
        changes=[_change(i, i < confirmed) for i in range(changes)],
        comments=[
            CleanComment(comment_id=f"COM-{i:04d}", local_index=i, platform="B站", content="x", cleaned_content="x")
            for i in range(comments)
        ],
        analyses=[
            CommentAnalysis(comment_id=f"COM-{i:04d}", evidence_quote="x")
            for i in range(analyses)
        ],
    )
    return project


def test_steps_follow_the_main_line():
    assert [step.title for step in STEPS] == ["提取更新内容", "评论收集", "分析评论", "统计结果"]


def test_empty_project_marks_everything_todo():
    assert _statuses(_ctx(_project())) == ["todo", "todo", "todo", "todo"]
    assert _counts(_ctx(_project()))[1] == "待导入"


def test_confirmed_changes_and_comments_advance_the_pipeline():
    project = _project(changes=3, confirmed=3, comments=10)
    assert _statuses(_ctx(project)) == ["done", "done", "active", "todo"]
    assert _counts(_ctx(project)) == ["3 项改动", "10 条评论", "0/10 已归类", "0/10 已判定"]


def test_analysis_step_completes_only_when_every_valid_comment_is_analyzed():
    partial = _project(changes=1, confirmed=1, comments=10, analyses=4)
    assert _statuses(_ctx(partial))[2] == "active"

    complete = _project(changes=1, confirmed=1, comments=10, analyses=10)
    assert _statuses(_ctx(complete)) == ["done", "done", "done", "done"]


def test_topic_only_classifications_keep_the_analysis_step_active():
    """Stage 1 done is not stage 2 done — attitudes still owe a pass."""
    partial = _project(changes=1, confirmed=1, comments=10, analyses=4)
    for analysis in partial.analyses:
        analysis.analysis_stage = STAGE_TOPIC
    assert _statuses(_ctx(partial))[2] == "active"
    counts = _counts(_ctx(partial))
    assert counts[2] == "4/10 已归类"
    assert counts[3] == "0/10 已判定"


def test_unconfirmed_changes_keep_the_first_step_incomplete():
    assert _statuses(_ctx(_project(changes=2, confirmed=1)))[0] == "active"


def test_invalid_comments_are_excluded_from_the_analysis_denominator():
    project = _project(changes=1, confirmed=1, comments=10, analyses=8)
    project.comments[8].is_valid = False
    project.comments[9].duplicate_of = "COM-0000"
    assert _counts(_ctx(project))[2] == "8/8 已归类"


def test_step_selection_defaults_to_the_first_step():
    st.session_state.pop(KEY_STEP, None)
    assert current_step() == STEPS[0].title

    st.session_state[KEY_STEP] = "统计结果"
    assert current_step() == "统计结果"
    st.session_state.pop(KEY_STEP, None)
