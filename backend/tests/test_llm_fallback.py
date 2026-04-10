import pytest

from src import llm_client


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_available_models_only_exposes_kimi():
    assert llm_client.available_models() == [{"key": "kimi", "label": "Kimi K2.5"}]


def test_resolve_model_defaults_to_kimi_cloud_route():
    resolved = llm_client.resolve_model(None)

    assert resolved.key == "kimi"
    assert resolved.label == "Kimi K2.5"
    assert resolved.is_local is False


def test_create_chat_completion_uses_primary_model_once_even_with_allow_fallback(monkeypatch):
    capture = {"calls": 0}

    class _FakeClient:
        chat = type("Chat", (), {"completions": None})()

    def fake_chat_completion(client, model_id, request_kwargs):
        capture["calls"] += 1
        capture["model_id"] = model_id
        capture["request_kwargs"] = request_kwargs
        return _FakeResponse("ok", model_id)

    monkeypatch.setattr(llm_client, "_get_client_for_resolved_model", lambda resolved: _FakeClient())
    monkeypatch.setattr(llm_client, "_chat_completion", fake_chat_completion)

    response = llm_client.create_chat_completion(
        model="kimi",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
        allow_fallback=True,
    )

    assert response.choices[0].message.content == "ok"
    assert capture["calls"] == 1
    assert capture["model_id"] == llm_client.resolve_model("kimi").model_id
    assert capture["request_kwargs"]["messages"][0]["content"] == "hello"


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


def test_normalize_image_mime_type_rejects_unsupported_types():
    with pytest.raises(ValueError, match="JPG"):
        llm_client.normalize_image_mime_type("application/pdf", "contract.pdf")
