"""Runtime settings, read from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # FalkorDB
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_username: str | None = None
    falkordb_password: str | None = None
    pagersage_graph: str = "pagersage"

    # Claude: per-agent models, see build-plan.md section 2
    anthropic_api_key: str | None = None
    model_triage: str = "claude-haiku-5-5"
    model_investigator: str = "claude-sonnet-5-5"
    model_historian: str = "claude-sonnet-5-5"
    model_responder: str = "claude-haiku-5-5"
    model_scribe: str = "claude-sonnet-5-5"
    model_brain: str = "claude-sonnet-5-5"
    # Run the agents when an alert opens an incident (A03). Tests turn this off.
    agents_enabled: bool = True

    # Actions
    discord_webhook_url: str | None = None
    github_token: str | None = None
    github_issues_repo: str | None = None

    # Web
    cors_origins: str = "http://localhost:3100"

    @field_validator(
        "falkordb_username",
        "falkordb_password",
        "anthropic_api_key",
        "discord_webhook_url",
        "github_token",
        "github_issues_repo",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        # `KEY=` in .env means "not set", not "empty string".
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
