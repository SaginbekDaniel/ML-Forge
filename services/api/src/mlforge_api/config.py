from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Server configuration. Secrets come from the environment only, never the DB."""

    model_config = SettingsConfigDict(env_prefix="MLFORGE_", env_file=(REPO_ROOT / ".env"), extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    database_url: str | None = None
    content_dir: Path = REPO_ROOT / "content" / "curriculum"
    runner_image: str | None = None
    embedded_worker: bool = True
    worker_threads: int = 2
    sandbox_timeout_s: float = 5.0
    sandbox_memory_mb: int = 256
    log_level: str = "INFO"

    # Optional AI mentor (M2). Absent key => AI features report "unavailable".
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "MLFORGE_ANTHROPIC_API_KEY")
    )
    ai_model: str = "claude-sonnet-5-5"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'mlforge.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
