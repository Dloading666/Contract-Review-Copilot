from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenRouter API（主力模型）
    openrouter_api_key: str | None = "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"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # SiliconFlow API（备用模型）
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.siliconflow.cn/v1"

    # 主力模型（OpenRouter）— Gemma 4 26B A4B MoE 速度最快
    primary_review_model: str = "Qwen/Qwen3.5-4B"      # 推理/审查/报告/问答（SiliconFlow）
    fallback_review_model: str = "deepseek-ai/DeepSeek-V2.5"  # 备用（SiliconFlow）

    primary_ocr_model: str = "nvidia/nemotron-nano-12b-v2-vl:free"    # 图片 OCR 识别
    fallback_ocr_model: str = "PaddlePaddle/PaddleOCR-VL-1.5"          # 图片 OCR（SiliconFlow）

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
