from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-20b"
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    outbound_webhook_url: str | None = None
    outbound_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    outbound_max_attempts: int = Field(default=3, ge=1, le=5)

    webhook_secret: str = "change-me"
    database_url: str = "sqlite:///./arcvault.db"
    output_dir: Path = Path("outputs")

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"groq", "ollama", "fake"}:
            raise ValueError("LLM_PROVIDER must be groq, ollama, or fake")
        return normalized

    @field_validator("webhook_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if not value:
            raise ValueError("WEBHOOK_SECRET cannot be empty")
        return value

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
        return Path(self.database_url.removeprefix(prefix))


@lru_cache
def get_settings() -> Settings:
    return Settings()
