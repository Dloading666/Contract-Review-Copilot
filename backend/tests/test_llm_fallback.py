import pytest

from src import llm_client


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_create_chat_completion_does_not_fallback_by_default(monkeypatch):
    class _FailingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            raise RuntimeError("primary unavailable")

    fallback_called = {"value": False}

    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: _FailingClient())
    monkeypatch.setattr(
        llm_client,
        "_ollama_native_chat_completion",
        lambda model_id, request_kwargs: fallback_called.update({"value": True}),
    )

    with pytest.raises(RuntimeError, match="primary unavailable"):
        llm_client.create_chat_completion(
            model="kimi",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.1,
            max_tokens=32,
        )

    assert fallback_called["value"] is False


def test_create_chat_completion_can_opt_into_gemma_fallback(monkeypatch):
    capture: dict = {}

    class _FailingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            raise RuntimeError("primary unavailable")

    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: _FailingClient())
    monkeypatch.setattr(
        llm_client,
        "_ollama_native_chat_completion",
        lambda model_id, request_kwargs: capture.update({"model_id": model_id, "kwargs": request_kwargs})
        or _FakeResponse("fallback ok", model_id),
    )

    response = llm_client.create_chat_completion(
        model="kimi",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
        allow_fallback=True,
    )

    assert response.choices[0].message.content == "fallback ok"
    assert capture["model_id"] == llm_client.resolve_model(llm_client.FALLBACK_MODEL_KEY).model_id
    assert capture["kwargs"]["messages"][0]["content"] == "hello"


def test_extract_text_from_image_uses_cloud_vision_format(monkeypatch):
    capture: dict = {}

    def fake_chat_completion(client, model_id, request_kwargs):
        capture["model_id"] = model_id
        capture["request_kwargs"] = request_kwargs
        return _FakeResponse("甲方：张三", model_id)

    monkeypatch.setattr(llm_client, "_chat_completion", fake_chat_completion)
    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: object())

    text, used_model = llm_client.extract_text_from_image(
        image_bytes=b"fake-image",
        mime_type="image/png",
        model="kimi",
        filename="contract.png",
    )

    content = capture["request_kwargs"]["messages"][0]["content"]
    assert text == "甲方：张三"
    assert used_model == capture["model_id"]
    assert capture["model_id"] == llm_client.resolve_model("kimi").model_id
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_extract_text_from_image_uses_ollama_images_field(monkeypatch):
    capture: dict = {}

    def fake_vision_completion(model_id, prompt, image_bytes, max_tokens, timeout):
        capture["model_id"] = model_id
        capture["prompt"] = prompt
        capture["image_bytes"] = image_bytes
        capture["max_tokens"] = max_tokens
        capture["timeout"] = timeout
        return _FakeResponse("押金：20000", model_id)

    monkeypatch.setattr(llm_client, "_ollama_native_vision_completion", fake_vision_completion)

    text, used_model = llm_client.extract_text_from_image(
        image_bytes=b"local-image",
        mime_type="image/webp",
        model="gemma4",
        filename="contract.webp",
    )

    assert text == "押金：20000"
    assert used_model == capture["model_id"]
    assert capture["model_id"] == llm_client.resolve_model("gemma4").model_id
    assert capture["image_bytes"] == b"local-image"
    assert capture["max_tokens"] == 4096


def test_normalize_image_mime_type_rejects_unsupported_types():
    with pytest.raises(ValueError, match="JPG"):
        llm_client.normalize_image_mime_type("application/pdf", "contract.pdf")
