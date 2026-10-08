"""Sidebar: model configuration and session controls only.

Navigation lives in the main-line stepper, and the rarely-touched editors are
folded away — the sidebar is for getting the model connected, nothing else.
"""
from __future__ import annotations

import os

import streamlit as st

from ...services.demo_data import DISCLAIMER
from ..state import AppContext, KEY_CLOSE_REQUESTED
from .api_console import render_api_console
from .api_settings import render_api_settings
from .editors import render_alias_editor, render_prompt_editor


def render_sidebar(ctx: AppContext, version: str) -> None:
    if ctx.project.is_demo:
        st.sidebar.warning("当前为虚构演示项目")

    render_api_settings(ctx)

    for label, ready in ctx.settings.safe_status.items():
        st.sidebar.write(f"{'●' if ready else '○'} {label}")

    with st.sidebar.expander("高级：提示词 / 词典 / 控制台", expanded=False):
        render_prompt_editor()
        render_alias_editor(ctx)
        render_api_console(ctx)

    st.sidebar.divider()
    _render_session_buttons(ctx)
    st.sidebar.caption(f"v{version}")


def _render_session_buttons(ctx: AppContext) -> None:
    if st.sidebar.button("保存当前项目", width="stretch"):
        ctx.save_project()

    if st.sidebar.button("关闭应用", width="stretch"):
        st.session_state[KEY_CLOSE_REQUESTED] = True

    if st.session_state.get(KEY_CLOSE_REQUESTED):
        st.sidebar.warning("确认关闭？未保存的修改会丢失。")
        left, right = st.sidebar.columns(2)
        if left.button("确认关闭", key="confirm_close_application"):
            # The BAT launches Streamlit in the foreground, so ending this
            # process also ends the BAT run.
            os._exit(0)
        if right.button("取消", key="cancel_close_application"):
            st.session_state[KEY_CLOSE_REQUESTED] = False
            st.rerun()


def render_header(ctx: AppContext) -> None:
    st.caption("把官方改动与玩家评论映射为可追溯结论；不判断版本整体成败，不替代游戏内行为数据。")
    if ctx.project.is_demo:
        st.markdown(f'<div class="notice"><b>{DISCLAIMER}</b></div>', unsafe_allow_html=True)
