from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import time
from typing import Any, AsyncGenerator


def _sse_event(event_type: str, data: dict) -> dict:
    return {
        "event": event_type,
        "data": data,
        "_raw": f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n",
    }


AGENT_ID_MAP = {
    "financial_specialist": "financial_performance",
    "rights_specialist": "rights_remedies",
    "compliance_specialist": "compliance_evidence",
    "general_review": "general_review",
}

ROLE_NAME_MAP = {
    "financial_performance": "财务履约审查",
    "rights_remedies": "权利救济审查",
    "compliance_evidence": "合规证据审查",
    "general_review": "综合审查",
}


async def graph_to_sse_events(
    graph_agen: AsyncGenerator,
    session_id: str,
    heartbeat_interval: float = 8.0,
) -> AsyncGenerator[dict, None]:
    """Convert LangGraph astream output to legacy SSE events with proper ordering."""
    yield _sse_event("review_started", {
        "session_id": session_id,
        "message": "开始审查合同，请稍候...",
    })

    # Cache for ordering
    cached_entity = None
    cached_routing = None
    cached_rule_issues = []
    cached_evidence = []
    emitted_initial_ready = False
    specialist_count = 0
    final_findings = []
    report_paragraphs = []
    used_rule_fallback = False
    persisted = False
    last_event_time = time.monotonic()

    try:
        async for chunk in _heartbeat_aware_iter(graph_agen, heartbeat_interval, session_id, last_event_time):
            if chunk.get("event") == "heartbeat":
                yield chunk
                last_event_time = time.monotonic()
                continue

            node_name = chunk.get("node")
            node_output = chunk.get("output") or {}

            if node_name == "entity_extraction":
                cached_entity = node_output.get("entities", {})

            elif node_name == "rule_scan":
                cached_rule_issues = node_output.get("rule_issues", [])

            elif node_name == "retrieval":
                cached_routing = node_output.get("routing", {})
                cached_evidence = node_output.get("evidence", [])

                # Now emit entity + routing in correct order
                if cached_entity:
                    yield _sse_event("entity_extraction", {
                        "session_id": session_id,
                        "entities": cached_entity,
                    })
                yield _sse_event("routing", {
                    "session_id": session_id,
                    "routing": cached_routing,
                })
                if cached_evidence:
                    yield _sse_event("rag_retrieval", {
                        "session_id": session_id,
                        "documents": cached_evidence,
                    })

                # Emit rule findings as initial logic_review
                for issue in cached_rule_issues:
                    yield _sse_event("logic_review", {
                        "session_id": session_id,
                        "issue": issue,
                    })
                last_event_time = time.monotonic()

            elif node_name == "collaboration_router":
                tasks = node_output.get("specialist_tasks", [])
                specialist_count = len(tasks)
                active_agent_ids = set()
                # Section 6: Only emit progress for agents that will actually run
                for task_id in tasks:
                    agent_id = AGENT_ID_MAP.get(task_id, task_id)
                    active_agent_ids.add(agent_id)
                    yield _sse_event("agent_progress", {
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "role": ROLE_NAME_MAP.get(agent_id, agent_id),
                        "status": "started",
                        "completed": 0,
                        "total": specialist_count,
                    })
                last_event_time = time.monotonic()

            elif node_name in AGENT_ID_MAP:
                agent_id = AGENT_ID_MAP[node_name]
                # Section 5: Don't emit agent findings as logic_review
                # They go through critic first; only rule findings shown early
                degraded = node_output.get("degraded_agents", [])
                status = "degraded" if agent_id in degraded else "completed"
                yield _sse_event("agent_progress", {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "role": ROLE_NAME_MAP.get(agent_id, agent_id),
                    "status": status,
                    "completed": len(node_output.get("candidate_findings", [])),
                    "total": specialist_count,
                })
                last_event_time = time.monotonic()

            elif node_name == "prepare_candidates":
                used_rule_fallback = node_output.get("used_rule_fallback", False)
                candidates = node_output.get("candidate_findings", [])
                yield _sse_event("initial_review_ready", {
                    "session_id": session_id,
                    "review_stage": "initial",
                    "summary": f"初审完成，{len(candidates)} 条发现待复核。",
                    "issues": candidates,
                    "used_rule_fallback": used_rule_fallback,
                })
                emitted_initial_ready = True

            elif node_name == "critic":
                yield _sse_event("deep_review_started", {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "message": "正在进行最终裁决...",
                })
                last_event_time = time.monotonic()

            elif node_name == "supervisor":
                final_findings = node_output.get("final_findings", [])
                overall_risk = node_output.get("overall_risk", "medium")
                summary = node_output.get("supervisor_summary", "审查完成")

                yield _sse_event("deep_review_update", {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "summary": summary,
                    "message": "最终审查结果已生成。",
                    "issues": final_findings,
                    "changes": [],
                })
                last_event_time = time.monotonic()

            elif node_name == "report_generation":
                report_paragraphs = node_output.get("report_paragraphs", [])
                for i, para in enumerate(report_paragraphs):
                    yield _sse_event("final_report", {
                        "session_id": session_id,
                        "paragraph": para,
                        "is_last": i == len(report_paragraphs) - 1,
                    })
                last_event_time = time.monotonic()

            elif node_name == "persist_result":
                persisted = node_output.get("persisted", False)
                yield _sse_event("deep_review_complete", {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "summary": "合同分析已完成。",
                    "message": "合同分析已完成，页面内容已自动更新。",
                    "issues": final_findings,
                    "changes": [],
                    "persisted": persisted,
                })
                yield _sse_event("review_complete", {
                    "session_id": session_id,
                    "persisted": persisted,
                })

    except Exception as exc:
        logger.exception("[SSE Adapter] Graph failed: %s", exc)
        if emitted_initial_ready:
            yield _sse_event("deep_review_failed", {
                "session_id": session_id,
                "message": "完整分析暂未补全，当前先展示阶段性审查结果。",
            })
            yield _sse_event("review_complete", {"session_id": session_id, "degraded": True})
        else:
            # Fallback to rule findings
            if cached_rule_issues:
                for issue in cached_rule_issues:
                    yield _sse_event("logic_review", {
                        "session_id": session_id,
                        "issue": issue,
                    })
                yield _sse_event("initial_review_ready", {
                    "session_id": session_id,
                    "review_stage": "initial",
                    "summary": f"阶段性审查完成，{len(cached_rule_issues)} 条规则发现。",
                    "issues": cached_rule_issues,
                    "used_rule_fallback": True,
                })
            yield _sse_event("error", {"message": str(exc)})


async def _heartbeat_aware_iter(
    graph_agen: AsyncGenerator,
    heartbeat_interval: float,
    session_id: str,
    start_time: float,
) -> AsyncGenerator[dict, None]:
    """Yield graph updates, injecting heartbeat events when the stream is slow."""
    agen_next = graph_agen.__aiter__()
    pending = None

    while True:
        try:
            if pending is None:
                task = asyncio.create_task(agen_next.__anext__())
            else:
                task = pending
                pending = None

            try:
                chunk = await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield _sse_event("deep_review_heartbeat", {
                    "session_id": session_id,
                    "stage": "processing",
                    "message": "合同分析仍在进行中...",
                    "completed": False,
                })
                pending = task
                continue

            if not isinstance(chunk, dict):
                continue

            for node_name, node_output in chunk.items():
                yield {"node": node_name, "output": node_output}

        except StopAsyncIteration:
            break
        except Exception as exc:
            logger.exception("[SSE Adapter] Iterator error: %s", exc)
            raise
