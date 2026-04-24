from __future__ import annotations

from fastapi.testclient import TestClient

from src import main



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



def test_ocr_ingest_hides_internal_exception_message(monkeypatch):
    main.paused_sessions.clear()
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "set_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_ttl_seconds", lambda _kind: 7200)
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    def broken_ingest(_files):
        raise RuntimeError("provider secret timeout")

    monkeypatch.setattr(main, "ingest_contract_files", broken_ingest)

    client = TestClient(main.app)
    response = client.post(
        "/api/ocr/ingest",
        headers=auth_header(),
        files=[("files", ("contract.png", b"fake-image", "image/png"))],
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INGEST_PROCESSING_FAILED"
    assert "secret" not in payload["error"]



def test_review_stream_hides_internal_exception_message(monkeypatch):
    main.paused_sessions.clear()
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "set_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_ttl_seconds", lambda _kind: 7200)
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    async def broken_review_stream(**_kwargs):
        if False:
            yield {}
        raise RuntimeError("upstream secret failure")

    monkeypatch.setattr(main, "run_review_stream", broken_review_stream)

    client = TestClient(main.app)
    response = client.post(
        "/api/review",
        json={"contract_text": "contract text"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "upstream secret failure" not in response.text
    assert "REVIEW_STREAM_FAILED" in response.text
