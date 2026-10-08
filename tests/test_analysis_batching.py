"""Analysis must be resumable at each stage: every batch lands before the next."""
from src.core.models import (
    STAGE_DONE,
    STAGE_TOPIC,
    CleanComment,
    CommentAnalysis,
    PatchChange,
    Project,
)
from src.services import analysis_service
from src.services.comment_analyzer import MAX_ATTITUDE_BATCH_SIZE


def _project(count: int) -> Project:
    return Project(
        changes=[PatchChange(target="地平线", change_summary="冷却加长")],
        comments=[
            CleanComment(
                comment_id=f"COM-{index:04d}",
                local_index=index,
                platform="B站",
                content=f"第 {index} 条反馈，力度不足",
                cleaned_content=f"第 {index} 条反馈，力度不足",
                source_file="a.csv",
            )
            for index in range(1, count + 1)
        ],
    )


def _topic(comment_id: str, target: str | None = "地平线") -> CommentAnalysis:
    return CommentAnalysis(comment_id=comment_id, analysis_stage=STAGE_TOPIC, primary_target=target)


def _done(comment_id: str, target: str | None = "地平线") -> CommentAnalysis:
    return CommentAnalysis(
        comment_id=comment_id, analysis_stage=STAGE_DONE, primary_target=target,
        direction_attitude="反对改动方向", intensity_attitude="力度不足",
    )


class StubClient:
    """Returns one verdict per requested sequence number, and records each call."""

    def __init__(self, stage: str, fail_on_call: int | None = None):
        self.stage = stage
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.targets: list[str | None] = []

    def text_json(self, prompt, payload, output_type):
        self.calls += 1
        if self.fail_on_call is not None and self.calls > self.fail_on_call:
            raise RuntimeError("上游中断")
        self.targets.append(payload.get("target"))
        if self.stage == "topic":
            return [
                {"n": row["n"], "tg": "地平线", "m": "平衡", "q": "力度不足", "c": 0.8}
                for row in payload["comments"]
            ]
        return [
            {"n": row["n"], "d": "反对改动方向", "i": "力度不足", "q": "力度不足", "c": 0.8, "s": False}
            for row in payload["comments"]
        ]


def _review():
    from src.core.models import ReviewRecord

    return ReviewRecord(comment_id="COM-0001", reasons=["测试"])


# --- stage 1: topic ----------------------------------------------------------


def test_topic_pending_skips_already_classified_rows():
    project = _project(5)
    project.analyses = [_topic("COM-0001"), _done("COM-0003")]
    assert [c.comment_id for c in analysis_service.topic_pending(project)] == [
        "COM-0002", "COM-0004", "COM-0005",
    ]


def test_topic_pending_skips_invalid_and_duplicates():
    project = _project(3)
    project.comments[1].is_valid = False
    project.comments[2].duplicate_of = "COM-0001"
    assert [c.comment_id for c in analysis_service.topic_pending(project)] == ["COM-0001"]


def test_stage1_runs_one_batch_at_a_time():
    project = _project(25)
    client = StubClient("topic")

    fresh = analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)

    assert len(fresh) == 20
    assert client.calls == 1
    assert len(project.analyses) == 20
    assert all(a.analysis_stage == STAGE_TOPIC for a in fresh)


def test_stage1_repeated_batches_drain_the_queue_and_never_reanalyze():
    project = _project(25)
    client = StubClient("topic")

    analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)
    analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)
    third = analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)

    assert third == []
    assert client.calls == 2
    assert len(project.analyses) == 25
    assert analysis_service.topic_pending(project) == []


def test_stage1_failure_keeps_everything_already_saved():
    project = _project(40)
    client = StubClient("topic", fail_on_call=1)

    analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)
    try:
        analysis_service.analyze_next_topic_batch(project, client, None, batch_size=20)
    except RuntimeError:
        pass

    assert len(project.analyses) == 20
    assert len(analysis_service.topic_pending(project)) == 20


# --- stage 2: attitude -------------------------------------------------------


def test_stage2_runs_one_target_at_a_time():
    """Each request carries one target and only that target's comments."""
    project = _project(30)
    project.changes = [
        PatchChange(target="地平线", change_summary="冷却加长"),
        PatchChange(target="恶灵", change_summary="位移调整"),
    ]
    project.analyses = [
        _topic(c.comment_id, "地平线" if int(c.comment_id[-2:]) <= 20 else "恶灵")
        for c in project.comments
    ]
    client = StubClient("attitude")

    target, fresh = analysis_service.analyze_next_attitude_batch(project, client, None)

    assert target == "地平线"
    assert len(fresh) == 20
    assert client.targets == ["地平线"]
    assert all(a.analysis_stage == STAGE_DONE for a in fresh)
    assert project.analyses[0].primary_target == "地平线"
    # Only the first bucket is done; the second is still queued.
    assert analysis_service.attitude_pending(project)[0][0].comment_id == "COM-0021"


def test_stage2_bucket_order_follows_the_change_list():
    project = _project(3)
    project.changes = [
        PatchChange(target="恶灵", change_summary="a"),
        PatchChange(target="地平线", change_summary="b"),
    ]
    project.comments[0].cleaned_content = "恶灵"
    project.comments[1].cleaned_content = "地平线"
    project.comments[2].cleaned_content = "地平线 again"
    project.analyses = [
        _topic("COM-0001", "恶灵"),
        _topic("COM-0002", "地平线"),
        _topic("COM-0003", "地平线"),
    ]

    first, _ = analysis_service.analyze_next_attitude_batch(project, StubClient("attitude"), None)
    assert first == "恶灵"


def test_stage2_unmapped_comments_still_get_an_attitude():
    """No matching change and no opinion are different answers."""
    project = _project(2)
    project.analyses = [_topic("COM-0001", None), _topic("COM-0002", None)]
    client = StubClient("attitude")

    target, fresh = analysis_service.analyze_next_attitude_batch(project, client, None)

    assert target is None
    assert len(fresh) == 2
    assert all(a.analysis_stage == STAGE_DONE for a in fresh)


def test_stage2_drains_bucket_by_bucket():
    # 45 comments in one bucket: 30 per batch means two calls to drain it.
    project = _project(45)
    project.analyses = [_topic(c.comment_id) for c in project.comments]
    client = StubClient("attitude")

    analysis_service.analyze_next_attitude_batch(project, client, None)
    progress = analysis_service.analysis_progress(project)
    assert client.calls == 1
    assert progress["judged"] == MAX_ATTITUDE_BATCH_SIZE
    assert progress["attitude_pending"] == 15

    analysis_service.analyze_next_attitude_batch(project, client, None)
    assert client.calls == 2
    assert analysis_service.attitude_pending(project) == []
    assert analysis_service.analysis_progress(project)["judged"] == 45


def test_progress_reports_both_stages():
    project = _project(4)
    assert analysis_service.analysis_progress(project) == {
        "total": 4, "classified": 0, "judged": 0, "topic_pending": 4, "attitude_pending": 0,
    }
    project.analyses = [_topic(c.comment_id) for c in project.comments]
    assert analysis_service.analysis_progress(project) == {
        "total": 4, "classified": 4, "judged": 0, "topic_pending": 0, "attitude_pending": 4,
    }
    project.analyses = [_done(c.comment_id) for c in project.comments]
    assert analysis_service.analysis_progress(project) == {
        "total": 4, "classified": 4, "judged": 4, "topic_pending": 0, "attitude_pending": 0,
    }


# --- restart -----------------------------------------------------------------


def test_clear_analyses_drops_model_results_and_keeps_human_work():
    project = _project(3)
    project.analyses = [_done(c.comment_id) for c in project.comments]
    project.reviews = [_review()]
    project.insights = {"地平线": {"observation": "x"}}
    project.review_history = [_review()]
    project.skipped_reviews = ["COM-0002"]

    counts = analysis_service.clear_analyses(project)

    assert counts == {"analyses": 3, "reviews": 1, "insights": 1, "skips": 1}
    assert project.analyses == []
    assert project.reviews == []
    assert project.insights == {}
    # Skip marks belong to the old round; a fresh run queues everything again.
    assert project.skipped_reviews == []
    # Human input is not model output; it must survive a restart.
    assert len(project.review_history) == 1
    assert len(project.comments) == 3


def test_reset_attitude_keeps_the_topic_classification():
    project = _project(2)
    project.analyses = [_done(c.comment_id) for c in project.comments]
    project.insights = {"地平线": {"observation": "x"}}

    counts = analysis_service.reset_attitude(project)

    assert counts == {"attitude_reset": 2}
    for analysis in project.analyses:
        assert analysis.analysis_stage == STAGE_TOPIC
        assert analysis.primary_target == "地平线"
        assert analysis.direction_attitude == "无法判断"
        assert analysis.overall_stance == "无法判断"
    assert project.insights == {}
    # Topic classification is untouched, so stage 2 can run again from here.
    assert analysis_service.topic_pending(project) == []
    assert set(analysis_service.attitude_buckets(project)) == {"地平线"}


def test_reset_attitude_is_a_noop_without_completed_rows():
    project = _project(2)
    project.analyses = [_topic(c.comment_id) for c in project.comments]
    assert analysis_service.reset_attitude(project) == {"attitude_reset": 0}


def test_merge_analyses_replaces_stale_rows_for_the_same_comment():
    project = _project(2)
    project.analyses = [_topic("COM-0001")]
    updated = CommentAnalysis(comment_id="COM-0001", analysis_stage=STAGE_TOPIC, problem_domain="Bug")
    analysis_service.merge_analyses(project, [updated])

    assert len(project.analyses) == 1
    assert project.analyses[0].problem_domain == "Bug"
