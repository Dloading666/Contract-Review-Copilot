import json
from functools import lru_cache
from hashlib import sha256
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from ..config import get_settings

_redis_client: Redis | None = None


def _serialize_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def get_ttl_seconds(kind: str) -> int:
    settings = get_settings()
    ttl_map = {
        "session": settings.redis_session_ttl_seconds,
        "search": settings.redis_search_ttl_seconds,
        "llm": settings.redis_llm_ttl_seconds,
    }
    return ttl_map.get(kind, settings.redis_search_ttl_seconds)


def build_cache_key(kind: str, payload: Any) -> str:
    digest = sha256(_serialize_payload(payload).encode("utf-8")).hexdigest()
    return f"contract-review:{kind}:{digest}"


@lru_cache(maxsize=1)
def _is_cache_enabled() -> bool:
    settings = get_settings()
    return settings.redis_enabled and bool(settings.redis_url)


def get_redis_client() -> Redis | None:
    global _redis_client
    if not _is_cache_enabled():
        return None

    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
            health_check_interval=30,
        )

    return _redis_client


def get_json(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None

    try:
        value = client.get(key)
    except RedisError as error:
        print(f"[Redis] GET failed for {key}: {error}", flush=True)
        return None

    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def set_json(key: str, value: Any, ttl_seconds: int) -> bool:
    client = get_redis_client()
    if client is None:
        return False

    try:
        client.setex(key, ttl_seconds, _serialize_payload(value))
        return True
    except RedisError as error:
        print(f"[Redis] SET failed for {key}: {error}", flush=True)
        return False


def delete_json(key: str) -> bool:
    client = get_redis_client()
    if client is None:
        return False

    try:
        client.delete(key)
        return True
    except RedisError as error:
        print(f"[Redis] DELETE failed for {key}: {error}", flush=True)
        return False


def close_redis_client() -> None:
    global _redis_client
    if _redis_client is None:
        return

    try:
        _redis_client.close()
    except RedisError:
        pass
    finally:
        _redis_client = None
