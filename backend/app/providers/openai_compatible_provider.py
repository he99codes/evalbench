"""Generic provider for any OpenAI-compatible chat-completions API (Groq, NVIDIA NIM, OpenAI...).

Configured entirely from env (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL). A single attempt per
call: errors are classified into typed LLM errors and retries happen in call_structured.
"""

from __future__ import annotations

import copy
import email.utils
import json
import re
import time
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.providers.base import (
    LLMMalformedOutputError,
    LLMPermanentError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
)

# JSON-schema keywords outside the strict structured-output subset. Constraints like
# min/max are still enforced afterwards by Pydantic validation.
_UNSUPPORTED_KEYWORDS = {
    "title", "default", "examples", "format", "pattern", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
    "minItems", "maxItems", "uniqueItems",
}


def to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic schema -> strict-mode schema: every object closed and fully required."""

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: fix(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYWORDS}
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["type"] = "object"
                node["required"] = list(props)
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    schema = fix(copy.deepcopy(model.model_json_schema()))
    if "$defs" in schema:
        schema["$defs"] = {k: fix(v) for k, v in schema["$defs"].items()}
    return schema


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
        return max(0.0, (when - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else body
        if isinstance(error, dict):
            message = str(error.get("message") or error)[:500]
            # Groq includes the model's malformed output as failed_generation;
            # a snippet of it is the single most useful diagnostic available.
            failed = error.get("failed_generation")
            if isinstance(failed, str) and failed:
                message += f" | failed_generation: {failed[:300]}"
            return message
        return str(error)[:500]
    except ValueError:
        return response.text[:500]


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 60.0,
        structured_mode: Literal["json_schema", "json_object"] = "json_schema",
        temperature: float = 0.0,
        max_completion_tokens: int | None = None,
        reasoning_effort: Literal["low", "medium", "high"] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.structured_mode = structured_mode
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.reasoning_effort = reasoning_effort
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=min(10.0, timeout_s)),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request_body(self, prompt: str, schema: type[BaseModel], system: str | None) -> dict[str, Any]:
        system = system or "Respond only with JSON."
        if self.structured_mode == "json_schema":
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True, "schema": to_strict_json_schema(schema)},
            }
        else:
            response_format = {"type": "json_object"}
            system += (
                "\nReturn a single JSON object that conforms to this JSON schema:\n"
                + json.dumps(to_strict_json_schema(schema))
            )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "response_format": response_format,
        }
        # Reasoning models (e.g. Groq's gpt-oss) spend hidden reasoning tokens inside the
        # completion budget; without an explicit cap the provider default can truncate the
        # JSON mid-generation, which fails server-side schema validation.
        if self.max_completion_tokens is not None:
            body["max_completion_tokens"] = self.max_completion_tokens
        if self.reasoning_effort is not None:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    def generate_structured(
        self, prompt: str, schema: type[BaseModel], *, system: str | None = None
    ) -> LLMResponse:
        started = time.monotonic()
        try:
            response = self._client.post("/chat/completions", json=self._request_body(prompt, schema, system))
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"LLM request timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise LLMTransientError(f"LLM connection error: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        status = response.status_code
        if status == 429:
            raise LLMRateLimitError(
                f"rate limited (429): {_error_message(response)}",
                retry_after=_parse_retry_after(response.headers.get("retry-after")),
            )
        if status >= 500 or status in (408, 409):
            raise LLMTransientError(f"provider error {status}: {_error_message(response)}")
        if status == 400 and "json_validate_failed" in response.text:
            # Groq: model output failed server-side schema validation -> retryable.
            raise LLMMalformedOutputError(f"provider rejected output: {_error_message(response)}")
        if status >= 400:
            raise LLMPermanentError(f"provider error {status}: {_error_message(response)}")

        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMMalformedOutputError(f"unexpected response envelope: {response.text[:300]}") from exc

        if message.get("refusal"):
            raise LLMPermanentError(f"model refused: {message['refusal']}")
        if choice.get("finish_reason") == "length":
            raise LLMMalformedOutputError("output was truncated (finish_reason=length)")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMMalformedOutputError("empty message content")
        text = content.strip()
        fenced = _FENCE.match(text)
        if fenced:
            text = fenced.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMMalformedOutputError(f"invalid JSON: {exc.msg} at char {exc.pos}") from exc
        if not isinstance(data, dict):
            raise LLMMalformedOutputError("JSON output is not an object")

        usage = body.get("usage") or {}
        return LLMResponse(
            data=data,
            raw_text=content,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )
