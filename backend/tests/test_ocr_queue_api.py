from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src import main
from src.services import queue_service


def build_user(**overrides):
    user = {
        "id": "user-1",
        "email": "user@example.com",
        "emailVerified": True,
        "accountStatus": "active",
        "createdAt": "2026-04-09T00:00:00Z",
    }
    user.update(overrides)
    return user


def auth_header(token: str = "token-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def reset_queue_state() -> None:
    queue_service._memory_tasks.clear()
    queue_service._memory_events.clear()
    queue_service._memory_pending_counts.clear()


def test_ocr_queue_creates_pending_task_and_status_endpoint_reads_it(monkeypatch):
    main.paused_sessions.clear()
    reset_queue_state()

    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "set_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_ttl_seconds", lambda _kind: 7200)
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(queue_service, "get_redis_client", lambda: None)

    staged = []
    monkeypatch.setattr(main, "stage_ocr_task_files", lambda task_id, files: staged.append((task_id, len(files))))

    async def fake_run_queued_ocr(**_kwargs):
        return None

    monkeypatch.setattr(main.ocr_worker, "run_queued_ocr", fake_run_queued_ocr)

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(main.asyncio, "create_task", fake_create_task)

    client = TestClient(main.app)
    response = client.post(
        "/api/ocr/queue",
        headers=auth_header(),
        files=[("files", ("contract.png", b"fake-image", "image/png"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["queue_position"] == 1
    assert payload["task_id"]
    assert staged == [(payload["task_id"], 1)]
    assert len(scheduled) == 1

    status_response = client.get(f"/api/ocr/queue/{payload['task_id']}", headers=auth_header())
    assert status_response.status_code == 200

    task_payload = status_response.json()
    assert task_payload["task_id"] == payload["task_id"]
    assert task_payload["status"] == "pending"
    assert task_payload["task_type"] == "ocr"

