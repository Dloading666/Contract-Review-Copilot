from src import main
from src.agents import entity_extraction
from src.search import duckduckgo


def test_create_chat_completion_returns_cached_response(monkeypatch):
    monkeypatch.setattr(
        entity_extraction,
        "get_json",
        lambda _key: {"content": "cached-response", "model": "Qwen/Qwen3.5-4B"},
    )
    monkeypatch.setattr(
        entity_extraction,
        "_core_create_chat_completion",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called on cache hit")),
    )

    response = entity_extraction.create_chat_completion(
        model="review",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
    )

    assert response.choices[0].message.content == "cached-response"
    assert response.model == "Qwen/Qwen3.5-4B"


def test_search_web_uses_cached_results(monkeypatch):
    cached_results = [{"title": "cached title", "url": "https://example.com", "description": "cached body"}]

    monkeypatch.setattr(duckduckgo, "get_json", lambda _key: cached_results)

    class _ShouldNotCallDDGS:
        def __enter__(self):
            raise AssertionError("DDGS should not be called on cache hit")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(duckduckgo, "DDGS", _ShouldNotCallDDGS)

    assert duckduckgo.search_web("rent contract law") == cached_results


def test_load_paused_session_reads_from_cache(monkeypatch):
    expected = {
        "owner": "owner@example.com",
        "contract_text": "合同文本",
        "issues": [{"clause": "押金条款"}],
    }

    main.paused_sessions.clear()
    monkeypatch.setattr(main, "get_json", lambda _key: expected)

    loaded = main.load_paused_session("session-redis")

    assert loaded == expected
    assert main.paused_sessions["session-redis"] == expected


def test_store_paused_session_keeps_memory_copy_when_cache_write_fails(monkeypatch):
    capture: dict = {}
    session_data = {
        "owner": "owner@example.com",
        "contract_text": "合同文本",
        "issues": [],
    }

    main.paused_sessions.clear()
    monkeypatch.setattr(main, "get_ttl_seconds", lambda _kind: 7200)
    monkeypatch.setattr(
        main,
        "set_json",
        lambda key, value, ttl: capture.update({"key": key, "value": value, "ttl": ttl}) or False,
    )

    main.store_paused_session("session-fallback", session_data)

    assert main.paused_sessions["session-fallback"] == session_data
    assert capture["ttl"] == 7200
