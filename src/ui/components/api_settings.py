"""Sidebar panel: API key, base URL, text model, and reasoning effort."""
from __future__ import annotations

import streamlit as st

from ...core.settings import (
    DEFAULT_REASONING_EFFORT,
    REASONING_EFFORTS,
    RECOMMENDED_TEXT_MODEL,
    save_api_settings,
)
from ...integrations.siliconflow_client import SiliconFlowClient, SiliconFlowError
from ..state import AppContext

# Model families that cannot produce chat completions.
EXCLUDED_MODEL_MARKERS = (
    "embedding", "rerank", "stable-diffusion", "flux", "kolors",
    "whisper", "sensevoice", "tts", "text-to-image", "video",
)
DEFAULT_BASE_URL = "https://api.siliconflow.com/v1"

REASONING_HINTS = {
    "low": "最省 token、最快。适合分类、抽取与简短归纳。",
    "high": "推理深度与延迟平衡，本项目默认。",
    "max": "最深推理，最贵最慢。适合困难的一次性复杂推理。",
}


def _model_choices(available: list[str], current: str) -> list[str]:
    preferred = [name for name in available if not any(marker in name.lower() for marker in EXCLUDED_MODEL_MARKERS)]
    return list(dict.fromkeys([name for name in [current, *preferred, *available] if name])) or [""]


def render_api_settings(ctx: AppContext) -> None:
    """Connection settings; values are stored only in the local .env."""
    settings = ctx.settings
    with st.expander("API 与模型设置", expanded=not settings.api_key):
        api_entry = st.text_input(
            "API Key",
            type="password",
            placeholder="已保存则可留空；新 Key 不会回显",
            key="siliconflow_api_entry",
        )
        base_url_entry = st.text_input("Base URL", value=settings.base_url or DEFAULT_BASE_URL, key="siliconflow_base_url_entry")
        if st.button("测试连接并读取模型", width="stretch"):
            _probe_models(ctx, api_entry, base_url_entry)

        available = st.session_state.get("siliconflow_models", [])
        choices = _model_choices(available, settings.text_model)
        text_model = st.selectbox("文本分析模型", choices, key="siliconflow_text_select")

        effort_index = REASONING_EFFORTS.index(settings.reasoning_effort) if settings.reasoning_effort in REASONING_EFFORTS else REASONING_EFFORTS.index(DEFAULT_REASONING_EFFORT)
        reasoning_effort = st.selectbox("思考强度", list(REASONING_EFFORTS), index=effort_index, key="siliconflow_reasoning_select")
        st.caption(REASONING_HINTS.get(reasoning_effort, ""))

        if st.button("保存配置", type="primary", width="stretch"):
            _save_settings(ctx, api_entry, base_url_entry, text_model, reasoning_effort)


def _probe_models(ctx: AppContext, api_entry: str, base_url: str) -> None:
    effective_key = api_entry.strip() or ctx.settings.api_key
    operation = "读取模型列表"
    ticket = ctx.monitor.start(operation)
    try:
        if not ctx.monitor.allow_client_call():
            raise SiliconFlowError("已达到本次会话 API 调用上限。")
        with st.spinner("正在读取可用模型…"):
            st.session_state.siliconflow_models = SiliconFlowClient.list_available_models(effective_key, base_url)
        ctx.monitor.finish(
            ticket, operation, "成功", f"读取 {len(st.session_state.siliconflow_models)} 个模型"
        )
        st.success(f"连接成功，读取到 {len(st.session_state.siliconflow_models)} 个模型。")
    except SiliconFlowError as exc:
        ctx.monitor.finish(ticket, operation, "失败", str(exc))
        st.error(str(exc))


def _save_settings(ctx: AppContext, api_entry: str, base_url: str, text_model: str, reasoning_effort: str) -> None:
    effective_key = api_entry.strip() or ctx.settings.api_key
    if not effective_key:
        st.warning("请填写 API Key。")
    elif not text_model:
        st.warning("请选择文本分析模型。")
    else:
        save_api_settings(effective_key, base_url, text_model, reasoning_effort)
        st.success("配置已仅保存到本机 .env，正在刷新应用。")
        st.rerun()
