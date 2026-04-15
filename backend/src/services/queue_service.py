"""
Review Queue Service — Redis-backed task queue for contract reviews.

Tasks are stored as Redis Hash keys; SSE events are stored as Redis Lists.
This allows the background worker to push events while the stream endpoint
polls and relays them to the connected client in real time.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from ..cache.redis_cache import get_redis_client

# TTL for task metadata and event lists (2 hours)
TASK_TTL = 7200
EVENTS_TTL = 7200

# Sentinel event type that signals end-of-stream to the SSE reader
DONE_SENTINEL = "_done"

_TASK_PREFIX = "review:task:"
_EVENTS_PREFIX = "review:events:"
_PENDING_COUNTER = "review:queue:pending_count"


def _task_key(task_id: str) -> str:
    return f"{_TASK_PREFIX}{task_id}"


def _events_key(task_id: str) -> str:
    return f"{_EVENTS_PREFIX}{task_id}"


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------

def create_task(
    user_id: str,
    contract_text: str,
    session_id: str,
    filename: str = "",
) -> str:
    """
    Register a new review task and return its task_id.

    The task starts in "pending" status; the background worker will
    transition it to "running" → "paused" | "completed" | "failed".
    """
    task_id = uuid.uuid4().hex
    task_data: dict[str, Any] = {
        "task_id": task_id,
        "session_id": session_id,
        "user_id": user_id,
        "status": "pending",
        "created_at": time.time(),
        "filename": filename,
        "contract_text_len": len(contract_text),
    }

    client = get_redis_client()
    if client:
        try:
            client.setex(
                _task_key(task_id),
                TASK_TTL,
                json.dumps(task_data, ensure_ascii=False),
            )
            client.incr(_PENDING_COUNTER)
            client.expire(_PENDING_COUNTER, TASK_TTL)
        except Exception as exc:
            print(f"[Queue] Failed to create task {task_id}: {exc}", flush=True)

    return task_id


def get_task(task_id: str) -> Optional[dict]:
    """Return task metadata dict, or None if not found."""
    client = get_redis_client()
    if not client:
        return None
    try:
        raw = client.get(_task_key(task_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def update_task_status(task_id: str, status: str, **extra: Any) -> None:
    """Atomically update task status and any extra fields."""
    client = get_redis_client()
    if not client:
        return
    try:
        raw = client.get(_task_key(task_id))
        if not raw:
            return
        task_data: dict = json.loads(raw)
        prev_status = task_data.get("status", "")
        task_data["status"] = status
        task_data.update(extra)

        client.setex(
            _task_key(task_id),
            TASK_TTL,
            json.dumps(task_data, ensure_ascii=False),
        )

        # Keep the pending counter accurate
        if prev_status == "pending" and status in ("running", "completed", "failed", "paused"):
            try:
                client.decr(_PENDING_COUNTER)
            except Exception:
                pass
    except Exception as exc:
        print(f"[Queue] Failed to update task {task_id}: {exc}", flush=True)


def get_pending_count() -> int:
    """Return the approximate number of pending/running tasks."""
    client = get_redis_client()
    if not client:
        return 0
    try:
        raw = client.get(_PENDING_COUNTER)
        return max(0, int(raw or 0))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

def push_event(task_id: str, event_type: str, data: dict) -> None:
    """
    Append an SSE-style event to the task's event list.

    The list is read sequentially by the stream endpoint.
    Use DONE_SENTINEL as event_type to signal end-of-stream.
    """
    client = get_redis_client()
    if not client:
        return
    try:
        payload = json.dumps(
            {"event": event_type, "data": data},
            ensure_ascii=False,
        )
        key = _events_key(task_id)
        client.rpush(key, payload)
        client.expire(key, EVENTS_TTL)
    except Exception as exc:
        print(f"[Queue] Failed to push event for task {task_id}: {exc}", flush=True)


def get_events(task_id: str, offset: int = 0) -> list[dict]:
    """
    Return events from ``offset`` onwards (non-blocking).

    Callers should track their offset and call this repeatedly.
    """
    client = get_redis_client()
    if not client:
        return []
    try:
        raw_events = client.lrange(_events_key(task_id), offset, -1)
        return [json.loads(e) for e in raw_events]
    except Exception:
        return []
