from __future__ import annotations

import os
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
from .state import ReviewState


def decide_collaboration_mode(
    rule_issues: list[dict],
    contract_text: str,
    routing: dict,
    mode_override: str | None = None,
) -> Literal["single", "multi"]:
    settings = get_settings()
    mode = mode_override or settings.review_collaboration_mode

    if mode == "single":
        return "single"
    if mode == "multi":
        return "multi"

    min_chars = settings.review_multi_agent_min_chars
    confidence_threshold = settings.review_multi_agent_confidence_threshold

    if len(contract_text) > min_chars:
        return "multi"

    has_significant_risk = any(
        i.get("risk_level", 0) >= 3 for i in rule_issues
    )
    if has_significant_risk:
        return "multi"

    confidence = routing.get("confidence", 1.0)
    if confidence < confidence_threshold:
        return "multi"

    contract_type = routing.get("contract_type", "")
    if contract_type not in ("租赁合同", "住宅租赁", "商业租赁", ""):
        return "multi"

    return "single"


# --- Node functions ---

def node_entity_extraction(state: ReviewState) -> dict:
    contract_text = state["contract_text"]
    model_key = state.get("model_key")
    try:
        entities = extract_entities(contract_text, model_key)
    except Exception:
        entities = _regex_fallback(contract_text)
    return {"entities": entities}


def node_rule_scan(state: ReviewState) -> dict:
    contract_text = state["contract_text"]
    rule_issues = rule_review_clauses(contract_text)
    return {"rule_issues": rule_issues}


def node_retrieval(state: ReviewState) -> dict:
    contract_text = state["contract_text"]
    entities = state.get("entities", {})
    model_key = state.get("model_key")
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

    return {"routing": routing, "evidence": evidence}


def node_collaboration_router(state: ReviewState) -> dict:
    settings = get_settings()
    mode = decide_collaboration_mode(
        rule_issues=state.get("rule_issues", []),
        contract_text=state["contract_text"],
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
    try:
        findings = run_financial_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        print(f"[Graph] Financial agent failed: {exc}", flush=True)
        return {"candidate_findings": [], "degraded_agents": ["financial_performance"]}


def node_rights_specialist(state: ReviewState) -> dict:
    try:
        findings = run_rights_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        print(f"[Graph] Rights agent failed: {exc}", flush=True)
        return {"candidate_findings": [], "degraded_agents": ["rights_remedies"]}


def node_compliance_specialist(state: ReviewState) -> dict:
    try:
        findings = run_compliance_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        print(f"[Graph] Compliance agent failed: {exc}", flush=True)
        return {"candidate_findings": [], "degraded_agents": ["compliance_evidence"]}


def node_general_review(state: ReviewState) -> dict:
    try:
        findings = run_general_agent(
            state["contract_text"],
            state.get("entities", {}),
            state.get("evidence", []),
            state.get("model_key"),
        )
        return {"candidate_findings": findings}
    except Exception as exc:
        print(f"[Graph] General agent failed: {exc}", flush=True)
        return {"candidate_findings": [], "degraded_agents": ["general_review"]}


def node_critic(state: ReviewState) -> dict:
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
        print(f"[Graph] Critic failed, passing all findings through: {exc}", flush=True)
        return {"verified_findings": candidates, "rejected_findings": []}


def node_supervisor(state: ReviewState) -> dict:
    verified = state.get("verified_findings", [])
    try:
        result = run_supervisor_agent(
            state["contract_text"],
            verified,
            state.get("model_key"),
        )
        return {
            "final_findings": result["final_findings"],
            "current_stage": "supervisor_complete",
        }
    except Exception as exc:
        print(f"[Graph] Supervisor failed: {exc}", flush=True)
        return {"final_findings": verified, "current_stage": "supervisor_complete"}


def node_report_generation(state: ReviewState) -> dict:
    final_findings = state.get("final_findings", []) or state.get("verified_findings", [])
    try:
        paragraphs = generate_report(
            state["contract_text"],
            final_findings,
            state.get("model_key"),
        )
        return {"report_paragraphs": paragraphs, "current_stage": "report_complete"}
    except Exception as exc:
        print(f"[Graph] Report generation failed: {exc}", flush=True)
        return {"report_paragraphs": ["报告生成失败，请重试。"], "current_stage": "report_complete"}


def node_persist_result(state: ReviewState) -> dict:
    return {"completed": True, "current_stage": "complete"}


# --- Conditional edges ---

def route_after_collaboration_router(state: ReviewState) -> str:
    if state.get("collaboration_mode") == "multi":
        return "financial_specialist"
    return "general_review"


def route_after_financial(state: ReviewState) -> str:
    if state.get("collaboration_mode") == "multi":
        return "rights_specialist"
    return "critic"


def route_after_rights(state: ReviewState) -> str:
    if state.get("collaboration_mode") == "multi":
        return "compliance_specialist"
    return "critic"


# --- Graph builder ---

def build_review_graph(checkpointer=None):
    graph = StateGraph(ReviewState)

    graph.add_node("entity_extraction", node_entity_extraction)
    graph.add_node("rule_scan", node_rule_scan)
    graph.add_node("retrieval", node_retrieval)
    graph.add_node("collaboration_router", node_collaboration_router)
    graph.add_node("financial_specialist", node_financial_specialist)
    graph.add_node("rights_specialist", node_rights_specialist)
    graph.add_node("compliance_specialist", node_compliance_specialist)
    graph.add_node("general_review", node_general_review)
    graph.add_node("critic", node_critic)
    graph.add_node("supervisor", node_supervisor)
    graph.add_node("report_generation", node_report_generation)
    graph.add_node("persist_result", node_persist_result)

    # START edges: entity_extraction and rule_scan run in parallel
    graph.add_edge(START, "entity_extraction")
    graph.add_edge(START, "rule_scan")

    # entity_extraction feeds retrieval
    graph.add_edge("entity_extraction", "retrieval")

    # Both rule_scan and retrieval must complete before routing
    graph.add_edge("rule_scan", "collaboration_router")
    graph.add_edge("retrieval", "collaboration_router")

    # Router decides: multi-agent (sequential specialist chain) or single (general_review)
    graph.add_conditional_edges(
        "collaboration_router",
        route_after_collaboration_router,
        {
            "financial_specialist": "financial_specialist",
            "general_review": "general_review",
        },
    )

    # Multi-agent chain: financial -> rights -> compliance -> critic
    graph.add_conditional_edges(
        "financial_specialist",
        route_after_financial,
        {
            "rights_specialist": "rights_specialist",
            "critic": "critic",
        },
    )

    graph.add_conditional_edges(
        "rights_specialist",
        route_after_rights,
        {
            "compliance_specialist": "compliance_specialist",
            "critic": "critic",
        },
    )

    # compliance always goes to critic
    graph.add_edge("compliance_specialist", "critic")

    # general_review also goes to critic
    graph.add_edge("general_review", "critic")

    # Linear tail
    graph.add_edge("critic", "supervisor")
    graph.add_edge("supervisor", "report_generation")
    graph.add_edge("report_generation", "persist_result")
    graph.add_edge("persist_result", END)

    return graph.compile(checkpointer=checkpointer)
