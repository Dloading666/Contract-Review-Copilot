from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenAI API (for Phase 2+)
    openai_api_key: str | None = None
    openai_model: str = "glm-5"
    openai_base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    minimax_model: str = "MiniMax-M2.5"
    qwen_model: str = "qwen-plus"
    kimi_model: str = "kimi-k2.5"
    primary_llm_model_key: str = "gemma4"
    gemma4_model: str = "gemma3"
    gemma4_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    jwt_secret: str | None = None
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # DuckDuckGo Search (free, no API key needed)
    # PostgreSQL / pgvector (for Phase 2+)
    database_url: str | None = None
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl_seconds: int = 7200
    redis_search_ttl_seconds: int = 1800
    redis_llm_ttl_seconds: int = 3600

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
