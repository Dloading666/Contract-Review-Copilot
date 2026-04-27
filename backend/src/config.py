from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Contract Review Copilot"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenRouter is optional and currently not used for OCR.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # DeepSeek backs review/report/chat text generation.
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.deepseek.com"

    # SiliconFlow powers OCR.
    ocr_fallback_api_key: str | None = None
    ocr_fallback_base_url: str = "https://api.siliconflow.cn/v1"

    primary_review_model: str = "deepseek-v4-flash"
    fallback_review_model: str | None = None
    primary_chat_model: str = "deepseek-v4-flash"
    fallback_chat_model: str | None = None
    primary_ocr_model: str = "PaddlePaddle/PaddleOCR-VL-1.5"
    fallback_ocr_model: str | None = None
    ocr_max_upload_file_bytes: int = 20 * 1024 * 1024
    ocr_max_batch_images: int = 12
    ocr_max_pdf_pages: int = 20
    ocr_max_image_pixels: int = 20_000_000
    review_queue_max_retries: int = 2
    ocr_queue_max_retries: int = 2
    queue_retry_backoff_seconds: float = 1.5

    review_temperature: float = 1.0
    chat_temperature: float = 1.0
    report_temperature: float = 1.0

    review_initial_deadline_seconds: float = 38.0
    review_entity_timeout_seconds: float = 8.0
    review_routing_timeout_seconds: float = 4.0
    review_model_timeout_seconds: float = 20.0
    review_report_timeout_seconds: float = 35.0
    review_heartbeat_interval_seconds: float = 8.0

    interactive_chat_timeout_seconds: float = 25.0
    interactive_chat_max_tokens: int = 640
    chat_query_rewrite_count: int = 3
    chat_pgvector_top_k: int = 4
    chat_pgvector_min_similarity: float = 0.3
    chat_pgvector_min_hits_for_skip_search: int = 3
    chat_pgvector_min_top_score_for_skip_search: float = 0.72
    chat_targeted_search_top_k: int = 4
    chat_targeted_search_min_hits_for_skip_web: int = 2
    chat_web_search_top_k: int = 4
    chat_max_evidence_items: int = 6
    chat_stream_model: str = "deepseek-v4-flash"
    chat_enable_targeted_search: bool = True
    chat_enable_web_search: bool = True

    jwt_secret: str | None = None
    jwt_secret_file: str | None = None
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    allow_dev_code_response: bool = False
    captcha_enabled: bool = False
    captcha_provider: str = "turnstile"
    captcha_secret_key: str | None = None
    captcha_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    database_url: str | None = None
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl_seconds: int = 7200
    redis_search_ttl_seconds: int = 1800
    redis_llm_ttl_seconds: int = 3600
    redis_auth_code_ttl_seconds: int = 300

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    from_email: str | None = None

    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
