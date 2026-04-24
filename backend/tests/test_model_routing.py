from fastapi.testclient import TestClient

from src import llm_client, main
from src.config import get_settings


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def _build_fake_client(call_log: list[str], failures: set[str] | None = None):
    failures = failures or set()

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            call_log.append(kwargs["model"])
            if kwargs["model"] in failures:
                raise RuntimeError(f"{kwargs['model']} unavailable")
            return _FakeResponse("ok", kwargs["model"])

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    return _FakeClient()


def test_available_models_exposes_current_review_model_chain():
    settings = get_settings()

    assert llm_client.available_models() == [
        {"key": llm_client.DEFAULT_MODEL_KEY, "label": settings.primary_review_model},
        {"key": "fallback", "label": settings.fallback_review_model},
    ]


def test_create_chat_completion_uses_review_lane_primary_model(monkeypatch):
    call_log: list[str] = []
    settings = get_settings()
    monkeypatch.setattr(llm_client, "_get_siliconflow_client", lambda api_key=None: _build_fake_client(call_log))

    response = llm_client.create_chat_completion(
        model=llm_client.DEFAULT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == "ok"
    assert call_log == [settings.primary_review_model]


def test_create_chat_completion_uses_chat_lane_primary_model(monkeypatch):
    call_log: list[str] = []
    settings = get_settings()
    monkeypatch.setattr(llm_client, "_get_siliconflow_client", lambda api_key=None: _build_fake_client(call_log))

    response = llm_client.create_chat_completion(
        lane=llm_client.CHAT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == "ok"
    assert call_log == [settings.primary_chat_model]


def test_create_chat_completion_falls_back_within_chat_lane(monkeypatch):
    call_log: list[str] = []
    settings = get_settings()
    monkeypatch.setattr(
        llm_client,
        "_get_siliconflow_client",
        lambda api_key=None: _build_fake_client(call_log, failures={settings.primary_chat_model}),
    )

    response = llm_client.create_chat_completion(
        lane=llm_client.CHAT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == "ok"
    assert call_log == [settings.primary_chat_model, settings.fallback_chat_model]


def test_chat_endpoint_uses_chat_lane_and_returns_degraded_reply_on_failure(monkeypatch):
    client = TestClient(main.app)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main.auth,
        "get_user_from_token",
        lambda token: {"id": "user-1", "email": "user@example.com"} if token == "token-a" else None,
    )

    def _fail_chat_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("chat lane unavailable")

    monkeypatch.setattr(main, "create_chat_completion", _fail_chat_completion)

    response = client.post(
        "/api/chat",
        json={
            "message": "押金有什么问题？",
            "contract_text": "押金不予退还。",
            "risk_summary": "[high] 押金条款：押金不予退还",
            "review_session_id": "session-1",
        },
        headers={"Authorization": "Bearer token-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["degraded"] is True
    assert "押金条款" in payload["reply"]
    assert captured["lane"] == llm_client.CHAT_MODEL_KEY
