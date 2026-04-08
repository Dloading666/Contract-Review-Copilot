import pytest

from src import llm_client


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_create_chat_completion_falls_back_to_gemma4(monkeypatch):
    capture: dict = {}

    class _FailingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            raise RuntimeError("primary unavailable")

    class _GemmaClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            capture["kwargs"] = kwargs
            return _FakeResponse("fallback ok", kwargs["model"])

    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: _FailingClient())
    monkeypatch.setattr(
        llm_client,
        "_ollama_native_chat_completion",
        lambda model_id, request_kwargs: capture.update({"model_id": model_id, "kwargs": request_kwargs})
        or _FakeResponse("fallback ok", model_id),
    )

    response = llm_client.create_chat_completion(
        model="glm-5",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == "fallback ok"
    assert capture["model_id"] == llm_client.resolve_model(llm_client.FALLBACK_MODEL_KEY).model_id
    assert capture["kwargs"]["messages"][0]["content"] == "hello"


def test_create_chat_completion_raises_when_primary_and_fallback_fail(monkeypatch):
    class _FailingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: _FailingClient())
    monkeypatch.setattr(
        llm_client,
        "_ollama_native_chat_completion",
        lambda model_id, request_kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        llm_client.create_chat_completion(
            model="glm-5",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.1,
            max_tokens=32,
        )
