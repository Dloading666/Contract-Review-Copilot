from __future__ import annotations

from pathlib import Path

import pytest

from src.ocr.ingest_service import UploadedContractFile
from src.ocr.task_storage import TASK_RUNTIME_ROOT, cleanup_staged_ocr_task_files, stage_ocr_task_files
from src.services import queue_service
from src.workers import ocr_worker, review_worker


def reset_queue_state() -> None:
    queue_service._memory_tasks.clear()
    queue_service._memory_events.clear()
    queue_service._memory_pending_counts.clear()


@pytest.fixture(autouse=True)
def _reset_queue(monkeypatch):
    reset_queue_state()
    monkeypatch.setattr(queue_service, "get_redis_client", lambda: None)
    yield
    reset_queue_state()


@pytest.mark.asyncio
async def test_review_worker_retries_then_completes(monkeypatch):
    attempts = {"count": 0}

    async def fake_run_review_stream(**_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary upstream failure")
        yield {"event": "logic_review", "data": {"issues": [{"title": "risk-a"}]}}

    monkeypatch.setattr(review_worker, "run_review_stream", fake_run_review_stream)

    task_id = queue_service.create_task(
        user_id="user-1",
        contract_text="合同正文",
        session_id="session-1",
        review_mode="deep",
        task_type="review",
        max_retries=1,
    )

    await review_worker.run_queued_review(
        task_id=task_id,
        contract_text="合同正文",
        session_id="session-1",
        user_id="user-1",
        review_mode="deep",
        on_breakpoint=lambda *_args, **_kwargs: None,
        max_retries=1,
        retry_backoff_seconds=0,
    )

    task = queue_service.get_task(task_id, task_type="review")
    events = queue_service.get_events(task_id, task_type="review")

    assert task is not None
    assert task["status"] == "completed"
    assert task["retry_count"] == 1
    assert task["dead_letter"] is False
    assert any(event["event"] == "retry_scheduled" for event in events)
    assert any(event["event"] == "logic_review" for event in events)
    assert events[-1]["event"] == queue_service.DONE_SENTINEL


@pytest.mark.asyncio
async def test_ocr_worker_dead_letters_after_exhausting_retries(monkeypatch):
    task_id = queue_service.create_task(
        user_id="user-1",
        filename="contract.png",
        task_type="ocr",
        max_retries=1,
    )

    cleanup_staged_ocr_task_files(task_id)
    stage_ocr_task_files(
        task_id,
        [UploadedContractFile(filename="contract.png", content=b"fake-image", content_type="image/png")],
    )

    def broken_ingest(_files):
        raise RuntimeError("ocr provider unavailable")

    monkeypatch.setattr(ocr_worker, "ingest_contract_files", broken_ingest)

    await ocr_worker.run_queued_ocr(task_id=task_id, max_retries=1, retry_backoff_seconds=0)

    task = queue_service.get_task(task_id, task_type="ocr")

    assert task is not None
    assert task["status"] == "dead_letter"
    assert task["retry_count"] == 1
    assert task["dead_letter"] is True
    assert task["error_code"] == "OCR_TASK_FAILED"
    assert task["last_error"] == ocr_worker.OCR_TASK_FAILURE_MESSAGE
    assert not (Path(TASK_RUNTIME_ROOT) / task_id).exists()
