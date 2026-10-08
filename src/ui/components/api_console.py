"""Sidebar console for inspecting API traffic, token usage, and transport recovery."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...integrations.siliconflow_client import SiliconFlowError
from ..state import AppContext


def _is_interesting(payload: dict) -> bool:
    return bool(
        payload.get("error_chain")
        or payload.get("partial")
        or payload.get("transport_recovered")
        or payload.get("validation_error")
    )


def _render_last_response(payload: dict) -> None:
    if payload.get("validation_error"):
        st.error("传输已结束，但 JSON / 数据结构校验失败；结果未保存，也未自动重试。")
    elif payload.get("transport_recovered"):
        st.success(
            "检测到 Schannel 缺少 close_notify；已复用本次响应，完整 JSON 与数据结构校验均已通过，没有再次调用 API。"
        )
    elif payload.get("partial"):
        st.warning(
            f"网络接收中断 · curl {payload.get('curl_exit_code')} · HTTP {payload.get('http_status') or '未完整返回'} · "
            f"{payload.get('chunks', 0)} chunks · 正文 {payload.get('content_chars', 0)} 字 · "
            f"思考 {payload.get('reasoning_chars', 0)} 字。Token usage 可能未返回，请求可能已计费；未自动重试。"
        )
    st.caption("最近一次 API 原始返回或异常")
    st.json(payload, expanded=False)


def render_api_console(ctx: AppContext) -> None:
    monitor = ctx.monitor
    with st.expander("API 调用控制台", expanded=_is_interesting(st.session_state.get("api_last_response") or {})):
        st.session_state.api_call_limit = st.number_input(
            "本次会话最大请求数",
            min_value=1,
            max_value=100,
            value=int(st.session_state.api_call_limit),
            help="达到上限后阻止新请求。",
        )
        st.caption(f"已预留/调用：{monitor.count} / {monitor.limit}")

        totals = monitor.token_totals()
        if totals["total"]:
            st.caption(
                f"Token 累计（仅统计上游已返回 usage 的请求）：输入 {totals['prompt']:,} · "
                f"输出 {totals['completion']:,}（含思考 {totals['reasoning']:,}）· 共 {totals['total']:,}"
            )

        events = monitor.rows()
        if events:
            st.dataframe(pd.DataFrame(events), width="stretch", hide_index=True)
        else:
            st.caption("暂无 API 请求。")

        last_request = monitor.last_request()
        if last_request:
            st.caption("最近一次发送给 API 的内容")
            st.json(last_request, expanded=False)

        last_response = st.session_state.get("api_last_response", {})
        if last_response:
            _render_last_response(last_response)

        if st.button("运行最小文本诊断", disabled=not ctx.settings.text_ready, width="stretch"):
            try:
                diagnostic = ctx.client.text_json("只返回 JSON 对象。", {"ping": "pong"}, dict)
                st.success(f"诊断成功：{diagnostic}")
            except SiliconFlowError as exc:
                st.error(f"诊断失败：{exc}")

        if st.button("清空控制台日志", width="stretch"):
            monitor.clear()
            st.rerun()
