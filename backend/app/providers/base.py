"""LLMProvider interface, typed errors and the structured-call retry wrapper.

Business logic depends only on `LLMProvider` and `call_structured`; no vendor SDK
or HTTP detail leaks past this module's implementations.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base class for provider failures."""


class LLMTransientError(LLMError):
    """Retryable: network errors, timeouts, 5xx, rate limits."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMTimeoutError(LLMTransientError):
    pass


class LLMRateLimitError(LLMTransientError):
    """HTTP 429. Retried with a larger budget, honouring Retry-After."""


class LLMMalformedOutputError(LLMError):
    """Retryable: output was not valid JSON or did not match the stage schema."""


class LLMPermanentError(LLMError):
    """Not retryable: auth failures, bad requests, unknown model."""


class LLMCallFailedError(LLMError):
    """Raised after the retry budget is exhausted (or on a permanent error)."""

    def __init__(self, message: str, *, attempts: int, errors: list[str]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.errors = errors


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    data: dict[str, Any]
    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_structured(
        self, prompt: str, schema: type[BaseModel], *, system: str | None = None
    ) -> LLMResponse:
        """Return JSON output intended to match `schema`. Validation happens in call_structured."""
        ...


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    rate_limit_max_attempts: int = 6
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0


@dataclass
class StructuredCallResult(Generic[T, R]):
    output: T
    processed: R
    response: LLMResponse
    attempts: int
    errors: list[str] = field(default_factory=list)


def call_structured(
    provider: LLMProvider,
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    postprocess: Callable[[T], R] | None = None,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> StructuredCallResult[T, R]:
    """Call the provider, validate against `schema`, optionally post-process, retrying on
    transient errors, rate limits and malformed output. Never returns unvalidated data.

    `postprocess` may raise ValueError to reject semantically invalid output (e.g. evidence
    quotes that are not in the response); that counts as malformed output and is retried.
    """
    policy = policy or RetryPolicy()
    errors: list[str] = []
    attempts = 0
    while True:
        attempts += 1
        try:
            response = provider.generate_structured(prompt, schema, system=system)
            if not isinstance(response.data, dict):
                raise LLMMalformedOutputError("provider returned a non-object JSON value")
            try:
                output = schema.model_validate(response.data)
            except ValidationError as exc:
                raise LLMMalformedOutputError(
                    f"output does not match {schema.__name__}: {exc.error_count()} error(s): "
                    f"{exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"
                ) from exc
            try:
                processed = postprocess(output) if postprocess else output
            except ValueError as exc:
                raise LLMMalformedOutputError(f"output rejected: {exc}") from exc
            return StructuredCallResult(output, processed, response, attempts, errors)  # type: ignore[arg-type]
        except LLMPermanentError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            raise LLMCallFailedError(str(exc), attempts=attempts, errors=errors) from exc
        except (LLMTransientError, LLMMalformedOutputError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            limit = (
                policy.rate_limit_max_attempts
                if isinstance(exc, LLMRateLimitError)
                else policy.max_attempts
            )
            if attempts >= limit:
                raise LLMCallFailedError(
                    f"{schema.__name__} failed after {attempts} attempt(s): {exc}",
                    attempts=attempts,
                    errors=errors,
                ) from exc
            retry_after = getattr(exc, "retry_after", None)
            delay = (
                retry_after
                if retry_after is not None
                else policy.base_delay_s * (2 ** (attempts - 1))
            )
            delay = min(max(delay, 0.0), policy.max_delay_s)
            logger.warning("LLM call attempt %d failed (%s); retrying in %.1fs", attempts, exc, delay)
            sleep(delay)
