from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: SecretStr = SecretStr("")
    openai_text_model: str = Field(default="gpt-6-luna", min_length=1)
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    openai_max_retries: int = Field(default=2, ge=0, le=3)
    openai_max_output_tokens: int = Field(default=1000, ge=16, le=2000)
    relay_agent_token: SecretStr = SecretStr("")
    relay_api_url: str = "https://api.relayapp.im"
    relay_webhook_secret: SecretStr = SecretStr("")
    relay_timeout_seconds: float = Field(default=10, gt=0, le=30)
    inbox_path: Path = Path(".runtime/inbox.sqlite3")
    worker_poll_seconds: float = Field(default=0.25, ge=0.01, le=5)
    worker_max_attempts: int = Field(default=3, ge=1, le=5)
    log_level: str = "INFO"

    @field_validator("relay_api_url")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("RELAY_API_URL must be an HTTPS origin without /v1")
        return value.rstrip("/")

    def missing_credentials(self) -> list[str]:
        return [
            name.upper()
            for name in ("openai_api_key", "relay_agent_token", "relay_webhook_secret")
            if not getattr(self, name).get_secret_value().strip()
        ]
