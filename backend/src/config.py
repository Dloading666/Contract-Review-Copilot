from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # SiliconFlow API（OpenAI 兼容接口）
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.minimax.chat/v1"

    # 模型配置
    review_model: str = "minimax-m2.7"                   # 推理/审查/报告/问答
    ocr_model: str = "minimax-vl-01"                    # 图片 OCR 识别

    jwt_secret: str | None = None
    jwt_secret_file: str | None = None
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    allow_dev_code_response: bool = False

    database_url: str | None = None
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl_seconds: int = 7200
    redis_search_ttl_seconds: int = 1800
    redis_llm_ttl_seconds: int = 3600
    redis_auth_code_ttl_seconds: int = 300

    # SMTP / Email 验证码
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    from_email: str | None = None

    # GitHub OAuth
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
