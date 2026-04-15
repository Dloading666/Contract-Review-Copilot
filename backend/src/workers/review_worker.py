"""
Review Worker — runs the review pipeline as a background asyncio task,
pushing SSE events into the Redis queue so the stream endpoint can relay
them to the connected client.

Usage (called from an async FastAPI handler):
    asyncio.create_task(
        run_queued_review(
            task_id, contract_text, session_id, user_id,
            on_breakpoint=store_paused_session,
        )
    )
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Callable

from ..graph.review_graph import run_review_stream
from ..services.queue_service import DONE_SENTINEL, push_event, update_task_status


async def run_queued_review(
    task_id: str,
    contract_text: str,
    session_id: str,
    user_id: str,
    on_breakpoint: Callable[[str, dict], None],
) -> None:
    """
    Execute the full review pipeline for a queued task.

    Emits SSE events into the Redis event list as they arrive so that
    the ``/api/review/queue/{task_id}/stream`` endpoint can relay them to
    the client in real time.

    When a breakpoint is reached the callback ``on_breakpoint(session_id,
    session_data)`` is invoked (synchronously) to persist the paused state,
    task status is set to "paused", and the worker exits.  The client then
    calls ``POST /api/review/confirm/{session_id}`` as usual to resume
    Phase 2 aggregation.
    """
    update_task_status(task_id, "running")
    print(f"[Worker] Starting task {task_id} (session {session_id})", flush=True)

    try:
        async for event in run_review_stream(
            contract_text=contract_text,
            session_id=session_id,
        ):
            event_type = event.get("event", "message")
            event_data = event.get("data", event)

            push_event(task_id, event_type, event_data)

            if event_type == "breakpoint":
                # Persist paused state so /api/review/confirm can resume
                on_breakpoint(
                    session_id,
                    {
                        "owner": user_id,
                        "contract_text": contract_text,
                        "issues": event_data.get("issues", []),
                    },
                )
                update_task_status(task_id, "paused", session_id=session_id)
                push_event(task_id, DONE_SENTINEL, {})
                print(f"[Worker] Task {task_id} paused at breakpoint", flush=True)
                return

        update_task_status(task_id, "completed")
        push_event(task_id, DONE_SENTINEL, {})
        print(f"[Worker] Task {task_id} completed", flush=True)

    except asyncio.CancelledError:
        push_event(task_id, "error", {"message": "任务被取消"})
        push_event(task_id, DONE_SENTINEL, {})
        update_task_status(task_id, "failed", error="cancelled")
        raise

    except Exception as exc:
        error_msg = str(exc)
        print(f"[Worker] Task {task_id} failed: {error_msg}", flush=True)
        traceback.print_exc()
        push_event(task_id, "error", {"message": error_msg})
        push_event(task_id, DONE_SENTINEL, {})
        update_task_status(task_id, "failed", error=error_msg)
