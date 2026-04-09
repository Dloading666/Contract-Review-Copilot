from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .cache.redis_cache import get_redis_client


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    subject: str
    limit: int
    window_seconds: int
    detail: str


def get_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client_host = getattr(request.client, "host", None)
    return client_host or "unknown"


def _build_rate_limit_key(scope: str, subject: str) -> str:
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return f"contract-review:rate-limit:{scope}:{digest}"


def enforce_rate_limit(rule: RateLimitRule) -> None:
    if not rule.subject:
        return

    client = get_redis_client()
    if client is None:
        return

    key = _build_rate_limit_key(rule.scope, rule.subject)
    try:
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, rule.window_seconds)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[RateLimit] Redis failure for {rule.scope}: {exc}", flush=True)
        return

    if count > rule.limit:
        raise HTTPException(status_code=429, detail=rule.detail)


def enforce_rate_limits(rules: list[RateLimitRule]) -> None:
    for rule in rules:
        enforce_rate_limit(rule)
