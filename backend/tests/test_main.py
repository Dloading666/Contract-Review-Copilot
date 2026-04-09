from fastapi.testclient import TestClient

from src import main


def test_protected_endpoints_require_auth():
    client = TestClient(main.app)

    autofix_response = client.post("/api/autofix", json={})
    chat_response = client.post("/api/chat", json={"message": "hello"})
    ocr_response = client.post(
        "/api/ocr",
        files={"file": ("contract.png", b"fake-image", "image/png")},
    )
    export_response = client.post("/api/review/export-docx", json={"report_paragraphs": ["report body"]})
    review_response = client.post("/api/review", json={"contract_text": "contract text"})

    assert autofix_response.status_code == 401
    assert chat_response.status_code == 401
    assert ocr_response.status_code == 401
    assert export_response.status_code == 401
    assert review_response.status_code == 401


def test_models_endpoint_returns_fixed_kimi_model():
    client = TestClient(main.app)
    response = client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model"] == "kimi"
    assert payload["models"] == [{"key": "kimi", "label": "Kimi K2.5"}]


def test_register_rejects_invalid_email_without_top_level_domain(monkeypatch):
    monkeypatch.setattr(main.auth, "register_user", lambda *_args, **_kwargs: {"success": True})

    client = TestClient(main.app)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@domaincom",
            "code": "123456",
            "password": "secret123",
        },
    )

    assert response.status_code == 400


def test_review_generates_uuid_session_id_when_client_omits_one(monkeypatch):
    captured: list[str] = []

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        captured.append(session_id)
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: {"email": "owner@example.com"} if token == "token-a" else None,
    )

    client = TestClient(main.app)
    for _ in range(2):
        with client.stream(
            "POST",
            "/api/review",
            json={"contract_text": "contract text", "model": "gemma4"},
            headers={"Authorization": "Bearer token-a"},
        ) as response:
            assert response.status_code == 200
            list(response.iter_text())

    assert len(captured) == 2
    assert captured[0] != captured[1]
    assert all(session_id.startswith("session-") for session_id in captured)
    assert all(len(session_id) == len("session-") + 32 for session_id in captured)


def test_chat_endpoint_uses_fixed_kimi_even_if_client_sends_other_model(monkeypatch):
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: {"email": "owner@example.com"} if token == "token-a" else None,
    )

    capture: dict[str, object] = {}

    class _FakeResponse:
        model = "kimi-k2.5"
        choices = [
            type(
                "Choice",
                (),
                {"message": type("Message", (), {"content": "reply from model"})()},
            )()
        ]

    monkeypatch.setattr(
        main,
        "create_chat_completion",
        lambda **kwargs: capture.update(kwargs) or _FakeResponse(),
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/chat",
        json={
            "message": "what is wrong with this deposit clause?",
            "model": "gemma4",
            "contract_text": "deposit is not refundable",
            "risk_summary": "[high] deposit clause: deposit is not refundable",
        },
        headers={"Authorization": "Bearer token-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "reply from model"
    assert payload["model"] == "kimi-k2.5"
    assert capture["model"] == "kimi"
    assert "deposit is not refundable" in capture["messages"][0]["content"]


def test_ocr_endpoint_returns_unified_ingest_payload(monkeypatch):
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: {"email": "owner@example.com"} if token == "token-a" else None,
    )

    captured: dict[str, object] = {}

    class _FakeIngestResult:
        def to_dict(self):
            return {
                "source_type": "image_batch",
                "display_name": "contract.png",
                "used_ocr_model": "kimi-k2.5",
                "merged_text": "party a\\nparty b",
                "pages": [
                    {
                        "page_index": 1,
                        "filename": "contract.png",
                        "text": "party a\\nparty b",
                        "average_confidence": 0.98,
                        "warnings": ["page 1 has low-confidence text"],
                    }
                ],
                "warnings": ["page 1 has low-confidence text"],
            }

    def fake_ingest_contract_files(uploaded_files):
        captured["files"] = uploaded_files
        return _FakeIngestResult()

    monkeypatch.setattr(main, "ingest_contract_files", fake_ingest_contract_files)

    client = TestClient(main.app)
    response = client.post(
        "/api/ocr/ingest",
        files=[("files", ("contract.png", b"fake-image", "image/png"))],
        headers={"Authorization": "Bearer token-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "image_batch"
    assert payload["display_name"] == "contract.png"
    assert payload["used_ocr_model"] == "kimi-k2.5"
    assert payload["merged_text"] == "party a\\nparty b"
    assert payload["pages"][0]["average_confidence"] == 0.98
    assert payload["warnings"] == ["page 1 has low-confidence text"]
    assert captured["files"][0].filename == "contract.png"
    assert captured["files"][0].content_type == "image/png"
    assert captured["files"][0].content == b"fake-image"


def test_review_accepts_valid_token_after_user_store_reset(monkeypatch):
    capture: dict[str, str | None] = {}

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        capture["model_key"] = model_key
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)

    main.paused_sessions.clear()
    main.auth._code_store.clear()
    main.auth._user_store.clear()

    email = "restart@example.com"
    send_code_result = main.auth.send_verification_code(email)
    token = main.auth.verify_code(email, send_code_result["dev_code"])

    main.auth._user_store.clear()

    client = TestClient(main.app)
    with client.stream(
        "POST",
        "/api/review",
        json={"contract_text": "contract text", "session_id": "session-auth", "model": "gemma4"},
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        assert response.status_code == 200
        stream_body = "".join(response.iter_text())

    assert "review_complete" in stream_body
    assert capture["model_key"] == "kimi"
    assert main.auth._user_store["restart"]["email"] == email


def test_breakpoint_session_is_owned_and_preserves_issues(monkeypatch):
    capture: dict[str, str | None] = {}

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        capture["review_model_key"] = model_key
        yield {
            "event": "breakpoint",
            "data": {
                "session_id": session_id,
                "breakpoint": {
                    "needs_review": True,
                    "question": "continue?",
                    "issues_count": 1,
                    "critical_count": 0,
                    "high_count": 1,
                    "medium_count": 0,
                },
                "issues": [
                    {
                        "clause": "deposit clause",
                        "level": "high",
                        "risk_level": 3,
                        "issue": "deposit too high",
                        "suggestion": "reduce deposit",
                        "legal_reference": "Civil Code Art. 585",
                    },
                ],
            },
        }

    async def fake_run_aggregation_stream(
        contract_text: str,
        session_id: str,
        issues: list[dict],
        model_key: str | None = None,
    ):
        capture["aggregation_model_key"] = model_key
        assert issues[0]["clause"] == "deposit clause"
        yield {"event": "stream_resume", "data": {"session_id": session_id}}
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    token_users = {
        "token-a": {"email": "owner@example.com"},
        "token-b": {"email": "other@example.com"},
    }

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)
    monkeypatch.setattr(main, "run_aggregation_stream", fake_run_aggregation_stream)
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: token_users.get(token))

    main.paused_sessions.clear()
    client = TestClient(main.app)

    with client.stream(
        "POST",
        "/api/review",
        json={"contract_text": "contract text", "session_id": "session-1", "model": "gemma4"},
        headers={"Authorization": "Bearer token-a"},
    ) as response:
        assert response.status_code == 200
        list(response.iter_text())

    assert main.paused_sessions["session-1"]["issues"][0]["clause"] == "deposit clause"
    assert main.paused_sessions["session-1"]["model_key"] == "kimi"
    assert capture["review_model_key"] == "kimi"

    forbidden_response = client.post(
        "/api/review/confirm/session-1",
        json={"confirmed": True},
        headers={"Authorization": "Bearer token-b"},
    )
    assert forbidden_response.status_code == 403

    with client.stream(
        "POST",
        "/api/review/confirm/session-1",
        json={"confirmed": True},
        headers={"Authorization": "Bearer token-a"},
    ) as response:
        assert response.status_code == 200
        list(response.iter_text())

    assert capture["aggregation_model_key"] == "kimi"
    assert "session-1" not in main.paused_sessions


def test_export_report_docx_returns_word_document(monkeypatch):
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: {"email": "owner@example.com"} if token == "token-a" else None,
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/review/export-docx",
        json={
            "filename": "lease.docx",
            "report_paragraphs": ["## review result", "one high-risk clause was found"],
        },
        headers={"Authorization": "Bearer token-a"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "filename*=UTF-8" in response.headers["content-disposition"]
    assert response.content.startswith(b"PK")
