from types import SimpleNamespace
import time

import pytest

from src.graph import review_graph


def _build_settings(**overrides):
    defaults = {
        "review_initial_deadline_seconds": 0.01,
        "review_entity_timeout_seconds": 1.0,
        "review_routing_timeout_seconds": 1.0,
        "review_model_timeout_seconds": 1.0,
        "review_heartbeat_interval_seconds": 0.01,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _sample_entities():
    return {
        "contract_type": "rental_contract",
        "parties": {"lessor": "Alice", "lessee": "Bob"},
        "property": {"address": "Beijing", "area": "45"},
        "rent": {"monthly": 8500},
        "deposit": {"amount": 17000, "conditions": "refundable_after_move_out"},
        "lease_term": {"duration_text": "12_months"},
        "penalty_clause": "two_months_rent",
    }


def _sample_routing(*, legal_focus: list[str] | None = None):
    return {
        "primary_source": "pgvector",
        "secondary_source": None,
        "reason": "test routing",
        "confidence": 0.9,
        "local_context": "",
        "legal_focus": legal_focus or [],
        "pgvector_results": [],
    }


def _deposit_issue(level: str = "high", risk_level: int = 4):
    return {
        "clause": "Deposit clause",
        "level": level,
        "risk_level": risk_level,
        "issue": "Deposit is too high",
        "suggestion": "Reduce the deposit",
        "legal_reference": "Civil Code Art. 585",
    }


def _penalty_issue(level: str = "high", risk_level: int = 4):
    return {
        "clause": "Penalty clause",
        "level": level,
        "risk_level": risk_level,
        "issue": "Penalty is too high",
        "suggestion": "Cap it at one month of rent",
        "legal_reference": "Civil Code Art. 585",
    }


@pytest.mark.asyncio
async def test_run_review_stream_emits_initial_then_deep_update(monkeypatch):
    monkeypatch.setattr(review_graph, "get_settings", lambda: _build_settings())
    monkeypatch.setattr(review_graph, "extract_entities", lambda contract_text, model_key=None: _sample_entities())
    monkeypatch.setattr(
        review_graph,
        "decide_routing",
        lambda contract_text, entities, model_key=None: _sample_routing(legal_focus=["deposit refund"]),
    )
    monkeypatch.setattr(review_graph, "rule_review_clauses", lambda contract_text: [_deposit_issue()])

    def fake_model_review(contract_text, routing=None, entities=None, model_key=None, **kwargs):
        time.sleep(0.05)
        return [
            _deposit_issue(level="critical", risk_level=5),
            _penalty_issue(),
        ]

    monkeypatch.setattr(review_graph, "model_review_clauses", fake_model_review)
    monkeypatch.setattr(
        review_graph,
        "generate_report",
        lambda contract_text, issues, model_key=None: ["## Review Report", "Two important risks were found."],
    )

    events = []
    async for event in review_graph.run_review_stream("contract text", "session-1", model_key="review"):
        events.append(event)

    event_names = [event["event"] for event in events]

    assert event_names[0] == "review_started"
    assert "initial_review_ready" in event_names
    assert "deep_review_started" in event_names
    assert "deep_review_update" in event_names
    assert event_names[-1] == "review_complete"

    initial_ready_index = event_names.index("initial_review_ready")
    deep_update_index = event_names.index("deep_review_update")
    assert initial_ready_index < deep_update_index

    deep_update_payload = next(event["data"] for event in events if event["event"] == "deep_review_update")
    assert any(change["change_type"] == "new" for change in deep_update_payload["changes"])
    assert any(change["change_type"] == "upgraded" for change in deep_update_payload["changes"])


@pytest.mark.asyncio
async def test_run_review_stream_keeps_initial_result_when_deep_stage_fails(monkeypatch):
    monkeypatch.setattr(review_graph, "get_settings", lambda: _build_settings())
    monkeypatch.setattr(review_graph, "extract_entities", lambda contract_text, model_key=None: _sample_entities())
    monkeypatch.setattr(
        review_graph,
        "decide_routing",
        lambda contract_text, entities, model_key=None: _sample_routing(),
    )
    monkeypatch.setattr(review_graph, "rule_review_clauses", lambda contract_text: [_deposit_issue()])

    def fail_model_review(*args, **kwargs):
        time.sleep(0.05)
        raise RuntimeError("model timeout")

    monkeypatch.setattr(review_graph, "model_review_clauses", fail_model_review)
    monkeypatch.setattr(
        review_graph,
        "generate_report",
        lambda contract_text, issues, model_key=None: ["## Review Report", "Initial result is preserved."],
    )

    events = []
    async for event in review_graph.run_review_stream("contract text", "session-2", model_key="review"):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert "initial_review_ready" in event_names
    assert "deep_review_failed" in event_names
    assert event_names[-1] == "review_complete"
    assert "error" not in event_names


@pytest.mark.asyncio
async def test_run_review_stream_stops_after_initial_stage_in_light_mode(monkeypatch):
    monkeypatch.setattr(review_graph, "get_settings", lambda: _build_settings())
    monkeypatch.setattr(review_graph, "extract_entities", lambda contract_text, model_key=None: _sample_entities())
    monkeypatch.setattr(
        review_graph,
        "decide_routing",
        lambda contract_text, entities, model_key=None: _sample_routing(),
    )
    monkeypatch.setattr(review_graph, "rule_review_clauses", lambda contract_text: [_deposit_issue()])
    monkeypatch.setattr(
        review_graph,
        "model_review_clauses",
        lambda *args, **kwargs: [_deposit_issue(level="critical", risk_level=5)],
    )
    monkeypatch.setattr(review_graph, "generate_report", lambda *args, **kwargs: ["should not be used"])

    events = []
    async for event in review_graph.run_review_stream(
        "contract text",
        "session-light-1",
        model_key="review",
        review_mode="light",
    ):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert "initial_review_ready" in event_names
    assert "deep_review_available" in event_names
    assert "deep_review_started" not in event_names
    assert "final_report" not in event_names
    assert event_names[-1] == "review_complete"


@pytest.mark.asyncio
async def test_run_deep_review_stream_resumes_from_initial_issues(monkeypatch):
    monkeypatch.setattr(review_graph, "get_settings", lambda: _build_settings(review_model_timeout_seconds=1.0))
    monkeypatch.setattr(review_graph, "extract_entities", lambda contract_text, model_key=None: _sample_entities())
    monkeypatch.setattr(
        review_graph,
        "decide_routing",
        lambda contract_text, entities, model_key=None: _sample_routing(legal_focus=["deposit refund"]),
    )
    monkeypatch.setattr(
        review_graph,
        "model_review_clauses",
        lambda *args, **kwargs: [
            _deposit_issue(level="critical", risk_level=5),
            _penalty_issue(),
        ],
    )
    monkeypatch.setattr(
        review_graph,
        "generate_report",
        lambda contract_text, issues, model_key=None: ["## Review Report", "Deep scan is complete."],
    )

    events = []
    async for event in review_graph.run_deep_review_stream(
        "contract text",
        "session-deep-1",
        issues=[_deposit_issue()],
        model_key="review",
    ):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert event_names[0] == "deep_review_started"
    assert "deep_review_update" in event_names
    assert "final_report" in event_names
    assert event_names[-1] == "review_complete"


@pytest.mark.asyncio
async def test_run_deep_review_stream_allows_retry_after_failure(monkeypatch):
    monkeypatch.setattr(review_graph, "get_settings", lambda: _build_settings(review_model_timeout_seconds=1.0))
    monkeypatch.setattr(review_graph, "extract_entities", lambda contract_text, model_key=None: _sample_entities())
    monkeypatch.setattr(
        review_graph,
        "decide_routing",
        lambda contract_text, entities, model_key=None: _sample_routing(),
    )

    def fail_model_review(*args, **kwargs):
        raise RuntimeError("model timeout")

    monkeypatch.setattr(review_graph, "model_review_clauses", fail_model_review)

    events = []
    async for event in review_graph.run_deep_review_stream(
        "contract text",
        "session-deep-2",
        issues=[_deposit_issue()],
        model_key="review",
    ):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert event_names[0] == "deep_review_started"
    assert "deep_review_failed" in event_names
    assert event_names[-1] == "review_complete"
