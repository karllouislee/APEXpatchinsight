"""Session state and dependency wiring.

``app.py`` used to keep ``p``, ``MONITOR``, ``CLIENT``, ``SETTINGS`` and
``STORE`` as module globals, and bound ``p = project()`` once at import time —
a hot reload could then render pages against a discarded project object.
:class:`AppContext` bundles the same collaborators but reads the live project
from ``session_state`` on every access instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st

from ..core.analytics import refresh_reviews
from ..core.community_aliases import AliasDictionary, load_aliases
from ..core.models import CleanComment, Project, RawComment
from ..core.settings import Settings, get_settings
from ..integrations.api_monitor import ApiMonitor
from ..integrations.project_store import ProjectStore
from ..integrations.siliconflow_client import SiliconFlowClient
from ..services.analysis_service import clear_analyses
from ..services.project_service import (
    apply_restored_comments,
    clear_comment_corpus,
    load_comment_corpus,
    load_or_create_project,
    persist_comment_corpus,
    raw_comment_models,
    raw_comment_payloads,
)

KEY_PROJECT = "project"
KEY_RAW_COMMENTS = "raw_comments"
KEY_VALIDATION_SAMPLE = "validation_sample"
KEY_RESTORE_NOTICE = "comment_store_restored"
KEY_CONFIRM_CLEAR = "confirm_clear_comments"
KEY_CONFIRM_CLEAR_ANALYSIS = "confirm_clear_analysis"
KEY_CONFIRM_RESET_ATTITUDE = "confirm_reset_attitude"
KEY_CLOSE_REQUESTED = "close_application_requested"
KEY_ANALYSIS_RUN = "analysis_run"
KEY_ANALYSIS_RESULT = "analysis_result"
KEY_STEP = "pipeline_step"


@dataclass
class AppContext:
    settings: Settings
    store: ProjectStore
    monitor: ApiMonitor
    client: SiliconFlowClient
    restored_comment_count: int = field(default=0)

    # --- construction -------------------------------------------------

    @classmethod
    def bootstrap(cls) -> "AppContext":
        settings = get_settings()
        monitor = ApiMonitor(st.session_state)
        client = SiliconFlowClient(settings)
        context = cls(
            settings=settings,
            store=ProjectStore(settings.workspace_dir),
            monitor=monitor,
            client=client,
        )
        context._init_state()
        # Streamlit hot reload can keep an older client class instance around;
        # re-point the event sink so monitoring never goes stale.
        client._event_sink = monitor.record_client_event
        client._call_guard = monitor.allow_client_call
        return context

    def _init_state(self) -> None:
        if KEY_PROJECT not in st.session_state:
            project = load_or_create_project(self.settings)
            store = load_comment_corpus(self.settings.workspace_dir)
            self.restored_comment_count = apply_restored_comments(project, store)
            st.session_state[KEY_PROJECT] = project
            st.session_state[KEY_RAW_COMMENTS] = store["raw_comments"]
            st.session_state[KEY_RESTORE_NOTICE] = self.restored_comment_count
        st.session_state.setdefault(KEY_RAW_COMMENTS, [])
        st.session_state.setdefault(KEY_VALIDATION_SAMPLE, [])
        st.session_state.setdefault(KEY_CONFIRM_CLEAR, False)
        st.session_state.setdefault(KEY_CONFIRM_CLEAR_ANALYSIS, False)
        st.session_state.setdefault(KEY_CONFIRM_RESET_ATTITUDE, False)
        st.session_state.setdefault(KEY_ANALYSIS_RUN, None)
        st.session_state.setdefault(KEY_ANALYSIS_RESULT, None)
        st.session_state.setdefault(KEY_STEP, None)

    # --- project ------------------------------------------------------

    @property
    def project(self) -> Project:
        return st.session_state[KEY_PROJECT]

    def replace_project(self, project: Project) -> None:
        st.session_state[KEY_PROJECT] = project

    def save_project(self) -> Path:
        path = self.store.save(self.project)
        st.toast(f"已保存到 {path.name}")
        return path

    def recalculate(self) -> dict[str, Any]:
        return refresh_reviews(self.project)

    # --- comment corpus -----------------------------------------------

    @property
    def raw_comments(self) -> list[dict[str, Any]]:
        return st.session_state[KEY_RAW_COMMENTS]

    @property
    def raw_models(self) -> list[RawComment]:
        return raw_comment_models(self.raw_comments)

    def set_raw_models(self, comments: list[RawComment]) -> None:
        st.session_state[KEY_RAW_COMMENTS] = raw_comment_payloads(comments)

    def persist_comments(self) -> None:
        persist_comment_corpus(
            self.settings.workspace_dir,
            self.raw_models,
            self.project.comments,
        )

    def clear_comments(self) -> None:
        st.session_state[KEY_RAW_COMMENTS] = []
        self.project.comments = []
        self.project.analyses = []
        self.project.reviews = []
        self.project.skipped_reviews = []
        st.session_state[KEY_ANALYSIS_RUN] = None
        st.session_state[KEY_ANALYSIS_RESULT] = None
        clear_comment_corpus(self.settings.workspace_dir)

    def clear_analysis(self) -> dict[str, int]:
        """Drop every model-produced result and reset the run state."""
        counts = clear_analyses(self.project)
        st.session_state[KEY_ANALYSIS_RUN] = None
        st.session_state[KEY_ANALYSIS_RESULT] = None
        return counts

    # --- analysis run -------------------------------------------------------
    #
    # Analysis runs one batch per Streamlit rerun, in two stages: stage 1
    # classifies every comment into a change topic, stage 2 then judges
    # attitude for one target at a time. Streamlit scripts are synchronous, so
    # a long loop cannot observe a button click; stepping once per rerun is
    # what makes the progress bar move and the stop button work. Every batch is
    # saved before the next rerun, so stopping — or closing the tab — never
    # discards billed results.

    @property
    def analysis_run(self) -> dict[str, Any] | None:
        return st.session_state.get(KEY_ANALYSIS_RUN)

    def start_analysis_run(self, stage: str, total: int, batch_size: int) -> None:
        st.session_state[KEY_ANALYSIS_RUN] = {
            "active": True, "stage": stage, "total": int(total), "batch_size": int(batch_size), "done": 0,
        }
        st.session_state[KEY_ANALYSIS_RESULT] = None

    def stop_analysis_run(self) -> None:
        """Stop-button callback: the loop notices on the next rerun."""
        run = st.session_state.get(KEY_ANALYSIS_RUN)
        if run:
            run["active"] = False

    def finish_analysis_run(self, status: str, analyzed: int, total: int, message: str = "") -> None:
        st.session_state[KEY_ANALYSIS_RUN] = None
        st.session_state[KEY_ANALYSIS_RESULT] = {"status": status, "analyzed": analyzed, "total": total, "message": message}

    def consume_analysis_result(self) -> dict[str, Any] | None:
        result = st.session_state.get(KEY_ANALYSIS_RESULT)
        if result:
            st.session_state[KEY_ANALYSIS_RESULT] = None
        return result

    def consume_restore_notice(self) -> int:
        count = int(st.session_state.get(KEY_RESTORE_NOTICE) or 0)
        if count:
            st.session_state[KEY_RESTORE_NOTICE] = 0
        return count

    @property
    def validation_sample(self) -> list[str]:
        return st.session_state[KEY_VALIDATION_SAMPLE]

    @validation_sample.setter
    def validation_sample(self, value: list[str]) -> None:
        st.session_state[KEY_VALIDATION_SAMPLE] = value

    # --- helpers -------------------------------------------------------

    @property
    def valid_comments(self) -> list[CleanComment]:
        return [c for c in self.project.comments if c.is_valid and not c.duplicate_of]

    @property
    def analysis_candidates(self) -> list[CleanComment]:
        return self.valid_comments

    @property
    def alias_dict(self) -> "AliasDictionary":
        """The slang dictionary, read fresh so sidebar edits apply immediately."""
        return load_aliases(self.settings.workspace_dir)
