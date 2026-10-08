from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, TypeVar, get_origin

import requests
from openai import OpenAI
from pydantic import TypeAdapter, ValidationError

from ..core.settings import Settings
from .prompt_store import read_prompt

T = TypeVar("T")

# GLM-5.x reasoning is always on, so the output budget must cover both the
# chain of thought and the JSON answer — otherwise the response truncates
# mid-object and the whole batch gets rejected.
TEXT_MAX_TOKENS = 32000


class SiliconFlowError(RuntimeError):
    pass


class _TransientUpstreamError(SiliconFlowError):
    """Retryable upstream failure (5xx/429, or timeout before any content arrived)."""


def _exception_chain(exc: Exception) -> list[dict[str, str]]:
    output = []
    current: Exception | None = exc
    while current is not None:
        output.append({"type": type(current).__name__, "message": str(current)})
        current = current.__cause__
    return output


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        starts = [position for position in (stripped.find("{"), stripped.find("[")) if position >= 0]
        if not starts:
            raise SiliconFlowError("模型响应中没有可解析的 JSON。") from exc
        end = max(stripped.rfind("}"), stripped.rfind("]"))
        try:
            return json.loads(stripped[min(starts) : end + 1])
        except json.JSONDecodeError as nested:
            raise SiliconFlowError("模型返回了无效 JSON。") from nested


def _strict_json_document(text: str) -> Any:
    """Parse the entire model document; never trim trailing partial data."""
    stripped = text.strip()
    fence = chr(96) * 3
    if stripped.startswith(fence):
        first_newline = stripped.find("\n")
        header = stripped[:first_newline].strip().casefold() if first_newline >= 0 else ""
        if first_newline < 0 or header not in (fence, fence + "json") or not stripped.endswith(fence):
            raise SiliconFlowError("模型返回了不完整的 JSON 代码块。")
        stripped = stripped[first_newline + 1 : -len(fence)].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise SiliconFlowError("模型返回的完整 JSON 文档无效或已截断。") from exc


def _can_recover_schannel_close(
    returncode: int,
    stderr: str,
    content: str,
    *,
    http_status: int,
    saw_sse: bool,
    saw_done: bool,
    finish_reason: str | None,
    malformed_sse_chunks: int,
) -> bool:
    """Accept curl 56 only after a strict, complete application document."""
    error_text = (stderr or "").casefold()
    known_close = (
        returncode == 56
        and "schannel" in error_text
        and ("close_notify" in error_text or "server closed abruptly" in error_text)
    )
    if not known_close or not 200 <= http_status < 300:
        return False
    if not saw_sse or not content.strip() or malformed_sse_chunks:
        return False
    if finish_reason not in (None, "stop"):
        return False
    try:
        _strict_json_document(content)
    except SiliconFlowError:
        return False
    return saw_done or finish_reason == "stop" or finish_reason is None

class SiliconFlowClient:
    def __init__(self, settings: Settings, event_sink: Callable[[dict[str, Any]], None] | None = None, call_guard: Callable[[], bool] | None = None):
        self.settings = settings
        self._event_sink = event_sink
        self._call_guard = call_guard
        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=180.0, max_retries=0) if settings.api_key else None

    def _emit(self, event: dict[str, Any]) -> None:
        if self._event_sink:
            self._event_sink(event)

    def _begin(self, operation: str, model: str) -> tuple[str, float]:
        if self._call_guard and not self._call_guard():
            raise SiliconFlowError("已达到本次会话 API 调用上限。请检查结果后再提高限额，避免重复消耗。")
        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        self._emit({"request_id": request_id, "operation": operation, "model": model, "status": "运行中", "elapsed": 0.0, "detail": "请求已发送"})
        return request_id, started

    def _finish(self, request_id: str, operation: str, model: str, started: float, status: str, detail: str, usage: dict[str, Any] | None = None) -> None:
        event: dict[str, Any] = {"request_id": request_id, "operation": operation, "model": model, "status": status, "elapsed": round(time.perf_counter() - started, 2), "detail": detail[:500]}
        if usage:
            event["usage"] = usage
        self._emit(event)

    @staticmethod
    def list_available_models(api_key: str, base_url: str) -> list[str]:
        if not api_key.strip() or not base_url.strip():
            raise SiliconFlowError("请填写 API Key 和 Base URL。")
        normalized_url = base_url.strip().split()[0].rstrip("/")
        for suffix in ("/chat/completions", "/completions", "/models"):
            if normalized_url.lower().endswith(suffix):
                normalized_url = normalized_url[: -len(suffix)].rstrip("/")
                break
        try:
            client = OpenAI(api_key=api_key.strip(), base_url=normalized_url, timeout=30.0, max_retries=0)
            response = client.models.list()
            model_ids = sorted({item.id for item in response.data if getattr(item, "id", None)})
            if not model_ids:
                raise SiliconFlowError("API 已连接，但没有返回可用模型。")
            return model_ids
        except Exception as exc:
            if isinstance(exc, SiliconFlowError):
                raise
            raise SiliconFlowError(f"获取模型列表失败（{type(exc).__name__}）。请检查 Key、Base URL 和网络连接。") from exc

    def require_text(self) -> None:
        if not self.settings.text_ready:
            raise SiliconFlowError("请先配置 API Key、Base URL 和文本模型。")

    # ------------------------------------------------------------------
    # Shared curl SSE transport
    # ------------------------------------------------------------------
    def _stream_with_retry(self, operation: str, model: str, payload: dict[str, Any], on_delta: Callable[[str, str], None] | None) -> dict[str, Any]:
        """Compatibility entry point that deliberately performs one request.

        SiliconFlow does not provide an idempotency key for chat completions.
        DNS, TLS, timeout, 429, 5xx, and partial-stream failures therefore
        require an explicit user decision before another potentially billed call.
        """
        endpoint = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        return self._curl_sse_once(operation, model, endpoint, payload, on_delta, attempt=1)
    def _curl_sse_once(self, operation: str, model: str, endpoint: str, payload: dict[str, Any], on_delta: Callable[[str, str], None] | None, attempt: int) -> dict[str, Any]:
        """One streaming attempt via Windows curl (Schannel, bypasses the flaky
        system proxy/SSL stack that breaks requests/OpenAI SDK on this host).

        Returns {"content", "reasoning", "usage", "finish_reason", "chunks"}.
        Raises _TransientUpstreamError for retryable failures, SiliconFlowError otherwise.
        """
        attempt_label = f"{operation}（第 {attempt} 次尝试）" if attempt > 1 else operation
        request_id, started = self._begin(attempt_label, model)
        payload_path: Path | None = None
        curl_status = 0
        curl_stderr = ""
        curl_returncode = 0
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        raw_lines: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason: str | None = None
        chunk_count = 0
        saw_sse = False
        saw_done = False
        transport_recovered = False
        malformed_sse_chunks = 0
        try:
            curl_executable = shutil.which("curl.exe") or shutil.which("curl")
            if not curl_executable:
                raise SiliconFlowError("Windows curl is required for API requests.")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as payload_file:
                json.dump(payload, payload_file, ensure_ascii=False)
                payload_path = Path(payload_file.name)
            curl_config = "\n".join([
                f'url = "{endpoint}"', 'request = "POST"',
                f'header = "Authorization: Bearer {self.settings.api_key}"',
                'header = "Content-Type: application/json"',
                f'data-binary = "@{payload_path.as_posix()}"',
                'silent', 'show-error', 'no-buffer', 'http1.1',
                'connect-timeout = 20', 'max-time = 600',
                # Idle guard: abort if the stream trickles below 1 B/s for 90 s.
                'speed-limit = 1', 'speed-time = 90',
                'write-out = "\\n__STATUS__:%{http_code}"',
            ])
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                [curl_executable, "--config", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", creationflags=creation_flags,
            )
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            process.stdin.write(curl_config)
            process.stdin.close()
            status_marker = "__STATUS__:"
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith(status_marker):
                    try:
                        curl_status = int(line[len(status_marker):].strip() or 0)
                    except ValueError:
                        curl_status = 0
                    continue
                if not line.startswith("data:"):
                    raw_lines.append(line)
                    continue
                saw_sse = True
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    saw_done = True
                    continue  # keep reading until the __STATUS__ marker / EOF
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    malformed_sse_chunks += 1
                    raw_lines.append(f"malformed_sse:{data[:500]}")
                    continue
                chunk_count += 1
                chunk_usage = chunk.get("usage")
                if isinstance(chunk_usage, dict) and chunk_usage.get("total_tokens"):
                    usage = chunk_usage
                piece: str | None = None
                thought: str | None = None
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        content_parts.append(piece)
                    thought = delta.get("reasoning_content")
                    if thought:
                        reasoning_parts.append(thought)
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]
                if on_delta and (piece or thought):
                    try:
                        on_delta("".join(content_parts), "".join(reasoning_parts))
                    except Exception:
                        pass  # UI callback must never kill the request
            curl_returncode = process.wait(timeout=30)
            curl_stderr = process.stderr.read() if process.stderr else ""
            raw_text = "\n".join(raw_lines)
            content = "".join(content_parts)
            reasoning = "".join(reasoning_parts)
            transport_recovered = _can_recover_schannel_close(
                curl_returncode,
                curl_stderr,
                content,
                http_status=curl_status,
                saw_sse=saw_sse,
                saw_done=saw_done,
                finish_reason=finish_reason,
                malformed_sse_chunks=malformed_sse_chunks,
            )
            self._emit({"kind": "response_preview", "operation": attempt_label, "response_payload": {
                "http_status": curl_status, "transport": "Windows curl SSE stream",
                "chunks": chunk_count, "finish_reason": finish_reason,
                "saw_done": saw_done, "malformed_sse_chunks": malformed_sse_chunks,
                "content_chars": len(content), "reasoning_chars": len(reasoning),
                "usage": usage, "raw_content": content[:12000], "reasoning_tail": reasoning[-2000:],
                "curl_exit_code": curl_returncode, "curl_stderr": curl_stderr[:2000],
                "transport_recovered": transport_recovered, "may_be_billed": bool(curl_status or chunk_count),
            }})
            if curl_returncode != 0 and not transport_recovered:
                received_chars = len(content) + len(reasoning)
                message = (
                    f"流式请求中断（curl exit={curl_returncode}，HTTP={curl_status or '未完成'}，"
                    f"chunks={chunk_count}，正文/思考共 {received_chars} 字，finish_reason={finish_reason}）："
                    f"{curl_stderr[:400] or '无详情'}"
                )
                if not content and not reasoning and chunk_count == 0 and curl_status == 0:
                    raise _TransientUpstreamError(f"{message}。未收到响应数据；本应用仍不会自动重试。")
                raise SiliconFlowError(f"{message}。请求可能已计费，本应用不会自动重试。")
            if curl_status == 0 and not transport_recovered:
                raise SiliconFlowError("请求结束但未获得完整 HTTP 状态；为避免重复计费，不会自动重试。")
            if curl_status and not 200 <= curl_status < 300:
                if curl_status in (429, 500, 502, 503, 504) and chunk_count == 0:
                    raise _TransientUpstreamError(f"SiliconFlow HTTP {curl_status}: {raw_text[:500]}。不会自动重试。")
                raise SiliconFlowError(f"SiliconFlow HTTP {curl_status}: {raw_text[:1000]}")
            if not saw_sse:
                # Server ignored stream=True and answered with a plain JSON body.
                body = json.loads(raw_text)
                message = body.get("choices", [{}])[0].get("message", {})
                content = message.get("content", "") or ""
                reasoning = message.get("reasoning_content", "") or ""
                finish_reason = (body.get("choices") or [{}])[0].get("finish_reason") or finish_reason
                usage = body.get("usage", {}) or usage
            return {
                "content": content, "reasoning": reasoning, "usage": usage,
                "finish_reason": finish_reason, "chunks": chunk_count, "http_status": curl_status,
                "transport_recovered": transport_recovered, "curl_exit_code": curl_returncode,
                "saw_done": saw_done, "malformed_sse_chunks": malformed_sse_chunks,
                "_request_id": request_id, "_started": started,
                "_attempt_label": attempt_label, "_model": model,
            }
        except ValidationError:
            raise  # pydantic errors happen in the callers, but keep the guard
        except Exception as exc:
            self._emit({"kind": "response_preview", "operation": attempt_label, "response_payload": {
                "error_chain": _exception_chain(exc), "http_status": curl_status,
                "content_so_far": "".join(content_parts)[-4000:], "reasoning_so_far": "".join(reasoning_parts)[-1000:],
                "raw_lines": "\n".join(raw_lines)[:4000], "curl_stderr": curl_stderr[:2000],
                "curl_exit_code": curl_returncode, "transport": "Windows curl SSE stream",
                "chunks": chunk_count, "finish_reason": finish_reason, "saw_done": saw_done,
                "malformed_sse_chunks": malformed_sse_chunks,
                "content_chars": len("".join(content_parts)), "reasoning_chars": len("".join(reasoning_parts)),
                "usage": usage, "partial": True, "may_be_billed": bool(curl_status or chunk_count),
                "auto_retry": False, "transport_recovered": transport_recovered,
            }})
            self._finish(request_id, attempt_label, model, started, "failed", str(exc), usage or None)
            if isinstance(exc, SiliconFlowError):
                raise
            raise SiliconFlowError(f"API 请求失败: {type(exc).__name__}: {exc}") from exc
        finally:
            if payload_path is not None:
                payload_path.unlink(missing_ok=True)

    def _validate_and_finish(self, operation: str, outcome: dict[str, Any], output_type: type[T]) -> T:
        """Record final success only after strict JSON and schema validation."""
        try:
            result = self._validate_model_json(operation, outcome, output_type)
        except Exception as exc:
            self._emit({
                "kind": "response_preview",
                "operation": outcome["_attempt_label"],
                "response_payload": {
                    "validation_error": str(exc),
                    "transport_recovered": outcome.get("transport_recovered", False),
                    "curl_exit_code": outcome.get("curl_exit_code"),
                    "http_status": outcome.get("http_status"),
                    "chunks": outcome.get("chunks"),
                    "finish_reason": outcome.get("finish_reason"),
                    "saw_done": outcome.get("saw_done"),
                    "malformed_sse_chunks": outcome.get("malformed_sse_chunks"),
                    "usage": outcome.get("usage") or {},
                    "auto_retry": False,
                    "may_be_billed": True,
                },
            })
            self._finish(
                outcome["_request_id"], outcome["_attempt_label"], outcome["_model"], outcome["_started"],
                "failed", f"响应校验失败：{exc}", outcome.get("usage") or None,
            )
            raise

        usage = outcome.get("usage") or {}
        total_tokens = usage.get("total_tokens", "unknown")
        if outcome.get("transport_recovered"):
            detail = f"TLS 关闭异常，但完整 JSON 与数据结构校验通过；tokens={total_tokens}, chunks={outcome.get('chunks', 0)}"
        else:
            detail = f"tokens={total_tokens}, chunks={outcome.get('chunks', 0)}"
        self._finish(
            outcome["_request_id"], outcome["_attempt_label"], outcome["_model"], outcome["_started"],
            "success", detail, usage or None,
        )
        return result
    def _validate_model_json(self, operation: str, outcome: dict[str, Any], output_type: type[T]) -> T:
        """Shared post-processing: empty guards, JSON extraction, schema validation."""
        content = outcome["content"]
        reasoning = outcome["reasoning"]
        finish_reason = outcome["finish_reason"]
        usage = outcome["usage"]
        if finish_reason == "length":
            raise SiliconFlowError(
                f"模型输出达到 max_tokens 上限（completion_tokens={usage.get('completion_tokens', '?')}），"
                "即使 JSON 可解析也可能缺少条目；不会当作完整结果保存。"
            )
        if finish_reason not in (None, "stop"):
            raise SiliconFlowError(f"模型未正常完成（finish_reason={finish_reason}），不会保存可能不完整的结果。")
        if not content.strip():
            if reasoning.strip():
                raise SiliconFlowError(
                    f"模型仅输出思考内容（reasoning {len(reasoning)} 字，finish_reason={finish_reason}），未给出结果。"
                    "通常是 max_tokens 被思考占满；请调大 max_tokens 或改用非思考型模型。"
                )
            raise SiliconFlowError(f"模型返回为空（HTTP {outcome.get('http_status')}，finish_reason={finish_reason}）。原始响应已记录到 API 控制台。")
        try:
            parser = _strict_json_document if outcome.get("transport_recovered") else _extract_json
            parsed = parser(content)
        except SiliconFlowError as exc:
            if finish_reason == "length":
                raise SiliconFlowError(
                    f"输出被 max_tokens 截断（finish_reason=length，completion_tokens={usage.get('completion_tokens', '?')}），"
                    f"JSON 不完整无法解析。请调大 max_tokens 后重试。"
                ) from exc
            raise
        if get_origin(output_type) is list and isinstance(parsed, dict):
            list_value = next((parsed[key] for key in ("changes", "analyses", "insights", "items", "results", "data") if isinstance(parsed.get(key), list)), None)
            if list_value is None and len(parsed) == 1:
                only_value = next(iter(parsed.values()))
                list_value = only_value if isinstance(only_value, list) else None
            if list_value is not None:
                parsed = list_value
        try:
            return TypeAdapter(output_type).validate_python(parsed)
        except ValidationError as exc:
            raise SiliconFlowError(f"模型 JSON 不符合数据结构：{exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def text_json(self, system_prompt: str, user_payload: Any, output_type: type[T], on_delta: Callable[[str, str], None] | None = None) -> T:
        """Structured text request over the shared SSE transport.

        ``temperature`` stays at 0 so repeated runs over the same corpus stay
        comparable — the whole pipeline is built around auditable, reproducible
        output rather than creative variety.
        """
        self.require_text()
        operation = "文本分析"
        reasoning_effort = self.settings.reasoning_effort
        payload = {
            "model": self.settings.text_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 0,
            "max_tokens": TEXT_MAX_TOKENS,
            "reasoning_effort": reasoning_effort,
            "response_format": {"type": "json_object"},
        }
        self._emit({
            "kind": "request_preview",
            "operation": operation,
            "request_payload": {
                "transport": "Windows curl SSE stream (Schannel, direct)",
                "endpoint": "/chat/completions", "model": self.settings.text_model,
                "system_prompt": system_prompt, "user_payload": user_payload,
                "temperature": 0, "reasoning_effort": reasoning_effort,
                "max_tokens": TEXT_MAX_TOKENS, "stream": True,
            },
        })
        outcome = self._stream_with_retry(operation, self.settings.text_model, payload, on_delta)
        return self._validate_and_finish(operation, outcome, output_type)

def load_prompt(name: str) -> str:
    return read_prompt(name)
