from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    jwt_secret: str
    jwt_lifetime_seconds: int = 60 * 15
    refresh_lifetime_seconds: int = 60 * 60 * 24 * 30
    refresh_cookie_secure: bool = False
    brapi_token: str | None = None
    timezone: str = "America/Sao_Paulo"


@lru_cache
def get_settings() -> Settings:
    return Settings()
