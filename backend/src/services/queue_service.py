"""
Background task queue service with Redis storage and in-memory fallback.

Tasks are stored as JSON blobs and can optionally carry SSE-style event lists.
The default task type is ``review`` so existing review queue flows remain
compatible while other background jobs (such as OCR ingestion) can reuse the
same lifecycle and retry metadata.
"""
from __future__ import annotations

import json
import time
import uuid
from threading import Lock
from typing import Any, Optional

from ..cache.redis_cache import get_redis_client

TASK_TTL = 7200
EVENTS_TTL = 7200
DONE_SENTINEL = "_done"
TERMINAL_STATUSES = {"completed", "failed", "paused", "dead_letter", "cancelled"}

_memory_lock = Lock()
_memory_tasks: dict[tuple[str, str], dict[str, Any]] = {}
_memory_events: dict[tuple[str, str], list[dict[str, Any]]] = {}
_memory_pending_counts: dict[str, int] = {}


def _task_key(task_id: str, task_type: str = "review") -> str:
    return f"queue:{task_type}:task:{task_id}"


def _events_key(task_id: str, task_type: str = "review") -> str:
    return f"queue:{task_type}:events:{task_id}"


def _pending_counter_key(task_type: str = "review") -> str:
    return f"queue:{task_type}:pending_count"


def _task_storage_key(task_id: str, task_type: str) -> tuple[str, str]:
    return task_type, task_id


def create_task(
    user_id: str,
    contract_text: str = "",
    session_id: str = "",
    filename: str = "",
    review_mode: str = "deep",
    *,
    task_type: str = "review",
    max_retries: int = 0,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    task_id = uuid.uuid4().hex
    now = time.time()
    task_data: dict[str, Any] = {
        "task_id": task_id,
        "task_type": task_type,
        "session_id": session_id,
        "user_id": user_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "filename": filename,
        "review_mode": review_mode,
        "contract_text_len": len(contract_text),
        "retry_count": 0,
        "max_retries": max(0, int(max_retries or 0)),
        "last_error": None,
        "error_code": None,
        "dead_letter": False,
    }
    if metadata:
        task_data.update(metadata)

    client = get_redis_client()
    if client:
        try:
            client.setex(_task_key(task_id, task_type), TASK_TTL, json.dumps(task_data, ensure_ascii=False))
            counter_key = _pending_counter_key(task_type)
            client.incr(counter_key)
            client.expire(counter_key, TASK_TTL)
            return task_id
        except Exception as exc:
            print(f"[Queue] Redis create task fallback for {task_type}:{task_id}: {exc}", flush=True)

    with _memory_lock:
        _memory_tasks[_task_storage_key(task_id, task_type)] = task_data
        _memory_pending_counts[task_type] = _memory_pending_counts.get(task_type, 0) + 1
    return task_id


def get_task(task_id: str, *, task_type: str = "review") -> Optional[dict[str, Any]]:
    client = get_redis_client()
    if client:
        try:
            raw = client.get(_task_key(task_id, task_type))
            return json.loads(raw) if raw else None
        except Exception as exc:
            print(f"[Queue] Redis get task fallback for {task_type}:{task_id}: {exc}", flush=True)

    with _memory_lock:
        task = _memory_tasks.get(_task_storage_key(task_id, task_type))
        return dict(task) if task else None


def update_task_status(task_id: str, status: str, *, task_type: str = "review", **extra: Any) -> None:
    now = time.time()
    client = get_redis_client()
    if client:
        try:
            raw = client.get(_task_key(task_id, task_type))
            if raw:
                task_data: dict[str, Any] = json.loads(raw)
                prev_status = task_data.get("status", "")
                task_data["status"] = status
                task_data["updated_at"] = now
                task_data.update(extra)
                if status in TERMINAL_STATUSES and "finished_at" not in task_data:
                    task_data["finished_at"] = now
                client.setex(
                    _task_key(task_id, task_type),
                    TASK_TTL,
                    json.dumps(task_data, ensure_ascii=False),
                )
                if prev_status == "pending" and status != "pending":
                    try:
                        client.decr(_pending_counter_key(task_type))
                    except Exception:
                        pass
                return
        except Exception as exc:
            print(f"[Queue] Redis update task fallback for {task_type}:{task_id}: {exc}", flush=True)

    with _memory_lock:
        key = _task_storage_key(task_id, task_type)
        task_data = dict(_memory_tasks.get(key) or {})
        if not task_data:
            return
        prev_status = task_data.get("status", "")
        task_data["status"] = status
        task_data["updated_at"] = now
        task_data.update(extra)
        if status in TERMINAL_STATUSES and "finished_at" not in task_data:
            task_data["finished_at"] = now
        _memory_tasks[key] = task_data
        if prev_status == "pending" and status != "pending":
            _memory_pending_counts[task_type] = max(0, _memory_pending_counts.get(task_type, 0) - 1)


def get_pending_count(*, task_type: str = "review") -> int:
    client = get_redis_client()
    if client:
        try:
            raw = client.get(_pending_counter_key(task_type))
            return max(0, int(raw or 0))
        except Exception as exc:
            print(f"[Queue] Redis get pending fallback for {task_type}: {exc}", flush=True)

    with _memory_lock:
        return max(0, int(_memory_pending_counts.get(task_type, 0)))


def push_event(task_id: str, event_type: str, data: dict, *, task_type: str = "review") -> None:
    payload = {"event": event_type, "data": data}
    client = get_redis_client()
    if client:
        try:
            key = _events_key(task_id, task_type)
            client.rpush(key, json.dumps(payload, ensure_ascii=False))
            client.expire(key, EVENTS_TTL)
            return
        except Exception as exc:
            print(f"[Queue] Redis push event fallback for {task_type}:{task_id}: {exc}", flush=True)

    with _memory_lock:
        key = _task_storage_key(task_id, task_type)
        events = list(_memory_events.get(key, []))
        events.append(payload)
        _memory_events[key] = events


def get_events(task_id: str, offset: int = 0, *, task_type: str = "review") -> list[dict[str, Any]]:
    client = get_redis_client()
    if client:
        try:
            raw_events = client.lrange(_events_key(task_id, task_type), offset, -1)
            return [json.loads(item) for item in raw_events]
        except Exception as exc:
            print(f"[Queue] Redis get events fallback for {task_type}:{task_id}: {exc}", flush=True)

    with _memory_lock:
        return list(_memory_events.get(_task_storage_key(task_id, task_type), []))[offset:]
