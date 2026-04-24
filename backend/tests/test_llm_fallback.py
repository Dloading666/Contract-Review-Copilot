from src import llm_client


class _FakeResponse:
    def __init__(self, content: str, model: str):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_available_models_hides_empty_fallback(monkeypatch):
    monkeypatch.setattr(llm_client, "_get_model_chain_for_lane", lambda lane: ("deepseek-chat", None))

    assert llm_client.available_models() == [
        {"key": llm_client.DEFAULT_MODEL_KEY, "label": "deepseek-chat"},
    ]


def test_create_chat_completion_uses_primary_model_only_when_no_fallback(monkeypatch):
    capture: dict[str, object] = {}

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            capture.update(kwargs)
            return _FakeResponse("ok", kwargs["model"])

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(llm_client, "_get_text_generation_client", lambda: _FakeClient())
    monkeypatch.setattr(llm_client, "_get_model_chain_for_lane", lambda lane: ("deepseek-chat", None))

    response = llm_client.create_chat_completion(
        lane=llm_client.DEFAULT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        temperature=1.0,
        max_tokens=32,
        allow_fallback=True,
    )

    assert response.choices[0].message.content == "ok"
    assert capture["model"] == "deepseek-chat"
    assert capture["messages"] == [{"role": "user", "content": "hello"}]


def test_stream_chat_completion_skips_duplicate_fallback(monkeypatch):
    capture: list[str] = []

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            capture.append(kwargs["model"])
            return iter(())

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(llm_client, "_get_text_generation_client", lambda: _FakeClient())
    monkeypatch.setattr(llm_client, "_get_model_chain_for_lane", lambda lane: ("deepseek-chat", "deepseek-chat"))

    _, used_model = llm_client.stream_chat_completion(
        lane=llm_client.CHAT_MODEL_KEY,
        messages=[{"role": "user", "content": "hello"}],
        allow_fallback=True,
    )

    assert used_model == "deepseek-chat"
    assert capture == ["deepseek-chat"]


def test_get_ocr_fallback_client_uses_dedicated_env(monkeypatch):
    capture: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            capture.update(kwargs)

    monkeypatch.setattr(llm_client, "OpenAI", _FakeOpenAI)
    monkeypatch.setenv("OCR_FALLBACK_API_KEY", "ocr-fallback-key")
    monkeypatch.setenv("OCR_FALLBACK_BASE_URL", "https://api.siliconflow.cn/v1")

    llm_client._get_ocr_fallback_client()

    assert capture["api_key"] == "ocr-fallback-key"
    assert capture["base_url"] == "https://api.siliconflow.cn/v1"



def test_stream_delta_ignores_reasoning_content():
    chunk = type(
        'Chunk',
        (),
        {
            'choices': [
                type(
                    'Choice',
                    (),
                    {'delta': type('Delta', (), {'content': '', 'reasoning_content': 'internal reasoning', 'text': ''})()},
                )()
            ]
        },
    )()

    assert llm_client.extract_stream_delta_text(chunk) == ''



def test_deepseek_v4_disables_thinking():
    assert llm_client._should_disable_thinking('deepseek-v4-flash') is True
