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
    primary_llm_model_key: str = "kimi"
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
    redis_auth_code_ttl_seconds: int = 300

    # Commercialization settings
    free_review_count: int = 2
    review_price_fen: int = 300
    review_question_quota: int = 15
    extra_question_price_fen: int = 8
    recharge_min_amount_fen: int = 300
    recharge_quick_amounts: str = "300,990,1990"

    # Aliyun SMS
    aliyun_sms_access_key_id: str | None = None
    aliyun_sms_access_key_secret: str | None = None
    aliyun_sms_sign_name: str | None = None
    aliyun_sms_template_code: str | None = None
    aliyun_sms_region_id: str = "cn-hangzhou"
    aliyun_sms_endpoint: str = "https://dysmsapi.aliyuncs.com"

    # WeChat Pay Native
    wechat_pay_appid: str | None = None
    wechat_pay_mchid: str | None = None
    wechat_pay_serial_no: str | None = None
    wechat_pay_private_key_path: str | None = None
    wechat_pay_private_key_pem: str | None = None
    wechat_pay_platform_serial_no: str | None = None
    wechat_pay_platform_cert_path: str | None = None
    wechat_pay_platform_cert_pem: str | None = None
    wechat_pay_api_v3_key: str | None = None
    wechat_pay_notify_url: str | None = None
    wechat_pay_api_base_url: str = "https://api.mch.weixin.qq.com"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
