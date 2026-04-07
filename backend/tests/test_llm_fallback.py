from src.agents import entity_extraction


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [type('Choice', (), {'message': type('Message', (), {'content': content})()})()]


class _FailingClient:
    def __init__(self):
        self.chat = type('Chat', (), {'completions': self})()

    def create(self, **kwargs):
        raise RuntimeError('primary unavailable')


class _CapturingClient:
    def __init__(self, capture: dict):
        self.chat = type('Chat', (), {'completions': self})()
        self._capture = capture

    def create(self, **kwargs):
        self._capture['kwargs'] = kwargs
        return _FakeResponse('fallback ok')


def test_create_chat_completion_falls_back_to_free_model(monkeypatch):
    capture: dict = {}

    monkeypatch.setattr(entity_extraction, 'get_json', lambda key: None)
    monkeypatch.setattr(entity_extraction, 'set_json', lambda key, value, ttl: True)
    monkeypatch.setattr(entity_extraction, 'get_ttl_seconds', lambda kind: 3600)
    monkeypatch.setattr(entity_extraction, 'get_llm_client', lambda *args, **kwargs: _FailingClient())
    monkeypatch.setattr(entity_extraction, 'get_fallback_llm_client', lambda: _CapturingClient(capture))

    response = entity_extraction.create_chat_completion(
        model='glm-5',
        messages=[{'role': 'user', 'content': 'hello'}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == 'fallback ok'
    assert capture['kwargs']['model'] == 'GLM-4.7-Flash'
    assert capture['kwargs']['messages'][0]['content'] == 'hello'
