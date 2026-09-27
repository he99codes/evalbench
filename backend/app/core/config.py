"""Application settings, loaded from environment variables / .env only."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Look in backend/.env first, then the repo-root .env. Missing files are ignored.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://evalbench:evalbench@localhost:5432/evalbench"

    # --- LLM provider (see app/providers/__init__.py) -------------------------
    # mock: deterministic, offline. openai_compatible: any OpenAI-compatible
    # chat-completions API (Groq, NVIDIA NIM, OpenAI, ...).
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    # Default per provider when unset: "mock" / "openai/gpt-oss-20b".
    llm_model: str | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: SecretStr | None = None
    # json_schema = strict structured outputs (Groq gpt-oss). json_object = JSON mode fallback.
    llm_structured_mode: Literal["json_schema", "json_object"] = "json_schema"
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    # Completion budget per call. Reasoning models burn hidden thinking tokens inside it.
    llm_max_completion_tokens: int = Field(default=8192, ge=256)
    # Optional pass-through for providers that support it (Groq gpt-oss: low|medium|high).
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = None
    llm_max_attempts: int = Field(default=3, ge=1, le=10)
    llm_rate_limit_max_attempts: int = Field(default=6, ge=1, le=20)
    llm_retry_base_delay_seconds: float = Field(default=1.0, ge=0)
    llm_retry_max_delay_seconds: float = Field(default=30.0, ge=0)

    # Comma-separated list, e.g. "http://localhost:5173,http://127.0.0.1:5173"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        return "mock" if self.llm_provider == "mock" else "openai/gpt-oss-20b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
