from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenAI API (for Phase 2+)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # DuckDuckGo Search (free, no API key needed)
    # PostgreSQL / pgvector (for Phase 2+)
    database_url: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
