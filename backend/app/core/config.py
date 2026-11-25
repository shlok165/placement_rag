"""Application settings, read from the environment."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    database_url: str = "postgresql+psycopg://placement:placement@db:5432/placement"
    raw_files_dir: Path = Path("/data/raw")
    embedding_cache_dir: Path = Path("/opt/models")
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    seed_demo: bool = False
    allowed_email_domains: str = "iitrpr.ac.in"
    dev_email_domains: str = ""
    cookie_secure: bool = False
    cors_origins: str = ""
    session_days: int = 7
    login_max_attempts: int = 8
    login_window_minutes: int = 15
    max_upload_mb: int = 5
    student_daily_turns: int = 30
    coordinator_daily_turns: int = 200
    alert_threshold: float = 0.62
    nightly_hour_utc: int = 19
    worker_poll_seconds: float = 1.0
    ingest_max_attempts: int = 3

    llm_mode: Literal["mock", "live"] = "mock"
    llm_base_url: str = Field(
        "https://gen.pollinations.ai",
        validation_alias=AliasChoices("LLM_BASE_URL", "POLLINATIONS_BASE_URL"),
    )
    llm_api_key: SecretStr = Field(
        SecretStr(""), validation_alias=AliasChoices("LLM_API_KEY", "POLLINATIONS_API_KEY")
    )
    llm_model: str = Field("", validation_alias=AliasChoices("LLM_MODEL", "POLLINATIONS_MODEL"))
    llm_judge_model: str = ""
    llm_timeout_s: float = 60.0
    llm_daily_call_cap: int = 300
    llm_total_call_cap: int = 2000
    llm_eval_call_cap: int = 150

    agent_max_iterations: int = 5
    agent_max_tokens_per_turn: int = 12000
    agent_max_output_tokens: int = 900
    agent_history_messages: int = 8

    @field_validator("llm_base_url")
    @classmethod
    def _strip_v1(cls, value: str) -> str:
        return value.rstrip("/").removesuffix("/v1")

    @property
    def email_domains(self) -> set[str]:
        raw = f"{self.allowed_email_domains},{self.dev_email_domains}"
        return {part.strip().lower() for part in raw.split(",") if part.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @property
    def is_live(self) -> bool:
        return self.llm_mode == "live" and bool(self.llm_api_key.get_secret_value())

    @property
    def judge_model(self) -> str:
        return self.llm_judge_model or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
