from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8082
    log_level: str = "info"
    environment: str = "dev"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5459/backtemplate"

    jwt_secret: str = "change-me-to-a-long-random-string-in-real-deployments"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30

    mail_host: str = ""
    mail_port: int = 587
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = "no-reply@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
