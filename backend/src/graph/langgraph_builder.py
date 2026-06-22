from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import os
import time
from typing import Literal

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from ..agents.entity_extraction import extract_entities, _regex_fallback
from ..agents.routing import decide_routing, _default_routing
from ..agents.logic_review import rule_review_clauses
from ..agents.financial_performance import run_financial_agent
from ..agents.rights_remedies import run_rights_agent
from ..agents.compliance_evidence import run_compliance_agent
from ..agents.general_review import run_general_agent
from ..agents.critic import run_critic_agent
from ..agents.supervisor import run_supervisor_agent
from ..agents.aggregation import generate_report
from .state import ReviewState, compute_finding_id, validate_finding

VALID_MODES = ("single", "auto", "multi")


def _validate_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid REVIEW_COLLABORATION_MODE={mode!r}. Must be one of {VALID_MODES}"
        )
    return mode


def decide_collaboration_mode(
    rule_issues: list[dict],
    contract_text: str,
    entities: dict,
    routing: dict,
    mode_override: str | None = None,
) -> Literal["single", "multi"]:
    settings = get_settings()
    mode = _validate_mode(mode_override or settings.review_collaboration_mode)

    if mode == "single":
        return "single"
    if mode == "multi":
        return "multi"

    # auto mode
    min_chars = settings.review_multi_agent_min_chars
    confidence_threshold = settings.review_multi_agent_confidence_threshold

    if len(contract_text) >= min_chars:
        return "multi"

    has_significant_risk = any(
        i.get("risk_level", 0) >= 3 for i in rule_issues
    )
    if has_significant_risk:
        return "multi"

    confidence = routing.get("confidence", 1.0)
    if confidence < confidence_threshold:
        return "multi"

    contract_type = entities.get("contract_type", "")
    if contract_type not in ("租赁合同", "住宅租赁", "商业租赁", ""):
        return "multi"

    return "single"


# --- Node functions ---

def node_entity_extraction(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    contract_text = state["contract_text"]
    model_key = state.get("model_key")
    try:
        entities = extract_entities(contract_text, model_key)
    except Exception:
        entities = _regex_fallback(contract_text)
    return {"entities": entities}


def node_prepare_inputs(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    """Run rule scan and retrieval together (single node = natural barrier)."""
    contract_text = state["contract_text"]
    entities = state.get("entities", {})
    model_key = state.get("model_key")

    rule_issues = rule_review_clauses(contract_text)

    try:
        routing = decide_routing(contract_text, entities, model_key)
    except Exception:
        routing = _default_routing(contract_text, entities)

    evidence = []
    pgvector_results = routing.get("pgvector_results", [])
    if pgvector_results:
        evidence = [
            {
                "id": f"ev_{i}",
                "title": chunk.get("metadata", {}).get("title", "法律条款"),
                "content": chunk.get("chunk_text", ""),
                "score": float(chunk.get("similarity", 0)),
            }
            for i, chunk in enumerate(pgvector_results)
        ]

    return {"rule_issues": rule_issues, "routing": routing, "evidence": evidence}


def node_collaboration_router(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    settings = get_settings()
    mode = decide_collaboration_mode(
        rule_issues=state.get("rule_issues", []),
        contract_text=state["contract_text"],
        entities=state.get("entities", {}),
        routing=state.get("routing", {}),
        mode_override=settings.review_collaboration_mode,
    )
    if mode == "multi":
        return {
            "collaboration_mode": "multi",
            "specialist_tasks": ["financial_performance", "rights_remedies", "compliance_evidence"],
        }
    return {
        "collaboration_mode": "single",
        "specialist_tasks": ["general_review"],
    }


def node_financial_specialist(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    if state.get("collaboration_mode") != "multi":
        return {}
    try:
        findings = run_financial_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        logger.exception("[Graph] Financial agent failed: %s", exc)
        return {"candidate_findings": [], "degraded_agents": ["financial_performance"]}


def node_rights_specialist(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    if state.get("collaboration_mode") != "multi":
        return {}
    try:
        findings = run_rights_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        logger.exception("[Graph] Rights agent failed: %s", exc)
        return {"candidate_findings": [], "degraded_agents": ["rights_remedies"]}


def node_compliance_specialist(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    if state.get("collaboration_mode") != "multi":
        return {}
    try:
        findings = run_compliance_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        logger.exception("[Graph] Compliance agent failed: %s", exc)
        return {"candidate_findings": [], "degraded_agents": ["compliance_evidence"]}


def node_general_review(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    if state.get("collaboration_mode") == "multi":
        return {}
    try:
        findings = run_general_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        logger.exception("[Graph] General agent failed: %s", exc)
        return {"candidate_findings": [], "degraded_agents": ["general_review"]}


def node_prepare_candidates(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    """Merge rule findings with agent findings, deduplicate by stable ID."""
    rule_issues = state.get("rule_issues", [])
    agent_findings = state.get("candidate_findings", [])

    # Convert rule issues to FindingCandidate dicts
    rule_findings = []
    for issue in rule_issues:
        if not isinstance(issue, dict):
            continue
        severity = issue.get("level") or issue.get("severity") or "medium"
        risk_level = int(issue.get("risk_level", 3))
        matched_text = issue.get("matched_text", "")
        clause = issue.get("clause", "未知条款")
        issue_text = issue.get("issue", "")
        finding_id = compute_finding_id("general", clause, matched_text, issue_text)
        rule_findings.append({
            "finding_id": finding_id,
            "agent_id": "rule_engine",
            "dimension": "general",
            "clause": clause,
            "matched_text": matched_text,
            "issue": issue_text,
            "severity": severity,
            "risk_level": risk_level,
            "confidence": 0.9,
            "legal_references": [issue.get("legal_reference", "")],
            "evidence_ids": [],
            "suggestion": issue.get("suggestion", ""),
        })

    # Merge and deduplicate by finding_id
    all_candidates = rule_findings + agent_findings
    seen_ids: dict[str, dict] = {}
    for f in all_candidates:
        if not validate_finding(f):
            continue
        fid = f.get("finding_id", "")
        if not fid:
            fid = compute_finding_id(
                f.get("dimension", "general"),
                f.get("clause", ""),
                f.get("matched_text", ""),
                f.get("issue", ""),
            )
            f["finding_id"] = fid
        if fid not in seen_ids:
            seen_ids[fid] = f

    deduplicated = list(seen_ids.values())

    has_rule_fallback = bool(rule_findings) and not agent_findings
    return {
        "candidate_findings": deduplicated,
        "used_rule_fallback": has_rule_fallback,
    }


def node_critic(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    candidates = state.get("candidate_findings", [])
    if not candidates:
        return {"verified_findings": [], "rejected_findings": []}
    try:
        result = run_critic_agent(
            state["contract_text"],
            candidates,
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {
            "verified_findings": result["verified"],
            "rejected_findings": result["rejected"],
        }
    except Exception as exc:
        logger.exception("[Graph] Critic failed: %s", exc)
        verified = []
        for f in candidates:
            if f.get("agent_id") == "rule_engine":
                verified.append(f)
            elif validate_finding(f) and _text_in_contract(f.get("matched_text", ""), state.get("contract_text", "")):
                capped = dict(f)
                if capped.get("risk_level", 3) > 3:
                    capped["risk_level"] = 3
                    capped["severity"] = "medium"
                capped["unverified"] = True
                verified.append(capped)
        return {"verified_findings": verified, "rejected_findings": []}


def _text_in_contract(matched_text: str, contract_text: str) -> bool:
    if not matched_text or not contract_text:
        return False
    import re
    norm_mt = re.sub(r"\s+", "", matched_text)
    norm_ct = re.sub(r"\s+", "", contract_text)
    return norm_mt in norm_ct


def node_supervisor(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    verified = state.get("verified_findings", [])
    try:
        result = run_supervisor_agent(
            state["contract_text"],
            verified,
            state.get("model_key"),
        )
        final = []
        finding_map = {f["finding_id"]: f for f in verified if "finding_id" in f}
        for ff in result.get("final_findings", []):
            fid = ff.get("finding_id", "")
            original = finding_map.get(fid)
            if not original:
                continue
            merged = dict(original)
            if "final_severity" in ff:
                sv = ff["final_severity"]
                if sv in ("critical", "high", "medium", "low"):
                    merged["severity"] = sv
            if "final_risk_level" in ff:
                rl = ff["final_risk_level"]
                if isinstance(rl, int) and 1 <= rl <= 5:
                    merged["risk_level"] = rl
            if "summary" in ff:
                merged["supervisor_summary"] = ff["summary"]
            final.append(merged)

        return {
            "final_findings": final if final else verified,
            "overall_risk": result.get("overall_risk", "medium"),
            "supervisor_summary": result.get("summary", "审查完成"),
            "current_stage": "supervisor_complete",
        }
    except Exception as exc:
        logger.exception("[Graph] Supervisor failed: %s", exc)
        return _fallback_supervisor(verified)


def _fallback_supervisor(findings: list[dict]) -> dict:
    max_risk = max((f.get("risk_level", 0) for f in findings), default=0)
    if max_risk >= 5:
        overall = "critical"
    elif max_risk >= 4:
        overall = "high"
    elif max_risk >= 3:
        overall = "medium"
    else:
        overall = "low"
    return {
        "final_findings": findings,
        "overall_risk": overall,
        "supervisor_summary": f"审查完成，共发现 {len(findings)} 条风险。",
        "current_stage": "supervisor_complete",
    }


def node_report_generation(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    final_findings = state.get("final_findings", [])
    try:
        paragraphs = generate_report(
            state["contract_text"],
            final_findings,
            state.get("model_key"),
        )
        return {"report_paragraphs": paragraphs, "current_stage": "report_complete"}
    except Exception as exc:
        logger.exception("[Graph] Report generation failed: %s", exc)
        return {"report_paragraphs": ["报告生成失败，请重试。"], "current_stage": "report_complete"}


def node_persist_result(state: ReviewState) -> dict:
    _t0 = time.monotonic()
    """Section 3: Real business persistence."""
    user_id = state.get("user_id")
    session_id = state.get("session_id", "")
    final_findings = state.get("final_findings", [])
    report_paragraphs = state.get("report_paragraphs", [])

    if not user_id:
        logger.warning("[Persist] No user_id, skipping persistence")
        return {"completed": True, "persisted": False, "current_stage": "complete"}

    try:
        from ..services import sync_store
        sync_store.save_review_result(
            user_id=user_id,
            session_id=session_id,
            filename=state.get("filename", ""),
            contract_text=state.get("contract_text", ""),
            issues=final_findings,
            report_paragraphs=report_paragraphs,
            status="complete",
            review_stage="complete",
        )
        return {"completed": True, "persisted": True, "current_stage": "complete"}
    except Exception as exc:
        logger.exception("[Persist] Failed to save: %s", exc)
        raise


# --- Graph builder ---

def build_review_graph(checkpointer=None):
    graph = StateGraph(ReviewState)

    graph.add_node("entity_extraction", node_entity_extraction)
    graph.add_node("prepare_inputs", node_prepare_inputs)
    graph.add_node("collaboration_router", node_collaboration_router)
    graph.add_node("financial_specialist", node_financial_specialist)
    graph.add_node("rights_specialist", node_rights_specialist)
    graph.add_node("compliance_specialist", node_compliance_specialist)
    graph.add_node("general_review", node_general_review)
    graph.add_node("prepare_candidates", node_prepare_candidates)
    graph.add_node("critic", node_critic)
    graph.add_node("supervisor", node_supervisor)
    graph.add_node("report_generation", node_report_generation)
    graph.add_node("persist_result", node_persist_result)

    # START: entity_extraction and prepare_inputs in parallel
    graph.add_edge(START, "entity_extraction")
    graph.add_edge(START, "prepare_inputs")

    # Both feed into collaboration_router
    graph.add_edge("entity_extraction", "collaboration_router")
    graph.add_edge("prepare_inputs", "collaboration_router")
    graph.add_edge("collaboration_router", "financial_specialist")
    graph.add_edge("collaboration_router", "rights_specialist")
    graph.add_edge("collaboration_router", "compliance_specialist")
    graph.add_edge("collaboration_router", "general_review")

    # All converge to prepare_candidates (fan-in)
    graph.add_edge("financial_specialist", "prepare_candidates")
    graph.add_edge("rights_specialist", "prepare_candidates")
    graph.add_edge("compliance_specialist", "prepare_candidates")
    graph.add_edge("general_review", "prepare_candidates")

    # Linear tail
    graph.add_edge("prepare_candidates", "critic")
    graph.add_edge("critic", "supervisor")
    graph.add_edge("supervisor", "report_generation")
    graph.add_edge("report_generation", "persist_result")
    graph.add_edge("persist_result", END)

    return graph.compile(checkpointer=checkpointer)
