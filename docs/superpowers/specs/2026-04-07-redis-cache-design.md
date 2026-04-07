# Redis Cache Integration Design

## Goal

Introduce Redis as a soft-dependency cache layer for the backend so the review flow stays available even if Redis is down.

## Scope

- Add a `redis` service to Docker Compose.
- Add backend Redis configuration and dependency.
- Cache paused review sessions used by `/api/review` and `/api/review/confirm/{session_id}`.
- Cache DuckDuckGo and pgvector retrieval results.
- Cache LLM chat completion text returned by the shared completion helper.
- Keep an in-process fallback for paused sessions and skip cache reads/writes when Redis is unavailable.

## Architecture

- New module: `backend/src/cache/redis_cache.py`
  - Owns Redis client creation.
  - Provides JSON get/set/delete helpers.
  - Swallows Redis connection/runtime failures and returns cache misses.
- `main.py`
  - Replaces direct reliance on the in-memory `paused_sessions` dict with a Redis-first session store.
  - Keeps `paused_sessions` as a local fallback for degraded mode.
- `search/duckduckgo.py`
  - Caches web search result lists by query parameters.
- `vectorstore/store.py`
  - Caches similarity retrieval results by query parameters.
- `agents/entity_extraction.py`
  - Caches chat completion output text by model + messages + selected generation parameters.

## Cache Policy

- Session cache TTL: 2 hours
- Search cache TTL: 30 minutes
- LLM cache TTL: 1 hour
- Key prefixes:
  - `contract-review:session:*`
  - `contract-review:search:*`
  - `contract-review:llm:*`

## Failure Handling

- If Redis is unreachable, the backend continues normally.
- Session pause/resume falls back to in-memory storage for the current process.
- Search and LLM cache calls become no-ops and the backend computes fresh results.

## Testing

- Add tests for Redis-backed paused session persistence and fallback behavior.
- Add tests for search cache and LLM cache helpers with mocked cache clients.
- Keep tests isolated from a real Redis server by monkeypatching the cache module.
