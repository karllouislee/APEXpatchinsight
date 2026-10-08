"""Composition root: builds the app context and renders the current pipeline step."""
from __future__ import annotations

from collections.abc import Callable

from .components.sidebar import render_header, render_sidebar
from .components.stepper import STEPS, render_stepper
from .pages import analysis_page, comments_page, import_page, results_page
from .state import AppContext

PageRenderer = Callable[[AppContext], None]

PAGES: dict[str, PageRenderer] = {
    STEPS[0].title: import_page.render,
    STEPS[1].title: comments_page.render,
    STEPS[2].title: analysis_page.render,
    STEPS[3].title: results_page.render,
}


def run(version: str) -> None:
    ctx = AppContext.bootstrap()
    # Refresh before the stepper renders so the strip shows live counts rather
    # than whatever the previous session left on disk.
    ctx.recalculate()
    render_sidebar(ctx, version)
    render_header(ctx)
    current = render_stepper(ctx)
    PAGES[current](ctx)
