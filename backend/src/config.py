from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # SiliconFlow API（OpenAI 兼容接口）
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.siliconflow.cn/v1"

    # 模型配置
    review_model: str = "Qwen/Qwen3.5-4B"                   # 推理/审查/报告/问答
    ocr_model: str = "PaddlePaddle/PaddleOCR-VL-1.5"        # 图片 OCR 识别

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

    aliyun_sms_access_key_id: str | None = None
    aliyun_sms_access_key_secret: str | None = None
    aliyun_sms_sign_name: str | None = None
    aliyun_sms_template_code: str | None = None
    aliyun_sms_region_id: str = "cn-hangzhou"
    aliyun_sms_endpoint: str = "https://dysmsapi.aliyuncs.com"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
