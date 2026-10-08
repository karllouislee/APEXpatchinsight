"""Sidebar editors for prompt overrides and the community alias dictionary."""
from __future__ import annotations

import json

import streamlit as st

from ...core.community_aliases import (
    current_text as alias_current_text,
    reset_override as alias_reset_override,
    save_override as alias_save_override,
)
from ...integrations.prompt_store import (
    list_prompts,
    read_prompt,
    reset_prompt_override,
    set_prompt_override,
)
from ..state import AppContext

PROMPT_RESET_KEY = "prompt_reset_value"
ALIAS_EDITOR_KEY = "alias_dict_editor"


def render_prompt_editor() -> None:
    with st.expander("Prompt 编辑器", expanded=False):
        selected = st.selectbox("选择调用场景", list_prompts(), key="selected_prompt_file")
        editor_key = f"prompt_editor_{selected}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = st.session_state.pop(PROMPT_RESET_KEY, None) or read_prompt(selected)
        edited = st.text_area("发送给模型的 System Prompt", key=editor_key, height=320)
        set_prompt_override(selected, edited)
        st.caption("修改会立即用于下一次请求；不会改写磁盘提示词文件。")
        if st.button("恢复该 Prompt 默认值", width="stretch"):
            st.session_state[PROMPT_RESET_KEY] = reset_prompt_override(selected)
            st.session_state.pop(editor_key, None)
            st.rerun()


def render_alias_editor(ctx: AppContext) -> None:
    with st.expander("社区别名词典", expanded=False):
        st.caption("把玩家黑话映射到正式名（如 挖机→瓦尔基里）。保存为 workspace 覆盖文件，不改动内置词典。")
        text = st.text_area(
            "词典 JSON",
            value=alias_current_text(ctx.settings.workspace_dir),
            height=300,
            key=ALIAS_EDITOR_KEY,
        )
        left, right = st.columns(2)
        with left:
            if st.button("保存词典", width="stretch"):
                try:
                    dictionary = alias_save_override(ctx.settings.workspace_dir, text)
                    st.success(f"词典已保存（{dictionary.entry_count} 条），下次分析生效。")
                except (json.JSONDecodeError, ValueError) as exc:
                    st.error(f"词典 JSON 无效：{exc}")
        with right:
            if st.button("恢复内置词典", width="stretch"):
                alias_reset_override(ctx.settings.workspace_dir)
                st.session_state.pop(ALIAS_EDITOR_KEY, None)
                st.rerun()
