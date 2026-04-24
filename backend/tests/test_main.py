from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src import main


def build_user(**overrides):
    user = {
        "id": "user-1",
        "email": "user@example.com",
        "emailVerified": True,
        "accountStatus": "active",
        "createdAt": "2026-04-09T00:00:00Z",
        "hasPassword": True,
    }
    user.update(overrides)
    return user


def auth_header(token: str = "token-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _FakeResponse:
    def __init__(self, content: str, model: str = "deepseek-v4-flash"):
        self.model = model
        self.choices = [
            type(
                "Choice",
                (),
                {"message": type("Message", (), {"content": content})()},
            )()
        ]


@pytest.fixture
def client(monkeypatch):
    main.paused_sessions.clear()
    monkeypatch.setattr(main, "enforce_rate_limits", lambda _rules: None)
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "set_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_ttl_seconds", lambda _kind: 7200)
    return TestClient(main.app)


def test_protected_endpoints_require_auth(client):
    response_chat = client.post(
        "/api/chat",
        json={
            "message": "hello",
            "contract_text": "deposit is non-refundable",
            "risk_summary": "[high] deposit clause",
            "review_session_id": "session-1",
        },
    )
    response_review = client.post("/api/review", json={"contract_text": "contract text"})
    response_export = client.post(
        "/api/review/export-docx",
        json={"report_paragraphs": ["report body"]},
    )

    assert response_chat.status_code == 401
    assert response_review.status_code == 401
    assert response_export.status_code == 401


def test_models_endpoint_returns_current_review_model(client):
    response = client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model"] == main.DEFAULT_MODEL_KEY
    assert payload["models"][0]["key"] == main.DEFAULT_MODEL_KEY
    assert payload["models"][0]["label"] == main.settings.primary_review_model


def test_normalize_chat_reply_falls_back_for_invisible_content():
    assert main.normalize_chat_reply("\u200b\n\ufeff") == main.EMPTY_CHAT_REPLY_TEXT
    assert main.normalize_chat_reply([{"text": "  可见回答  "}]) == "可见回答"


def test_extract_chat_reply_uses_model_text_fallback_fields():
    response = _FakeResponse("")
    response.choices[0].message.reasoning_content = "  备用可见回复  "

    assert main.extract_chat_reply(response) == main.EMPTY_CHAT_REPLY_TEXT


def test_build_empty_chat_fallback_reply_uses_risk_summary():
    reply = main.build_empty_chat_fallback_reply("[high] 押金条款：押金不退")

    assert "押金条款" in reply
    assert "高风险条款" in reply


def test_register_rejects_invalid_email_without_top_level_domain(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@domaincom",
            "code": "123456",
            "password": "secret123",
        },
    )

    assert response.status_code == 400


def test_auth_honeypot_returns_readable_bot_guard_message(client):
    response = client.post(
        "/api/auth/send-code",
        json={
            "email": "bot@example.com",
            "website": "https://spam.example",
            "client_elapsed_ms": 1000,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"error": "检测到异常注册行为，请刷新后重试", "code": "AUTH_BOT_GUARD"}


def test_send_password_reset_code_uses_current_user_email(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main.auth,
        "send_password_reset_code_for_user",
        lambda user_id: {"success": True, "dev_code": "654321"} if user_id == "user-1" else {"success": False},
    )

    response = client.post("/api/auth/security/send-password-code", headers=auth_header())

    assert response.status_code == 200
    assert response.json() == {"success": True, "dev_code": "654321"}


def test_reset_password_updates_current_user_password(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main.auth,
        "reset_password_with_email_code",
        lambda user_id, code, new_password: {"success": True}
        if user_id == "user-1" and code == "123456" and new_password == "newSecret123"
        else {"success": False, "error": "验证码无效或已过期"},
    )

    response = client.post(
        "/api/auth/security/reset-password",
        json={"code": "123456", "new_password": "newSecret123"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "密码修改成功"}


def test_review_generates_unique_session_ids_and_streams_events(client, monkeypatch):
    captured_session_ids = []
    captured_model_keys = []

    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    async def fake_run_review_stream(
        contract_text: str,
        session_id: str,
        model_key: str | None = None,
        review_mode: str = "deep",
    ):
        captured_session_ids.append(session_id)
        captured_model_keys.append(model_key)
        yield {"event": "review_started", "data": {"session_id": session_id, "review_mode": review_mode}}
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)

    bodies = []
    for _ in range(2):
        with client.stream(
            "POST",
            "/api/review",
            json={"contract_text": "contract text", "filename": "lease.docx", "review_mode": "light"},
            headers=auth_header(),
        ) as response:
            assert response.status_code == 200
            bodies.append("".join(response.iter_text()))

    assert len(captured_session_ids) == 2
    assert captured_session_ids[0] != captured_session_ids[1]
    assert all(re.fullmatch(r"session-[0-9a-f]{32}", session_id) for session_id in captured_session_ids)
    assert captured_model_keys == [main.DEFAULT_MODEL_KEY, main.DEFAULT_MODEL_KEY]
    assert all("event: review_started" in body for body in bodies)
    assert all("event: review_complete" in body for body in bodies)
    assert all('"review_mode": "light"' in body for body in bodies)


def test_review_stores_breakpoint_session_for_owner(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user(id="owner-1") if token == "token-a" else None)

    async def fake_run_review_stream(
        contract_text: str,
        session_id: str,
        model_key: str | None = None,
        review_mode: str = "deep",
    ):
        yield {
            "event": "breakpoint",
            "data": {
                "session_id": session_id,
                "issues": [{"clause": "押金条款", "level": "high"}],
            },
        }

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)

    with client.stream(
        "POST",
        "/api/review",
        json={"contract_text": "contract text", "session_id": "session-break", "filename": "lease.docx"},
        headers=auth_header(),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: breakpoint" in body
    assert main.paused_sessions["session-break"]["owner"] == "owner-1"
    assert main.paused_sessions["session-break"]["filename"] == "lease.docx"


def test_confirm_breakpoint_enforces_owner_and_streams_completion(client, monkeypatch):
    token_users = {
        "token-a": build_user(id="owner-1"),
        "token-b": build_user(id="owner-2"),
    }
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: token_users.get(token))
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)

    async def fake_run_aggregation_stream(
        contract_text: str,
        session_id: str,
        issues: list[dict],
        model_key: str | None = None,
    ):
        assert model_key == main.DEFAULT_MODEL_KEY
        assert issues[0]["clause"] == "deposit clause"
        yield {"event": "stream_resume", "data": {"session_id": session_id}}
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "run_aggregation_stream", fake_run_aggregation_stream)

    main.paused_sessions["session-1"] = {
        "owner": "owner-1",
        "contract_text": "contract text",
        "issues": [{"clause": "deposit clause", "level": "high"}],
        "filename": "lease.docx",
    }

    forbidden_response = client.post(
        "/api/review/confirm/session-1",
        json={"confirmed": True},
        headers=auth_header("token-b"),
    )
    assert forbidden_response.status_code == 403

    with client.stream(
        "POST",
        "/api/review/confirm/session-1",
        json={"confirmed": True},
        headers=auth_header("token-a"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: stream_resume" in body
    assert "event: review_complete" in body
    assert "session-1" not in main.paused_sessions


def test_confirm_breakpoint_can_resume_from_request_payload_when_cache_is_missing(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user(id="owner-1") if token == "token-a" else None)
    monkeypatch.setattr(main, "get_json", lambda _key: None)

    async def fake_run_aggregation_stream(
        contract_text: str,
        session_id: str,
        issues: list[dict],
        model_key: str | None = None,
    ):
        assert contract_text == "contract text"
        assert issues[0]["clause"] == "deposit clause"
        yield {"event": "stream_resume", "data": {"session_id": session_id}}
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "run_aggregation_stream", fake_run_aggregation_stream)

    with client.stream(
        "POST",
        "/api/review/confirm/session-fallback",
        json={
            "confirmed": True,
            "contract_text": "contract text",
            "issues": [{"clause": "deposit clause", "level": "high"}],
            "filename": "lease.docx",
        },
        headers=auth_header(),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: stream_resume" in body
    assert "event: review_complete" in body


def test_chat_endpoint_uses_contract_context(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    captured = {}

    def fake_create_chat_completion(**kwargs):
        captured.update(kwargs)
        return _FakeResponse("answer from review model")

    monkeypatch.setattr(main, "create_chat_completion", fake_create_chat_completion)

    response = client.post(
        "/api/chat",
        json={
            "message": "what is wrong with the deposit clause?",
            "contract_text": "deposit is not refundable",
            "risk_summary": "[high] deposit clause: deposit is not refundable",
            "review_session_id": "session-42",
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "answer from review model"
    assert captured["lane"] == main.CHAT_MODEL_KEY
    assert "deposit is not refundable" in captured["messages"][0]["content"]


def test_chat_endpoint_returns_fallback_when_model_call_fails(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(main, "create_chat_completion", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("upstream down")))

    response = client.post(
        "/api/chat",
        json={
            "message": "can I ask another question?",
            "contract_text": "contract text",
            "risk_summary": "[high] 押金条款：押金不退",
            "review_session_id": "session-42",
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["degraded"] is True
    assert "押金条款" in payload["reply"]


def test_export_report_docx_returns_word_document(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(main, "build_report_docx", lambda paragraphs, filename=None: b"docx-bytes")
    monkeypatch.setattr(main, "build_report_download_name", lambda filename=None: "lease-report.docx")

    response = client.post(
        "/api/review/export-docx",
        json={"report_paragraphs": ["report body"], "filename": "lease.txt"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.content == b"docx-bytes"
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "lease-report.docx" in response.headers["content-disposition"]
