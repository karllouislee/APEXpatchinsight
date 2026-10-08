from __future__ import annotations

import time
import uuid
from collections.abc import MutableMapping
from typing import Any


class ApiMonitor:
    def __init__(self, state: MutableMapping[str, Any]):
        self.state = state
        self.state.setdefault("api_events", [])
        self.state.setdefault("api_call_count", 0)
        self.state.setdefault("api_call_limit", 20)

    @property
    def count(self) -> int:
        return int(self.state["api_call_count"])

    @property
    def limit(self) -> int:
        return int(self.state["api_call_limit"])

    def allow_client_call(self) -> bool:
        if self.count + 1 > self.limit:
            self._append("API 请求", "", "已阻止", 0.0, f"已达到会话限额 {self.limit}")
            return False
        self.state["api_call_count"] = self.count + 1
        return True

    def record_client_event(self, event: dict[str, Any]) -> None:
        if event.get("kind") == "request_preview":
            self.state["api_last_request"] = event.get("request_payload", {})
            return
        if event.get("kind") == "response_preview":
            self.state["api_last_response"] = event.get("response_payload", {})
            return
        usage = event.get("usage") or {}
        if usage:
            totals = self.state.setdefault("api_token_totals", {"prompt": 0, "completion": 0, "reasoning": 0, "total": 0})
            totals["prompt"] += int(usage.get("prompt_tokens") or 0)
            totals["completion"] += int(usage.get("completion_tokens") or 0)
            details = usage.get("completion_tokens_details") or {}
            totals["reasoning"] += int(details.get("reasoning_tokens") or 0)
            totals["total"] += int(usage.get("total_tokens") or 0)
        self._append(
            str(event.get("operation", "API 请求")),
            str(event.get("model", "")),
            str(event.get("status", "未知")),
            float(event.get("elapsed", 0.0)),
            str(event.get("detail", "")),
            str(event.get("request_id", "")) or None,
            int(usage.get("total_tokens")) if usage.get("total_tokens") else None,
        )

    def start(self, operation: str, estimated_calls: int = 1, model: str = "") -> tuple[str, float] | None:
        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        self._append(operation, model, "准备中", 0.0, f"预计 {max(1, estimated_calls)} 次请求", request_id)
        return request_id, started

    def finish(self, ticket: tuple[str, float], operation: str, status: str, detail: str, model: str = "") -> None:
        request_id, started = ticket
        self._append(operation, model, status, round(time.perf_counter() - started, 2), detail, request_id)

    def clear(self) -> None:
        self.state["api_events"] = []
        self.state["api_token_totals"] = {"prompt": 0, "completion": 0, "reasoning": 0, "total": 0}

    def token_totals(self) -> dict[str, int]:
        totals = self.state.get("api_token_totals") or {}
        return {
            "prompt": int(totals.get("prompt", 0)),
            "completion": int(totals.get("completion", 0)),
            "reasoning": int(totals.get("reasoning", 0)),
            "total": int(totals.get("total", 0)),
        }

    def last_request(self) -> dict[str, Any]:
        return dict(self.state.get("api_last_request", {}))

    def rows(self) -> list[dict[str, Any]]:
        return list(reversed(self.state["api_events"][-50:]))

    def _append(self, operation: str, model: str, status: str, elapsed: float, detail: str, request_id: str | None = None, tokens: int | None = None) -> None:
        self.state["api_events"].append({
            "ID": request_id or uuid.uuid4().hex[:8], "操作": operation, "模型": model,
            "状态": status, "耗时(秒)": elapsed, "Tokens": tokens if tokens is not None else "—",
            "详情": detail[:500],
        })
