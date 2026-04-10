import pytest

from src import llm_client
from src.config import get_settings


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_available_models_exposes_current_review_model():
    settings = get_settings()

    assert llm_client.available_models() == [
        {"key": llm_client.DEFAULT_MODEL_KEY, "label": settings.review_model},
    ]


def test_create_chat_completion_uses_review_model_once_even_with_allow_fallback(monkeypatch):
    capture: dict[str, object] = {}

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            capture.update(kwargs)
            return _FakeResponse("ok", kwargs["model"])

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(llm_client, "_get_client", lambda: _FakeClient())

    response = llm_client.create_chat_completion(
        model=llm_client.DEFAULT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
        allow_fallback=True,
    )

    assert response.choices[0].message.content == "ok"
    assert capture["model"] == get_settings().review_model
    assert capture["messages"] == [{"role": "user", "content": "hello"}]


def test_extract_text_from_image_uses_ocr_model_and_image_url_format(monkeypatch):
    capture: dict[str, object] = {}
    settings = get_settings()

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            capture.update(kwargs)
            return _FakeResponse("甲方：张三", kwargs["model"])

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(llm_client, "_get_client", lambda: _FakeClient())

    text, used_model = llm_client.extract_text_from_image(
        image_bytes=b"fake-image",
        mime_type="image/png",
        filename="contract.png",
    )

    content = capture["messages"][0]["content"]
    assert text == "甲方：张三"
    assert used_model == settings.ocr_model
    assert capture["model"] == settings.ocr_model
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_normalize_image_mime_type_rejects_unsupported_types():
    with pytest.raises(ValueError, match="JPG"):
        llm_client.normalize_image_mime_type("application/pdf", "contract.pdf")
