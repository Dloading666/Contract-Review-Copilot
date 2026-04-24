"""
Review worker with retry and dead-letter support.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from typing import Callable

from ..graph.review_graph import run_review_stream
from ..services import queue_service

TASK_CANCELLED_MESSAGE = "审查任务已取消。"
TASK_FAILURE_MESSAGE = "审查任务处理失败，请稍后重试。"
TASK_RETRYING_MESSAGE = "审查任务异常，正在准备自动重试。"


async def run_queued_review(
    task_id: str,
    contract_text: str,
    session_id: str,
    user_id: str,
    review_mode: str,
    on_breakpoint: Callable[[str, dict], None],
    *,
    max_retries: int = 0,
    retry_backoff_seconds: float = 1.5,
) -> None:
    attempt = 0

    while True:
        attempt += 1
        queue_service.update_task_status(
            task_id,
            "running",
            attempt=attempt,
            retry_count=attempt - 1,
            task_type="review",
            next_retry_at=None,
            last_error=None,
            error_code=None,
            dead_letter=False,
        )
        print(f"[Worker] Starting task {task_id} attempt {attempt} (session {session_id})", flush=True)

        try:
            async for event in run_review_stream(
                contract_text=contract_text,
                session_id=session_id,
                review_mode=review_mode,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)

                queue_service.push_event(task_id, event_type, event_data, task_type="review")

                if event_type == "breakpoint":
                    on_breakpoint(
                        session_id,
                        {
                            "owner": user_id,
                            "contract_text": contract_text,
                            "issues": event_data.get("issues", []),
                        },
                    )
                    queue_service.update_task_status(
                        task_id,
                        "paused",
                        task_type="review",
                        session_id=session_id,
                        retry_count=attempt - 1,
                    )
                    queue_service.push_event(task_id, queue_service.DONE_SENTINEL, {}, task_type="review")
                    print(f"[Worker] Task {task_id} paused at breakpoint", flush=True)
                    return

            queue_service.update_task_status(
                task_id,
                "completed",
                task_type="review",
                retry_count=attempt - 1,
                next_retry_at=None,
                last_error=None,
                error_code=None,
                dead_letter=False,
            )
            queue_service.push_event(task_id, queue_service.DONE_SENTINEL, {}, task_type="review")
            print(f"[Worker] Task {task_id} completed", flush=True)
            return

        except asyncio.CancelledError:
            queue_service.push_event(
                task_id,
                "error",
                {"message": TASK_CANCELLED_MESSAGE, "code": "REVIEW_TASK_CANCELLED"},
                task_type="review",
            )
            queue_service.push_event(task_id, queue_service.DONE_SENTINEL, {}, task_type="review")
            queue_service.update_task_status(
                task_id,
                "cancelled",
                task_type="review",
                retry_count=max(0, attempt - 1),
                next_retry_at=None,
                last_error=TASK_CANCELLED_MESSAGE,
                error_code="REVIEW_TASK_CANCELLED",
                dead_letter=False,
            )
            raise

        except Exception as exc:
            print(f"[Worker] Task {task_id} failed on attempt {attempt}: {exc}", flush=True)
            traceback.print_exc()
            if attempt <= max_retries:
                delay_seconds = max(retry_backoff_seconds, 0.1) * attempt
                queue_service.update_task_status(
                    task_id,
                    "retrying",
                    task_type="review",
                    retry_count=attempt,
                    last_error=TASK_RETRYING_MESSAGE,
                    error_code="REVIEW_TASK_RETRYING",
                    next_retry_at=time.time() + delay_seconds,
                    dead_letter=False,
                )
                queue_service.push_event(
                    task_id,
                    "retry_scheduled",
                    {
                        "message": TASK_RETRYING_MESSAGE,
                        "code": "REVIEW_TASK_RETRYING",
                        "retry_count": attempt,
                        "delay_seconds": delay_seconds,
                    },
                    task_type="review",
                )
                await asyncio.sleep(delay_seconds)
                continue

            queue_service.push_event(
                task_id,
                "error",
                {"message": TASK_FAILURE_MESSAGE, "code": "REVIEW_TASK_FAILED"},
                task_type="review",
            )
            queue_service.push_event(task_id, queue_service.DONE_SENTINEL, {}, task_type="review")
            queue_service.update_task_status(
                task_id,
                "dead_letter",
                task_type="review",
                retry_count=attempt - 1,
                next_retry_at=None,
                last_error=TASK_FAILURE_MESSAGE,
                error_code="REVIEW_TASK_FAILED",
                dead_letter=True,
            )
            return
