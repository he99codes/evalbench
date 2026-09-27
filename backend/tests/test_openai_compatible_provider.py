"""OpenAI-compatible provider against a fake HTTP transport (no network)."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.providers import ProviderConfigError, get_llm_provider
from app.providers.base import (
    LLMMalformedOutputError,
    LLMPermanentError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.providers.mock_provider import MockLLMProvider
from app.providers.openai_compatible_provider import OpenAICompatibleProvider, to_strict_json_schema
from app.utils.validation import CriterionEvaluationOutput, RequirementExtractionOutput


def _ok(content, usage=None, finish="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 120, "completion_tokens": 30},
        },
    )


def _provider(handler, mode="json_schema"):
    return OpenAICompatibleProvider(
        base_url="https://api.example.test/openai/v1/",
        api_key="test-key",
        model="openai/gpt-oss-20b",
        structured_mode=mode,
        transport=httpx.MockTransport(handler),
    )


VALID = {"criterion": "Tone", "score": 4, "passed": True, "reasoning": "r", "evidence": [{"quote": "q", "supports": "s"}]}


def test_request_shape_and_success():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _ok(json.dumps(VALID))

    result = _provider(handler).generate_structured("prompt text", CriterionEvaluationOutput, system="sys")
    assert seen["url"] == "https://api.example.test/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["model"] == "openai/gpt-oss-20b" and body["temperature"] == 0
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "prompt text"}]
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert result.data == VALID
    assert (result.input_tokens, result.output_tokens) == (120, 30)


def test_strict_schema_is_closed_and_fully_required():
    schema = to_strict_json_schema(RequirementExtractionOutput)

    def walk(node):
        if isinstance(node, dict):
            assert "title" not in node and "default" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    assert schema["required"] == ["requests", "constraints", "format_requirements", "ambiguities"]


def test_json_object_mode_embeds_schema_and_strips_fences():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _ok("```json\n" + json.dumps(VALID) + "\n```")

    result = _provider(handler, mode="json_object").generate_structured("p", CriterionEvaluationOutput)
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in seen["body"]["messages"][0]["content"]
    assert result.data == VALID


def test_429_is_rate_limit_with_retry_after():
    provider = _provider(lambda r: httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "slow down"}}))
    with pytest.raises(LLMRateLimitError) as info:
        provider.generate_structured("p", CriterionEvaluationOutput)
    assert info.value.retry_after == 7.0 and "slow down" in str(info.value)


@pytest.mark.parametrize("status", [500, 502, 503, 408])
def test_server_errors_are_transient(status):
    with pytest.raises(LLMTransientError) as info:
        _provider(lambda r: httpx.Response(status, text="boom")).generate_structured("p", CriterionEvaluationOutput)
    assert not isinstance(info.value, LLMRateLimitError)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_permanent(status):
    with pytest.raises(LLMPermanentError):
        _provider(lambda r: httpx.Response(status, json={"error": {"message": "nope"}})).generate_structured(
            "p", CriterionEvaluationOutput
        )


def test_groq_json_validate_failed_is_malformed_not_permanent():
    resp = httpx.Response(400, json={"error": {"message": "Failed to validate JSON", "code": "json_validate_failed"}})
    with pytest.raises(LLMMalformedOutputError):
        _provider(lambda r: resp).generate_structured("p", CriterionEvaluationOutput)


def test_timeout_and_connection_errors():
    def timeout(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMTimeoutError):
        _provider(timeout).generate_structured("p", CriterionEvaluationOutput)
    with pytest.raises(LLMTransientError):
        _provider(refused).generate_structured("p", CriterionEvaluationOutput)


@pytest.mark.parametrize(
    "response",
    [
        _ok("this is not json"),
        _ok('{"criterion": "Tone", "score": '),
        _ok("[1, 2, 3]"),
        _ok(""),
        _ok(json.dumps(VALID), finish="length"),
        httpx.Response(200, json={"unexpected": True}),
    ],
)
def test_malformed_outputs(response):
    with pytest.raises(LLMMalformedOutputError):
        _provider(lambda r: response).generate_structured("p", CriterionEvaluationOutput)


def test_refusal_is_permanent():
    resp = httpx.Response(200, json={"choices": [{"message": {"content": None, "refusal": "I can't"}, "finish_reason": "stop"}]})
    with pytest.raises(LLMPermanentError):
        _provider(lambda r: resp).generate_structured("p", CriterionEvaluationOutput)


def test_factory_selects_provider_from_config_without_code_changes():
    assert isinstance(get_llm_provider(Settings(llm_provider="mock")), MockLLMProvider)
    assert get_llm_provider(Settings(llm_provider="mock")).model == "mock"
    real = get_llm_provider(Settings(llm_provider="openai_compatible", llm_api_key="k"))
    assert isinstance(real, OpenAICompatibleProvider)
    assert (real.name, real.model) == ("openai_compatible", "openai/gpt-oss-20b")
    custom = get_llm_provider(
        Settings(llm_provider="openai_compatible", llm_api_key="k", llm_model="meta/llama-3.3-70b-instruct",
                 llm_base_url="https://integrate.api.nvidia.com/v1")
    )
    assert custom.model == "meta/llama-3.3-70b-instruct"
    with pytest.raises(ProviderConfigError):
        get_llm_provider(Settings(llm_provider="openai_compatible", llm_api_key=None))


def test_token_budget_and_reasoning_effort_in_request():
    """Regression: reasoning models truncate JSON without an explicit completion cap."""
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return _ok(json.dumps(VALID))

    provider = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="openai/gpt-oss-20b",
        max_completion_tokens=8192,
        reasoning_effort="low",
        transport=httpx.MockTransport(handler),
    )
    provider.generate_structured("p", CriterionEvaluationOutput)
    assert seen["body"]["max_completion_tokens"] == 8192
    assert seen["body"]["reasoning_effort"] == "low"

    seen.clear()
    bare = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    bare.generate_structured("p", CriterionEvaluationOutput)
    assert "max_completion_tokens" not in seen["body"]
    assert "reasoning_effort" not in seen["body"]


def test_failed_generation_included_in_error():
    from app.providers.base import LLMCallFailedError
    from app.providers.base import RetryPolicy
    from app.providers.base import call_structured

    def handler(request: httpx.Request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Failed to validate JSON. See 'failed_generation' for more details.",
                    "code": "json_validate_failed",
                    "failed_generation": '{"criterion": "Tone", "score": "f',
                }
            },
        )

    provider = _provider(handler)
    with pytest.raises(LLMCallFailedError) as excinfo:
        call_structured(
            provider,
            "p",
            CriterionEvaluationOutput,
            policy=RetryPolicy(max_attempts=1, base_delay_s=0),
            sleep=lambda s: None,
        )
    assert "failed_generation" in excinfo.value.errors[0]
