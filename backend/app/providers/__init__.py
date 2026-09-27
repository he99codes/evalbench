"""Provider factory: the only place that maps LLM_PROVIDER / LLM_MODEL to an implementation."""

from app.core.config import Settings, get_settings
from app.providers.base import LLMProvider, RetryPolicy


class ProviderConfigError(RuntimeError):
    """The configured provider cannot be constructed (e.g. missing API key)."""


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "mock":
        from app.providers.mock_provider import MockLLMProvider

        return MockLLMProvider(model=settings.llm_model or "mock")

    if settings.llm_provider == "openai_compatible":
        from app.providers.openai_compatible_provider import OpenAICompatibleProvider

        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
            raise ProviderConfigError("LLM_PROVIDER=openai_compatible requires LLM_API_KEY")
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model or "openai/gpt-oss-20b",
            timeout_s=settings.llm_timeout_seconds,
            structured_mode=settings.llm_structured_mode,
            temperature=settings.llm_temperature,
            max_completion_tokens=settings.llm_max_completion_tokens,
            reasoning_effort=settings.llm_reasoning_effort,
        )

    raise ProviderConfigError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}")


def get_retry_policy(settings: Settings | None = None) -> RetryPolicy:
    settings = settings or get_settings()
    return RetryPolicy(
        max_attempts=settings.llm_max_attempts,
        rate_limit_max_attempts=settings.llm_rate_limit_max_attempts,
        base_delay_s=settings.llm_retry_base_delay_seconds,
        max_delay_s=settings.llm_retry_max_delay_seconds,
    )
