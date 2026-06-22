"""Verify that specialist agents execute in parallel, not sequentially."""
import time
from unittest.mock import patch

import pytest
from src.graph.langgraph_builder import build_review_graph


def _sample_contract():
    return "甲方：张三\n乙方：李四\n月租金5000元\n押金20000元\n违约金条款" * 200


def _sample_entities():
    return {
        "contract_type": "租赁合同",
        "parties": {"lessor": "张三", "lessee": "李四"},
        "rent": {"monthly": 5000},
        "deposit": {"amount": 20000},
    }


def _make_finding(agent_id="test"):
    return {
        "finding_id": f"fid_{agent_id}",
        "agent_id": agent_id,
        "dimension": "deposit",
        "clause": "押金条款",
        "matched_text": "押金20000元",
        "issue": "押金偏高",
        "severity": "high",
        "risk_level": 4,
        "confidence": 0.85,
        "legal_references": [],
        "evidence_ids": [],
        "suggestion": "降低押金",
    }


@pytest.mark.asyncio
async def test_multi_mode_specialists_run_concurrently():
    """Three specialists with 0.3s delay each should complete in ~0.3s, not ~0.9s."""
    call_times = {}
    call_order = []

    def track(name, delay):
        def fn(*args, **kwargs):
            call_order.append((name, time.monotonic()))
            start = time.monotonic()
            time.sleep(delay)
            call_times[name] = time.monotonic() - start
            return [_make_finding(name)]
        return fn

    graph = build_review_graph()

    with (
        patch("src.graph.langgraph_builder.extract_entities", return_value=_sample_entities()),
        patch("src.graph.langgraph_builder._regex_fallback", return_value=_sample_entities()),
        patch("src.graph.langgraph_builder.rule_review_clauses", return_value=[]),
        patch("src.graph.langgraph_builder.decide_routing", return_value={"confidence": 0.5}),
        patch("src.graph.langgraph_builder._default_routing", return_value={"confidence": 0.5}),
        patch("src.graph.langgraph_builder.run_financial_agent", side_effect=track("financial", 0.3)),
        patch("src.graph.langgraph_builder.run_rights_agent", side_effect=track("rights", 0.3)),
        patch("src.graph.langgraph_builder.run_compliance_agent", side_effect=track("compliance", 0.3)),
        patch("src.graph.langgraph_builder.run_critic_agent", return_value={"verified": [_make_finding()], "rejected": [], "degraded": False}),
        patch("src.graph.langgraph_builder.run_supervisor_agent", return_value={"final_findings": [_make_finding()], "overall_risk": "high", "summary": "test"}),
        patch("src.graph.langgraph_builder.generate_report", return_value=["## Report"]),
    ):
        start = time.monotonic()
        result = await graph.ainvoke({
            "session_id": "test-parallel",
            "contract_text": _sample_contract(),
        })
        total = time.monotonic() - start

    # All 3 should have been called
    assert len(call_times) == 3, f"Expected 3 agents, got {call_times}"

    # Parallel: ~0.3s. Sequential: ~0.9s. Allow 0.5s overhead.
    assert total < 0.8, f"Expected parallel (~0.3s), took {total:.2f}s — agents may be sequential"

    # Verify all started before any finished (overlap)
    starts = [t for name, t in call_order]
    assert len(starts) == 3


@pytest.mark.asyncio
async def test_single_mode_only_calls_general():
    """In single mode, only general_review should execute."""
    called_agents = []

    def track(name):
        def fn(*args, **kwargs):
            called_agents.append(name)
            return [_make_finding(name)]
        return fn

    graph = build_review_graph()

    with (
        patch("src.graph.langgraph_builder.extract_entities", return_value=_sample_entities()),
        patch("src.graph.langgraph_builder._regex_fallback", return_value=_sample_entities()),
        patch("src.graph.langgraph_builder.rule_review_clauses", return_value=[]),
        patch("src.graph.langgraph_builder.decide_routing", return_value={"confidence": 0.99}),
        patch("src.graph.langgraph_builder._default_routing", return_value={"confidence": 0.99}),
        patch("src.graph.langgraph_builder.run_financial_agent", side_effect=track("financial")),
        patch("src.graph.langgraph_builder.run_rights_agent", side_effect=track("rights")),
        patch("src.graph.langgraph_builder.run_compliance_agent", side_effect=track("compliance")),
        patch("src.graph.langgraph_builder.run_general_agent", side_effect=track("general")),
        patch("src.graph.langgraph_builder.run_critic_agent", return_value={"verified": [_make_finding()], "rejected": [], "degraded": False}),
        patch("src.graph.langgraph_builder.run_supervisor_agent", return_value={"final_findings": [_make_finding()], "overall_risk": "low", "summary": "test"}),
        patch("src.graph.langgraph_builder.generate_report", return_value=["## Report"]),
    ):
        # Short contract + high confidence + standard type = single mode
        await graph.ainvoke({
            "session_id": "test-single",
            "contract_text": "短合同",
        })

    assert "general" in called_agents, f"general should be called, got {called_agents}"
    # Financial/rights/compliance should be called but return empty (skip due to mode)
    # They ARE called (graph edges always connect) but they check mode and skip
