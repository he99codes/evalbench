"""Retry behaviour for transient failures, rate limits and malformed output."""

import json
from pathlib import Path

import pytest

from app.models import EvaluationRun, RunStatus
from app.providers.base import (
    LLMCallFailedError,
    LLMMalformedOutputError,
    LLMPermanentError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
    RetryPolicy,
    call_structured,
)
from app.providers.mock_provider import MockLLMProvider
from app.services import evaluation_service
from app.utils.validation import ImprovementOutput

GOOD = {"target_response": "A", "improvement": "Shorten it."}


class Scripted:
    """Provider double that plays back a script of exceptions / payloads."""

    name, model = "scripted", "scripted-1"

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def generate_structured(self, prompt, schema, *, system=None):
        self.calls += 1
        step = self.script.pop(0) if self.script else GOOD
        if isinstance(step, Exception):
            raise step
        return LLMResponse(data=step, raw_text=json.dumps(step), input_tokens=10, output_tokens=5)


def _call(provider, policy=RetryPolicy(max_attempts=3, rate_limit_max_attempts=5, base_delay_s=1, max_delay_s=8)):
    sleeps = []
    result = call_structured(provider, "p", ImprovementOutput, policy=policy, sleep=sleeps.append)
    return result, sleeps


def test_transient_then_success_with_exponential_backoff():
    provider = Scripted(LLMTimeoutError("t1"), LLMTransientError("503"), GOOD)
    result, sleeps = _call(provider)
    assert result.output.improvement == "Shorten it."
    assert result.attempts == 3 and sleeps == [1, 2]
    assert [e.split(":")[0] for e in result.errors] == ["LLMTimeoutError", "LLMTransientError"]


def test_rate_limit_honours_retry_after_and_has_larger_budget():
    provider = Scripted(*[LLMRateLimitError("429", retry_after=3)] * 4, GOOD)
    result, sleeps = _call(provider)  # 4 rate limits > max_attempts=3, but < rate_limit budget 5
    assert result.attempts == 5 and sleeps == [3, 3, 3, 3]


def test_rate_limit_without_retry_after_backs_off_and_caps():
    provider = Scripted(*[LLMRateLimitError("429")] * 4, GOOD)
    _, sleeps = _call(provider)
    assert sleeps == [1, 2, 4, 8]
    provider = Scripted(LLMRateLimitError("429", retry_after=120), GOOD)
    _, sleeps = _call(provider)
    assert sleeps == [8]  # capped at max_delay_s


def test_rate_limit_budget_exhausted():
    provider = Scripted(*[LLMRateLimitError("429", retry_after=0)] * 10)
    with pytest.raises(LLMCallFailedError) as info:
        _call(provider)
    assert info.value.attempts == 5 and provider.calls == 5


def test_malformed_then_success():
    provider = Scripted({"target_response": "C"}, {"nope": 1}, GOOD)
    result, _ = _call(provider)
    assert result.attempts == 3 and all("LLMMalformedOutputError" in e for e in result.errors)


def test_postprocess_rejection_is_retried():
    provider = Scripted({"target_response": "A", "improvement": "  "}, GOOD)

    def reject_blank(out):
        if not out.improvement.strip():
            raise ValueError("blank")
        return out

    result = call_structured(provider, "p", ImprovementOutput, postprocess=reject_blank, sleep=lambda s: None)
    assert result.attempts == 2


def test_permanent_error_is_not_retried():
    provider = Scripted(LLMPermanentError("401"), GOOD)
    with pytest.raises(LLMCallFailedError) as info:
        _call(provider)
    assert provider.calls == 1 and info.value.attempts == 1


def test_exhausted_malformed_raises_with_history():
    provider = Scripted(*[LLMMalformedOutputError("bad json")] * 3)
    with pytest.raises(LLMCallFailedError) as info:
        _call(provider)
    assert info.value.attempts == 3 and len(info.value.errors) == 3


class FlakyMock(MockLLMProvider):
    """Every stage's first call fails once (alternating timeout / 429 / malformed), then succeeds."""

    def __init__(self):
        super().__init__()
        self.failed = set()
        self.failures = [LLMTimeoutError("timeout"), LLMRateLimitError("429", retry_after=0), "malformed"]

    def generate_structured(self, prompt, schema, *, system=None):
        if schema not in self.failed:
            self.failed.add(schema)
            failure = self.failures[len(self.failed) % 3]
            if failure == "malformed":
                return LLMResponse(data={"garbage": True}, raw_text="{garbage}")
            raise failure
        return super().generate_structured(prompt, schema, system=system)


def test_pipeline_recovers_from_transient_failures(db, api):
    project = api.create_project()
    criteria = [api.create_criterion(project["id"], n) for n in ("Accuracy", "Tone")]
    evaluation = api.create_evaluation(project["id"], criteria)
    provider = FlakyMock()
    run = evaluation_service.start_run(db, evaluation["id"], provider=provider)
    policy = RetryPolicy(max_attempts=3, rate_limit_max_attempts=3, base_delay_s=0, max_delay_s=0)
    evaluation_service.execute_run(run.id, provider, policy=policy, sleep=lambda s: None)
    db.expire_all()
    run = db.get(EvaluationRun, run.id)
    assert run.status == RunStatus.COMPLETED, run.raw_output.get("error")
    retried = [c for c in run.raw_output["calls"] if c["attempts"] > 1]
    assert len(retried) == 5  # one per stage schema
    assert all(len(c["retried_errors"]) == 1 for c in retried)


def test_evidence_service_dedup_edge_cases():
    from app.services.evidence_service import ground_evidence
    from app.utils.validation import EvidenceQuote

    text = "We apologize for the double charge. It will be refunded soon."
    # Wrapped/spaced duplicate of the same span, a fragment contained in it, and a bogus quote.
    result = ground_evidence(
        text,
        "A",
        [
            EvidenceQuote(quote="We apologize for the double charge.", supports="first"),
            EvidenceQuote(quote='"We  apologize   for the double charge."', supports="duplicate, wrapped+spaced"),
            EvidenceQuote(quote="apologize for the double", supports="contained fragment, dropped"),
            EvidenceQuote(quote="This text is not in the response at all.", supports="bogus"),
        ],
    )
    assert [item.quote for item in result] == ["We apologize for the double charge."]
    assert result[0].supports == "first"

    with pytest.raises(ValueError, match="no evidence quote"):
        ground_evidence(text, "A", [EvidenceQuote(quote="nonexistent text", supports="x")])


def test_retry_after_header_parsing():
    from app.providers.openai_compatible_provider import _parse_retry_after

    assert _parse_retry_after(None) is None
    assert _parse_retry_after("3") == 3.0
    assert _parse_retry_after("not-a-date-or-number") is None
    http_date = "Wed, 21 Oct 2099 07:28:00 GMT"
    parsed = _parse_retry_after(http_date)
    assert parsed is not None and parsed > 0


def test_evidence_matching_tolerates_markdown_and_typos():
    """Regression: gpt-oss quotes markdown responses with mangled formatting/typos;
    matching must tolerate it while still storing the true original substring."""
    from app.services.evidence_service import ground_evidence, locate_quote
    from app.utils.validation import EvidenceQuote

    response = (
        "- **Client Layer:** Native mobile apps (iOS & Android) and Web client for the restaurant portal.\n"
        "- **Order Service:** Manages cart, order lifecycle, and state machine.\n"
        "When an order status changes, the Order Service emits an event to a pub/sub topic."
    )
    # Markdown emphasis differs from the response's actual formatting.
    span = locate_quote(response, "*Client Layer:* Native mobile apps (iOS & Android)")
    assert span is not None and response[span[0]:span[1]].endswith("(iOS & Android)")
    # Tail-truncated quote (model cut "restaurant portal" mid-word).
    span = locate_quote(response, "Native mobile apps (iOS & Android) and Web client for the restaurant po")
    assert span is not None and "restaurant" in response[span[0]:span[1]]
    # Minor typo inside the quote -> best-sentence alignment returns the verbatim span.
    span = locate_quote(response, "the Order Service emits a event to a pub/sub topic")
    assert span is not None and "emits an event" in response[span[0]:span[1]]

    items = ground_evidence(
        response,
        "A",
        [EvidenceQuote(quote="*Client Layer:* Native mobile apps (iOS & Android)", supports="s")],
    )
    # Stored quote is the response's own text, expanded to include its ** markers.
    assert items[0].quote in response
    assert items[0].quote == "**Client Layer:** Native mobile apps (iOS & Android)"


def test_evidence_still_rejects_real_paraphrases():
    from app.services.evidence_service import ground_evidence
    from app.utils.validation import EvidenceQuote
    import pytest

    response = "Your refund will be processed soon. We added a store credit."
    with pytest.raises(ValueError):
        ground_evidence(
            response,
            "A",
            [EvidenceQuote(quote="The reply mentions numerous industry best practices.", supports="x")],
        )
