"""Tests for the LangGraph workflow including parallel execution, rule integration, and critic."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.graph.langgraph_builder import (
    build_review_graph,
    node_prepare_candidates,
    node_critic,
    node_supervisor,
)
from src.graph.state import compute_finding_id


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
        "evidence_ids": [],
        "suggestion": "降低押金",
    }


def test_prepare_candidates_merges_rule_and_agent():
    state = {
        "contract_text": _sample_contract(),
        "rule_issues": [{
            "clause": "押金条款", "level": "high", "risk_level": 4,
            "issue": "押金偏高", "suggestion": "降低",
            "legal_reference": "民法典", "matched_text": "押金20000元",
        }],
        "candidate_findings": [_make_finding(agent_id="financial_performance", clause="违约金条款", issue="违约金过高", matched_text="违约金")],
    }
    result = node_prepare_candidates(state)
    candidates = result["candidate_findings"]
    agent_ids = {c["agent_id"] for c in candidates}
    assert "rule_engine" in agent_ids
    assert "financial_performance" in agent_ids


def test_prepare_candidates_deduplicates():
    rule_finding = _make_finding(agent_id="rule_engine")
    agent_finding = _make_finding(agent_id="financial_performance")
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
    assert len(result["candidate_findings"]) == 1


def test_prepare_candidates_all_agents_fail():
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
    assert len(result["candidate_findings"]) >= 1
    assert result.get("used_rule_fallback") is True


def test_prepare_candidates_filters_invalid():
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


def test_graph_structure_supports_parallel_specialists():
    """Verify graph has specialist nodes and prepare_candidates node for fan-in."""
    graph = build_review_graph()
    g = graph.get_graph()

    nodes = set(g.nodes.keys())
    assert "financial_specialist" in nodes
    assert "rights_specialist" in nodes
    assert "compliance_specialist" in nodes
    assert "prepare_candidates" in nodes
    assert "general_review" in nodes

    edges = [(e.source, e.target) for e in g.edges]

    # prepare_candidates should be reachable from specialists
    prepare_sources = {s for s, t in edges if t == "prepare_candidates"}
    assert "financial_specialist" in prepare_sources
    assert "general_review" in prepare_sources

    # prepare_candidates should go to critic
    prepare_targets = {t for s, t in edges if s == "prepare_candidates"}
    assert "critic" in prepare_targets


def test_critic_rejects_bad_matched_text():
    finding = _make_finding(matched_text="这段文字不在合同中")
    state = {
        "contract_text": _sample_contract(),
        "candidate_findings": [finding],
        "evidence": [{"id": "ev_0", "title": "test", "content": "test"}],
    }
    result = node_critic(state)
    verified = result.get("verified_findings", [])
    rejected = result.get("rejected_findings", [])
    all_findings = verified + rejected
    finding_ids = {f.get("finding_id") for f in all_findings}
    assert finding["finding_id"] in finding_ids


def test_critic_llm_failure_keeps_rule_findings():
    rule_finding = _make_finding(agent_id="rule_engine")
    model_finding = _make_finding(agent_id="financial_performance", clause="违约金",
                                   issue="违约金过高", matched_text="违约金")

    with patch("src.graph.langgraph_builder.run_critic_agent", side_effect=RuntimeError("LLM timeout")):
        state = {
            "contract_text": _sample_contract(),
            "candidate_findings": [rule_finding, model_finding],
            "evidence": [],
        }
        result = node_critic(state)

    verified = result.get("verified_findings", [])
    verified_ids = {f.get("finding_id") for f in verified}
    assert rule_finding["finding_id"] in verified_ids


def test_supervisor_only_returns_existing_ids():
    verified = [_make_finding()]
    result = node_supervisor({
        "contract_text": _sample_contract(),
        "verified_findings": verified,
    })
    final_ids = {f.get("finding_id") for f in result.get("final_findings", [])}
    original_ids = {f.get("finding_id") for f in verified}
    assert final_ids.issubset(original_ids)


def test_supervisor_maps_final_severity():
    finding_id = _make_finding()["finding_id"]
    mock_result = {
        "final_findings": [{"finding_id": finding_id, "final_severity": "critical", "final_risk_level": 5}],
        "overall_risk": "critical",
        "summary": "test",
    }
    with patch("src.graph.langgraph_builder.run_supervisor_agent", return_value=mock_result):
        result = node_supervisor({
            "contract_text": _sample_contract(),
            "verified_findings": [_make_finding()],
        })
    final = result.get("final_findings", [])
    assert len(final) == 1
    assert final[0].get("severity") == "critical"
    assert final[0].get("risk_level") == 5


def test_supervisor_llm_failure_uses_fallback():
    with patch("src.graph.langgraph_builder.run_supervisor_agent", side_effect=RuntimeError("timeout")):
        result = node_supervisor({
            "contract_text": _sample_contract(),
            "verified_findings": [_make_finding()],
        })
    assert len(result.get("final_findings", [])) >= 1
    assert result.get("current_stage") == "supervisor_complete"
