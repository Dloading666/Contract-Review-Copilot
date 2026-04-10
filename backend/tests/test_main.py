from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import main
from src.commerce import (
    AccountStateError,
    ChatChargeReservation,
    InsufficientFundsError,
)


def build_user(**overrides):
    user = {
        "id": "user-1",
        "email": "user@example.com",
        "emailVerified": True,
        "phone": "13800138000",
        "phoneVerified": True,
        "accountStatus": "active",
        "walletBalanceFen": 600,
        "freeReviewRemaining": 2,
        "mustBindPhone": False,
        "createdAt": "2026-04-09T00:00:00Z",
    }
    user.update(overrides)
    return user


def auth_header(token: str = "token-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_review_session(session_id: str, **overrides):
    session = {
        "reviewSessionId": session_id,
        "billingType": "free_review",
        "questionQuotaTotal": 15,
        "questionQuotaUsed": 0,
        "extraQuestionPriceFen": 8,
        "reviewPriceFen": 100,
        "status": "reviewing",
    }
    session.update(overrides)
    return session


class _FakeResponse:
    def __init__(self, content: str, model: str = "kimi-k2.5"):
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
    response_account = client.get("/api/account/summary")
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

    assert response_account.status_code == 401
    assert response_chat.status_code == 401
    assert response_review.status_code == 401
    assert response_export.status_code == 401


def test_models_endpoint_returns_fixed_kimi_model(client):
    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == {
        "default_model": "kimi",
        "models": [{"key": "kimi", "label": "Kimi K2.5"}],
    }


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


def test_phone_send_code_uses_sms_provider(client, monkeypatch):
    captured = {}

    def fake_send_phone_verification_code(phone: str):
        captured["phone"] = phone
        return {"success": True, "dev_code": "654321"}

    monkeypatch.setattr(main.auth, "send_phone_verification_code", fake_send_phone_verification_code)

    response = client.post("/api/auth/phone/send-code", json={"phone": "13800138000"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "dev_code": "654321"}
    assert captured["phone"] == "13800138000"


def test_phone_login_returns_token_and_user(client, monkeypatch):
    monkeypatch.setattr(
        main.auth,
        "login_with_phone_code",
        lambda phone, code: {
            "success": True,
            "token": "phone-token",
            "user": build_user(phone=phone, email=None, emailVerified=False),
        },
    )

    response = client.post(
        "/api/auth/phone/login",
        json={"phone": "13800138000", "code": "123456"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token"] == "phone-token"
    assert payload["user"]["phone"] == "13800138000"
    assert payload["user"]["freeReviewRemaining"] == 2


def test_email_login_returns_user_that_must_bind_phone(client, monkeypatch):
    monkeypatch.setattr(main.auth, "login_with_password", lambda email, password: "email-token")
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: build_user(
            email="legacy@example.com",
            phone=None,
            phoneVerified=False,
            mustBindPhone=True,
            freeReviewRemaining=0,
        ) if token == "email-token" else None,
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "legacy@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["mustBindPhone"] is True


def test_bind_phone_returns_updated_user(client, monkeypatch):
    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: build_user(
            id="legacy-user",
            phone=None,
            phoneVerified=False,
            mustBindPhone=True,
            freeReviewRemaining=0,
        ) if token == "token-a" else None,
    )
    monkeypatch.setattr(
        main.auth,
        "bind_phone_for_user",
        lambda user_id, phone, code: {
            "success": True,
            "user": build_user(
                id=user_id,
                phone=phone,
                phoneVerified=True,
                mustBindPhone=False,
                freeReviewRemaining=2,
            ),
        },
    )

    response = client.post(
        "/api/auth/phone/bind",
        json={"phone": "13800138000", "code": "123456"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["user"]["phoneVerified"] is True
    assert response.json()["user"]["mustBindPhone"] is False
    assert response.json()["user"]["freeReviewRemaining"] == 2


def test_account_summary_returns_wallet_bundle(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id))
    monkeypatch.setattr(main, "list_wallet_transactions", lambda user_id, limit=12: [{"transaction_id": "txn-1"}])
    monkeypatch.setattr(main, "list_recharge_orders", lambda user_id, limit=6: [{"order_id": "order-1"}])

    response = client.get("/api/account/summary", headers=auth_header())

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == "user-1"
    assert payload["recentTransactions"] == [{"transaction_id": "txn-1"}]
    assert payload["recentRechargeOrders"] == [{"order_id": "order-1"}]


def test_email_only_user_cannot_review_or_chat_until_phone_is_bound(client, monkeypatch):
    user = build_user(
        phone=None,
        phoneVerified=False,
        mustBindPhone=True,
        freeReviewRemaining=0,
        walletBalanceFen=0,
    )
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: user if token == "token-a" else None)

    review_response = client.post(
        "/api/review",
        json={"contract_text": "contract text"},
        headers=auth_header(),
    )
    chat_response = client.post(
        "/api/chat",
        json={
            "message": "what is the problem?",
            "contract_text": "contract text",
            "risk_summary": "",
            "review_session_id": "session-1",
        },
        headers=auth_header(),
    )

    assert review_response.status_code == 403
    assert chat_response.status_code == 403


def test_create_wallet_recharge_order_returns_wechat_native_order(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main,
        "create_native_order",
        lambda order_id, amount_fen, description: SimpleNamespace(
            code_url=f"weixin://pay/{order_id}",
            response_payload={"prepay_id": "prepay-1", "amount_fen": amount_fen, "description": description},
        ),
    )

    def fake_create_recharge_order(**kwargs):
        captured.update(kwargs)
        return {
            "order_id": kwargs["order_id"],
            "amount_fen": kwargs["amount_fen"],
            "status": "pending",
            "code_url": kwargs["code_url"],
        }

    monkeypatch.setattr(main, "create_recharge_order", fake_create_recharge_order)

    response = client.post(
        "/api/wallet/recharge/orders",
        json={"amount_fen": 990},
        headers=auth_header(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "pending"
    assert payload["order"]["code_url"].startswith("weixin://pay/recharge-")
    assert payload["minimumAmountFen"] == 100
    assert captured["amount_fen"] == 990


def test_get_wallet_recharge_order_marks_pending_order_paid_on_poll(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main,
        "get_recharge_order",
        lambda order_id, user_id=None: {
            "order_id": order_id,
            "status": "pending",
            "amount_fen": 990,
        },
    )
    monkeypatch.setattr(
        main,
        "query_order_by_out_trade_no",
        lambda order_id: {"trade_state": "SUCCESS", "transaction_id": "wx-100"},
    )
    monkeypatch.setattr(
        main,
        "mark_recharge_order_paid",
        lambda order_id, provider_transaction_id=None, callback_payload=None: {
            "order_id": order_id,
            "status": "paid",
            "provider_transaction_id": provider_transaction_id,
        },
    )
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id, walletBalanceFen=1590))

    response = client.get("/api/wallet/recharge/orders/order-1", headers=auth_header())

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "paid"
    assert payload["order"]["provider_transaction_id"] == "wx-100"
    assert payload["account"]["walletBalanceFen"] == 1590


def test_wechat_callback_marks_order_paid(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        main,
        "parse_payment_callback",
        lambda headers, body: {"payment": {"out_trade_no": "order-1", "transaction_id": "wx-200"}},
    )
    monkeypatch.setattr(
        main,
        "mark_recharge_order_paid",
        lambda order_id, provider_transaction_id=None, callback_payload=None: captured.update(
            {
                "order_id": order_id,
                "provider_transaction_id": provider_transaction_id,
                "callback_payload": callback_payload,
            }
        ),
    )

    response = client.post("/api/payments/wechat/callback", content=b"encrypted-payload")

    assert response.status_code == 200
    assert response.json()["code"] == "SUCCESS"
    assert captured["order_id"] == "order-1"
    assert captured["provider_transaction_id"] == "wx-200"


def test_review_generates_unique_session_ids_and_streams_account_updates(client, monkeypatch):
    captured_session_ids = []
    captured_model_keys = []
    status_updates = []

    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    def fake_reserve_review_session(**kwargs):
        captured_session_ids.append(kwargs["session_id"])

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        captured_model_keys.append(model_key)
        yield {"event": "review_started", "data": {"session_id": session_id}}
        yield {"event": "review_complete", "data": {"session_id": session_id}}

    monkeypatch.setattr(main, "reserve_review_session", fake_reserve_review_session)
    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id))
    monkeypatch.setattr(main, "get_chat_session_summary", lambda user_id, session_id: build_review_session(session_id, status="completed"))
    monkeypatch.setattr(
        main,
        "update_review_session_status",
        lambda session_id, status, error_message=None: status_updates.append((session_id, status, error_message)),
    )

    bodies = []
    for _ in range(2):
        with client.stream(
            "POST",
            "/api/review",
            json={"contract_text": "contract text", "filename": "lease.docx"},
            headers=auth_header(),
        ) as response:
            assert response.status_code == 200
            bodies.append("".join(response.iter_text()))

    assert len(captured_session_ids) == 2
    assert captured_session_ids[0] != captured_session_ids[1]
    assert all(re.fullmatch(r"session-[0-9a-f]{32}", session_id) for session_id in captured_session_ids)
    assert captured_model_keys == ["kimi", "kimi"]
    assert all("event: review_started" in body for body in bodies)
    assert all("event: review_complete" in body for body in bodies)
    assert [status for _, status, _ in status_updates] == ["reviewing", "completed", "reviewing", "completed"]


def test_review_returns_payment_required_when_quota_and_balance_are_missing(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main,
        "reserve_review_session",
        lambda **kwargs: (_ for _ in ()).throw(InsufficientFundsError("balance is not enough")),
    )

    response = client.post(
        "/api/review",
        json={"contract_text": "contract text"},
        headers=auth_header(),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "INSUFFICIENT_BALANCE"


def test_review_rolls_back_reserved_session_when_stream_fails_before_start(client, monkeypatch):
    rolled_back = []

    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(main, "reserve_review_session", lambda **kwargs: None)

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        raise RuntimeError("stream failed before start")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "run_review_stream", fake_run_review_stream)
    monkeypatch.setattr(
        main,
        "rollback_reserved_review_session",
        lambda session_id, reason=None: rolled_back.append((session_id, reason)),
    )

    with client.stream(
        "POST",
        "/api/review",
        json={"contract_text": "contract text", "session_id": "session-fail"},
        headers=auth_header(),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: error" in body
    assert rolled_back == [("session-fail", "stream failed before start")]


def test_confirm_breakpoint_enforces_owner_and_streams_completion(client, monkeypatch):
    token_users = {
        "token-a": build_user(id="owner-1"),
        "token-b": build_user(id="owner-2"),
    }
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: token_users.get(token))
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "delete_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id))
    monkeypatch.setattr(main, "get_chat_session_summary", lambda user_id, session_id: build_review_session(session_id, status="completed"))

    status_updates = []
    monkeypatch.setattr(
        main,
        "update_review_session_status",
        lambda session_id, status, error_message=None: status_updates.append((session_id, status, error_message)),
    )

    async def fake_run_aggregation_stream(contract_text: str, session_id: str, issues: list[dict], model_key: str | None = None):
        assert model_key == "kimi"
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
    assert [status for _, status, _ in status_updates] == ["reviewing", "completed"]


def test_confirm_breakpoint_can_resume_from_request_payload_when_cache_is_missing(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user(id="owner-1") if token == "token-a" else None)
    monkeypatch.setattr(main, "get_json", lambda _key: None)
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id))
    monkeypatch.setattr(main, "get_chat_session_summary", lambda user_id, session_id: build_review_session(session_id, status="completed"))

    status_updates = []
    monkeypatch.setattr(
        main,
        "update_review_session_status",
        lambda session_id, status, error_message=None: status_updates.append((session_id, status, error_message)),
    )

    async def fake_run_aggregation_stream(contract_text: str, session_id: str, issues: list[dict], model_key: str | None = None):
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
    assert [status for _, status, _ in status_updates] == ["reviewing", "completed"]


def test_chat_endpoint_uses_review_session_billing_and_context(client, monkeypatch):
    user = build_user(walletBalanceFen=592)
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: user if token == "token-a" else None)
    monkeypatch.setattr(
        main,
        "reserve_chat_turn",
        lambda user_id, review_session_id: ChatChargeReservation(
            session_id=review_session_id,
            user_id=user_id,
            charged_fen=8,
            transaction_id="txn-8",
            question_quota_total=15,
            question_quota_used=16,
            extra_question_price_fen=8,
        ),
    )
    monkeypatch.setattr(main, "get_account_summary", lambda user_id: build_user(id=user_id, walletBalanceFen=592))
    monkeypatch.setattr(
        main,
        "get_chat_session_summary",
        lambda user_id, session_id: build_review_session(
            session_id,
            questionQuotaUsed=16,
            status="completed",
            billingType="wallet_paid",
        ),
    )

    captured = {}

    def fake_create_chat_completion(**kwargs):
        captured.update(kwargs)
        return _FakeResponse("answer from kimi")

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
    assert payload["reply"] == "answer from kimi"
    assert payload["chargedFen"] == 8
    assert payload["reviewSession"]["questionQuotaUsed"] == 16
    assert captured["model"] == "kimi"
    assert "deposit is not refundable" in captured["messages"][0]["content"]


def test_chat_returns_payment_required_when_question_charge_cannot_be_reserved(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(
        main,
        "reserve_chat_turn",
        lambda user_id, review_session_id: (_ for _ in ()).throw(InsufficientFundsError("wallet balance is too low")),
    )

    response = client.post(
        "/api/chat",
        json={
            "message": "can I ask another question?",
            "contract_text": "contract text",
            "risk_summary": "",
            "review_session_id": "session-42",
        },
        headers=auth_header(),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "INSUFFICIENT_BALANCE"


def test_chat_rolls_back_charge_when_model_call_fails(client, monkeypatch):
    reservation = ChatChargeReservation(
        session_id="session-42",
        user_id="user-1",
        charged_fen=8,
        transaction_id="txn-8",
        question_quota_total=15,
        question_quota_used=16,
        extra_question_price_fen=8,
    )
    rolled_back = []

    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)
    monkeypatch.setattr(main, "reserve_chat_turn", lambda user_id, review_session_id: reservation)
    monkeypatch.setattr(
        main,
        "create_chat_completion",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("kimi unavailable")),
    )
    monkeypatch.setattr(
        main,
        "rollback_chat_turn",
        lambda reservation, reason=None: rolled_back.append((reservation.transaction_id, reason)),
    )

    response = client.post(
        "/api/chat",
        json={
            "message": "what now?",
            "contract_text": "contract text",
            "risk_summary": "",
            "review_session_id": "session-42",
        },
        headers=auth_header(),
    )

    assert response.status_code == 500
    assert rolled_back == [("txn-8", "kimi unavailable")]


def test_export_report_docx_returns_word_document(client, monkeypatch):
    monkeypatch.setattr(main.auth, "get_user_from_token", lambda token: build_user() if token == "token-a" else None)

    response = client.post(
        "/api/review/export-docx",
        json={
            "filename": "lease.docx",
            "report_paragraphs": ["## review result", "one high-risk clause was found"],
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "filename*=UTF-8" in response.headers["content-disposition"]
    assert response.content.startswith(b"PK")
