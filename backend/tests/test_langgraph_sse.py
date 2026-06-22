"""Tests for SSE adapter event ordering and compatibility."""
import pytest
from src.graph.sse_adapter import graph_to_sse_events, _sse_event, AGENT_ID_MAP


@pytest.mark.asyncio
async def test_sse_emits_required_events_in_order():
    """Verify all required SSE events are emitted in correct order."""
    async def mock_graph():
        yield {"entity_extraction": {"entities": {"contract_type": "租赁合同"}}}
        yield {"rule_scan": {"rule_issues": [{"clause": "test", "level": "low", "risk_level": 1, "issue": "test"}]}}
        yield {"retrieval": {"routing": {"confidence": 0.9}, "evidence": []}}
        yield {"collaboration_router": {"specialist_tasks": ["general_review"], "collaboration_mode": "single"}}
        yield {"general_review": {"candidate_findings": []}}
        yield {"prepare_candidates": {"candidate_findings": [], "used_rule_fallback": False}}
        yield {"critic": {"verified_findings": [], "rejected_findings": []}}
        yield {"supervisor": {"final_findings": [], "overall_risk": "low", "supervisor_summary": "test"}}
        yield {"report_generation": {"report_paragraphs": ["## Report"]}}
        yield {"persist_result": {"completed": True, "persisted": True}}

    events = []
    async for event in graph_to_sse_events(mock_graph(), "test-session"):
        events.append(event)

    event_names = [e["event"] for e in events]

    assert event_names[0] == "review_started"
    assert "entity_extraction" in event_names
    assert "routing" in event_names
    assert "logic_review" in event_names
    assert "initial_review_ready" in event_names
    assert "deep_review_started" in event_names
    assert "deep_review_update" in event_names
    assert "final_report" in event_names
    assert "deep_review_complete" in event_names
    assert event_names[-1] == "review_complete"

    # Verify ordering
    idx = {name: event_names.index(name) for name in set(event_names)}
    assert idx["entity_extraction"] < idx["routing"]
    assert idx["routing"] < idx["initial_review_ready"]
    assert idx["initial_review_ready"] < idx["deep_review_started"]
    assert idx["deep_review_started"] < idx["deep_review_update"]
    assert idx["deep_review_update"] < idx["final_report"]
    assert idx["final_report"] < idx["deep_review_complete"]


@pytest.mark.asyncio
async def test_sse_agent_id_mapping():
    """Verify agent IDs are correctly mapped."""
    async def mock_graph():
        yield {"collaboration_router": {"specialist_tasks": ["financial_performance", "rights_remedies", "compliance_evidence"], "collaboration_mode": "multi"}}
        yield {"financial_specialist": {"candidate_findings": [], "degraded_agents": []}}
        yield {"rights_specialist": {"candidate_findings": [], "degraded_agents": []}}
        yield {"compliance_specialist": {"candidate_findings": [], "degraded_agents": []}}
        yield {"prepare_candidates": {"candidate_findings": [], "used_rule_fallback": False}}
        yield {"critic": {"verified_findings": [], "rejected_findings": []}}
        yield {"supervisor": {"final_findings": [], "overall_risk": "low"}}
        yield {"report_generation": {"report_paragraphs": []}}
        yield {"persist_result": {"completed": True}}

    events = []
    async for event in graph_to_sse_events(mock_graph(), "test"):
        events.append(event)

    progress_events = [e for e in events if e["event"] == "agent_progress"]
    agent_ids = [e["data"]["agent_id"] for e in progress_events]

    assert "financial_performance" in agent_ids
    assert "rights_remedies" in agent_ids
    assert "compliance_evidence" in agent_ids
    # Should NOT have "financial", "rights", "compliance" without suffix
    assert "financial" not in agent_ids


@pytest.mark.asyncio
async def test_sse_persisted_flag():
    """review_complete should include persisted flag."""
    async def mock_graph():
        yield {"persist_result": {"completed": True, "persisted": True}}

    events = []
    async for event in graph_to_sse_events(mock_graph(), "test"):
        events.append(event)

    complete = [e for e in events if e["event"] == "review_complete"]
    assert len(complete) == 1
    assert complete[0]["data"].get("persisted") is True


@pytest.mark.asyncio
async def test_sse_uses_final_findings_not_initial():
    """deep_review_complete.issues must be final_findings, not initial candidates."""
    async def mock_graph():
        yield {"critic": {"verified_findings": [{"finding_id": "verified_1"}], "rejected_findings": []}}
        yield {"supervisor": {"final_findings": [{"finding_id": "final_1"}], "overall_risk": "high"}}
        yield {"report_generation": {"report_paragraphs": []}}
        yield {"persist_result": {"completed": True}}

    events = []
    async for event in graph_to_sse_events(mock_graph(), "test"):
        events.append(event)

    deep_complete = [e for e in events if e["event"] == "deep_review_complete"]
    assert len(deep_complete) == 1
    issues = deep_complete[0]["data"].get("issues", [])
    # Should contain final findings, not initial
    issue_ids = {f.get("finding_id") for f in issues}
    assert "final_1" in issue_ids


def test_sse_event_format():
    event = _sse_event("test", {"key": "value"})
    assert event["event"] == "test"
    assert event["data"] == {"key": "value"}
    assert "event: test" in event["_raw"]
    assert '"key"' in event["_raw"]
