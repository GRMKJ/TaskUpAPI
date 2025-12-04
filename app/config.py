import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration pulled from environment variables or .env files."""

    database_url: str = "mysql+pymysql://root:root@localhost:3306/taskup"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 60
    refresh_token_expires_days: int = 30
    password_salt_rounds: int = 12
    google_client_ids: list[str] = Field(default_factory=list)
    enable_reminder_worker: bool = True
    reminder_poll_interval_seconds: int = 60
    reminder_batch_size: int = 50
    fcm_server_key: str | None = None
    firebase_project_id: str | None = None
    firebase_credentials_file: str | None = None

    @field_validator("google_client_ids", mode="before")
    @classmethod
    def _split_google_ids(cls, value):
        if isinstance(value, str):
            return [segment.strip() for segment in value.split(",") if segment.strip()]
        return value

    @field_validator("firebase_credentials_file", mode="before")
    @classmethod
    def _default_credentials(cls, value):
        if value:
            return value
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    @field_validator("firebase_project_id", mode="before")
    @classmethod
    def _default_project(cls, value):
        if value:
            return value
        return os.getenv("FIREBASE_PROJECT_ID")

    model_config = SettingsConfigDict(
        env_prefix="TASKUP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
