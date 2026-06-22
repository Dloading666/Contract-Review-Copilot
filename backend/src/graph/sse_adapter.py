from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator


def _sse_event(event_type: str, data: dict) -> dict:
    return {
        "event": event_type,
        "data": data,
        "_raw": f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n",
    }


async def graph_to_sse_events(
    graph_agen: AsyncGenerator,
    session_id: str,
) -> AsyncGenerator[dict, None]:
    """Convert LangGraph astream output to legacy SSE events."""
    yield _sse_event("review_started", {
        "session_id": session_id,
        "message": "开始审查合同，请稍候...",
    })

    emitted_entity = False
    emitted_routing = False
    initial_issues = []
    report_paragraphs = []
    specialist_count = 0
    specialist_completed = 0

    async for chunk in graph_agen:
        if not isinstance(chunk, dict):
            continue

        for node_name, node_output in chunk.items():
            if not isinstance(node_output, dict):
                continue

            if node_name == "entity_extraction" and not emitted_entity:
                entities = node_output.get("entities", {})
                yield _sse_event("entity_extraction", {
                    "session_id": session_id,
                    "entities": entities,
                })
                emitted_entity = True

            elif node_name == "retrieval":
                routing = node_output.get("routing", {})
                if not emitted_routing:
                    yield _sse_event("routing", {
                        "session_id": session_id,
                        "routing": routing,
                    })
                    emitted_routing = True
                evidence = node_output.get("evidence", [])
                if evidence:
                    yield _sse_event("rag_retrieval", {
                        "session_id": session_id,
                        "documents": evidence,
                    })

            elif node_name == "collaboration_router":
                tasks = node_output.get("specialist_tasks", [])
                specialist_count = len(tasks)
                specialist_completed = 0
                for task_id in tasks:
                    yield _sse_event("agent_progress", {
                        "session_id": session_id,
                        "agent_id": task_id,
                        "role": _task_role_name(task_id),
                        "status": "started",
                        "completed": 0,
                        "total": specialist_count,
                    })

            elif node_name in ("financial_specialist", "rights_specialist",
                               "compliance_specialist", "general_review"):
                findings = node_output.get("candidate_findings", [])
                for finding in findings:
                    yield _sse_event("logic_review", {
                        "session_id": session_id,
                        "issue": finding,
                    })
                    initial_issues.append(finding)

                agent_id = node_name.replace("_specialist", "").replace("_review", "_review")
                degraded = node_output.get("degraded_agents", [])
                status = "degraded" if agent_id in degraded else "completed"
                specialist_completed += 1
                yield _sse_event("agent_progress", {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "role": _task_role_name(agent_id),
                    "status": status,
                    "completed": len(findings),
                    "total": specialist_count,
                })

            elif node_name == "critic":
                verified = node_output.get("verified_findings", [])
                yield _sse_event("initial_review_ready", {
                    "session_id": session_id,
                    "review_stage": "initial",
                    "summary": f"复核完成，{len(verified)} 条结论通过验证。",
                    "issues": verified,
                    "used_rule_fallback": False,
                })

            elif node_name == "supervisor":
                yield _sse_event("deep_review_started", {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "message": "正在生成最终报告...",
                })

            elif node_name == "report_generation":
                paragraphs = node_output.get("report_paragraphs", [])
                report_paragraphs = paragraphs
                for i, para in enumerate(paragraphs):
                    yield _sse_event("final_report", {
                        "session_id": session_id,
                        "paragraph": para,
                        "is_last": i == len(paragraphs) - 1,
                    })

            elif node_name == "persist_result":
                yield _sse_event("deep_review_complete", {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "summary": "合同分析已完成。",
                    "message": "合同分析已完成，页面内容已自动更新。",
                    "issues": initial_issues,
                    "changes": [],
                })
                yield _sse_event("review_complete", {"session_id": session_id})


def _task_role_name(task_id: str) -> str:
    names = {
        "financial_performance": "财务履约审查",
        "rights_remedies": "权利救济审查",
        "compliance_evidence": "合规证据审查",
        "general_review": "综合审查",
    }
    return names.get(task_id, task_id)
