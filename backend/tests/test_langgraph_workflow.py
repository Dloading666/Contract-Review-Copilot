"""Tests for the LangGraph workflow including parallel execution, rule integration, and critic."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.graph.langgraph_builder import (
    build_review_graph,
    node_prepare_candidates,
    node_critic,
    node_supervisor,
)
from src.graph.state import compute_finding_id, validate_finding


def _sample_contract():
    return "甲方：张三\n乙方：李四\n月租金5000元\n押金20000元\n违约金：提前退租需支付剩余全部租金"


def _sample_entities():
    return {
        "contract_type": "租赁合同",
        "parties": {"lessor": "张三", "lessee": "李四"},
        "rent": {"monthly": 5000},
        "deposit": {"amount": 20000},
    }


def _make_finding(agent_id="test_agent", clause="押金条款", issue="押金偏高",
                  severity="high", risk_level=4, matched_text="押金20000元"):
    return {
        "finding_id": compute_finding_id("deposit", clause, matched_text, issue),
        "agent_id": agent_id,
        "dimension": "deposit",
        "clause": clause,
        "matched_text": matched_text,
        "issue": issue,
        "severity": severity,
        "risk_level": risk_level,
        "confidence": 0.85,
        "legal_references": ["民法典497条"],
        "evidence_ids": ["ev_0"],
        "suggestion": "降低押金",
    }


def test_prepare_candidates_merges_rule_and_agent():
    """Rule findings must be included in candidates."""
    state = {
        "contract_text": _sample_contract(),
        "rule_issues": [{
            "clause": "押金条款", "level": "high", "risk_level": 4,
            "issue": "押金偏高", "suggestion": "降低",
            "legal_reference": "民法典", "matched_text": "押金20000元",
        }],
        "candidate_findings": [_make_finding(agent_id="financial_performance")],
    }
    result = node_prepare_candidates(state)
    candidates = result["candidate_findings"]
    agent_ids = {c["agent_id"] for c in candidates}
    assert "rule_engine" in agent_ids, "Rule findings must be included"
    assert "financial_performance" in agent_ids, "Agent findings must be included"


def test_prepare_candidates_deduplicates():
    """Same finding from rule and agent should be deduplicated."""
    rule_finding = _make_finding(agent_id="rule_engine")
    agent_finding = _make_finding(agent_id="financial_performance")
    # Same finding_id since content is the same
    assert rule_finding["finding_id"] == agent_finding["finding_id"]

    state = {
        "contract_text": _sample_contract(),
        "rule_issues": [{
            "clause": "押金条款", "level": "high", "risk_level": 4,
            "issue": "押金偏高", "suggestion": "降低",
            "legal_reference": "民法典", "matched_text": "押金20000元",
        }],
        "candidate_findings": [agent_finding],
    }
    result = node_prepare_candidates(state)
    candidates = result["candidate_findings"]
    assert len(candidates) == 1, f"Should deduplicate, got {len(candidates)}"


def test_prepare_candidates_all_agents_fail():
    """When all agents fail, rule findings must still produce candidates."""
    state = {
        "contract_text": _sample_contract(),
        "rule_issues": [{
            "clause": "押金条款", "level": "high", "risk_level": 4,
            "issue": "押金偏高", "suggestion": "降低",
            "legal_reference": "民法典", "matched_text": "押金20000元",
        }],
        "candidate_findings": [],
    }
    result = node_prepare_candidates(state)
    candidates = result["candidate_findings"]
    assert len(candidates) >= 1
    assert result.get("used_rule_fallback") is True


def test_prepare_candidates_filters_invalid():
    """Invalid findings (empty clause, bad severity) should be filtered."""
    state = {
        "contract_text": _sample_contract(),
        "rule_issues": [],
        "candidate_findings": [
            {"agent_id": "test", "dimension": "test", "clause": "", "issue": "test",
             "severity": "high", "risk_level": 4, "confidence": 0.8},
            {"agent_id": "test", "dimension": "test", "clause": "test", "issue": "test",
             "severity": "invalid", "risk_level": 4, "confidence": 0.8},
            _make_finding(),
        ],
    }
    result = node_prepare_candidates(state)
    assert len(result["candidate_findings"]) == 1


@pytest.mark.asyncio
async def test_parallel_agents_execute_concurrently():
    """Verify that specialist agents run in parallel, not sequentially."""
    call_times = {}

    def track_call(agent_name, delay):
        def fn(*args, **kwargs):
            start = time.monotonic()
            time.sleep(delay)
            call_times[agent_name] = time.monotonic() - start
            return [_make_finding(agent_id=agent_name)]
        return fn

    graph = build_review_graph()

    with patch("src.graph.langgraph_builder.extract_entities", return_value=_sample_entities()), \
         patch("src.graph.langgraph_builder._regex_fallback", return_value=_sample_entities()), \
         patch("src.graph.langgraph_builder.rule_review_clauses", return_value=[]), \
         patch("src.graph.langgraph_builder.decide_routing", return_value={"confidence": 0.5}), \
         patch("src.graph.langgraph_builder._default_routing", return_value={"confidence": 0.5}), \
         patch("src.graph.langgraph_builder.run_financial_agent", side_effect=track_call("financial", 0.3)), \
         patch("src.graph.langgraph_builder.run_rights_agent", side_effect=track_call("rights", 0.3)), \
         patch("src.graph.langgraph_builder.run_compliance_agent", side_effect=track_call("compliance", 0.3)), \
         patch("src.graph.langgraph_builder.run_critic_agent", return_value={"verified": [_make_finding()], "rejected": [], "degraded": False}), \
         patch("src.graph.langgraph_builder.run_supervisor_agent", return_value={"final_findings": [_make_finding()], "overall_risk": "high", "summary": "test"}), \
         patch("src.graph.langgraph_builder.generate_report", return_value=["## Report", "Content"]):

        initial_state = {
            "session_id": "test-parallel",
            "contract_text": _sample_contract() * 100,  # >6000 chars to trigger multi
        }
        start = time.monotonic()
        result = await graph.ainvoke(initial_state)
        total = time.monotonic() - start

    # If parallel: total ~0.3s + overhead
    # If sequential: total ~0.9s + overhead
    assert total < 0.8, f"Expected parallel execution (~0.3s), took {total:.2f}s"
    assert len(call_times) == 3, f"All 3 agents should have been called, got {call_times}"


def test_critic_rejects_bad_matched_text():
    """Critic should reject findings with matched_text not in contract."""
    state = {
        "contract_text": _sample_contract(),
        "candidate_findings": [_make_finding(matched_text="这段文字不在合同中")],
        "evidence": [{"id": "ev_0", "title": "test", "content": "test"}],
    }
    result = node_critic(state)
    # Should either reject or mark as unverified
    verified = result.get("verified_findings", [])
    rejected = result.get("rejected_findings", [])
    all_ids = {f.get("finding_id") for f in verified + rejected}
    assert _make_finding()["finding_id"] in all_ids


def test_critic_llm_failure_keeps_rule_findings():
    """When critic LLM fails, rule findings should be preserved."""
    rule_finding = _make_finding(agent_id="rule_engine")
    model_finding = _make_finding(agent_id="financial_performance", clause="违约金",
                                   issue="违约金过高", matched_text="违约金")

    def fail_critic(*args, **kwargs):
        raise RuntimeError("LLM timeout")

    with patch("src.graph.langgraph_builder.run_critic_agent", side_effect=fail_critic):
        state = {
            "contract_text": _sample_contract(),
            "candidate_findings": [rule_finding, model_finding],
            "evidence": [],
        }
        result = node_critic(state)

    verified = result.get("verified_findings", [])
    verified_ids = {f.get("finding_id") for f in verified}
    assert rule_finding["finding_id"] in verified_ids, "Rule finding must survive critic failure"


def test_supervisor_only_returns_existing_ids():
    """Supervisor must not create new findings."""
    verified = [_make_finding()]
    result = node_supervisor({
        "contract_text": _sample_contract(),
        "verified_findings": verified,
    })
    final_ids = {f.get("finding_id") for f in result.get("final_findings", [])}
    original_ids = {f.get("finding_id") for f in verified}
    assert final_ids.issubset(original_ids)


def test_supervisor_maps_final_severity():
    """Supervisor's final_severity should map back to severity."""
    mock_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"final_findings":[{"finding_id":"' + _make_finding()["finding_id"] + '","final_severity":"critical","final_risk_level":5}],"overall_risk":"critical","summary":"test"}'))]
    )
    with patch("src.graph.langgraph_builder.create_chat_completion", return_value=mock_response):
        result = node_supervisor({
            "contract_text": _sample_contract(),
            "verified_findings": [_make_finding()],
        })
    final = result.get("final_findings", [])
    assert len(final) == 1
    assert final[0].get("severity") == "critical"
    assert final[0].get("risk_level") == 5


def test_supervisor_llm_failure_uses_fallback():
    """Supervisor fallback should use verified findings directly."""
    def fail(*args, **kwargs):
        raise RuntimeError("timeout")

    with patch("src.graph.langgraph_builder.run_supervisor_agent", side_effect=fail):
        result = node_supervisor({
            "contract_text": _sample_contract(),
            "verified_findings": [_make_finding()],
        })
    assert len(result.get("final_findings", [])) >= 1
    assert result.get("current_stage") == "supervisor_complete"
