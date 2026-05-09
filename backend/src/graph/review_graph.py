"""
Contract review stream orchestration.

This module keeps the user-facing review stream responsive by splitting the
pipeline into two stages:

1. Initial review
   Emit risk cards and an initial summary inside a hard time budget.
2. Full completion
   Continue the heavier model/report work in the same SSE stream, while
   sending periodic heartbeat events so reverse proxies do not treat the
   request as idle.
"""
from __future__ import annotations

import atexit
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator

from ..agents.aggregation import generate_report
from ..agents.entity_extraction import _regex_fallback, extract_entities
from ..agents.logic_review import model_review_clauses, rule_review_clauses
from ..agents.routing import _default_routing, decide_routing
from ..config import get_settings

_GRAPH_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="review-graph")
atexit.register(_GRAPH_EXECUTOR.shutdown, wait=False, cancel_futures=True)

_SEVERITY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


async def _run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_GRAPH_EXECUTOR, lambda: func(*args, **kwargs))


def _sse_event(event_type: str, data: dict) -> dict:
    return {
        "event": event_type,
        "data": data,
        "_raw": f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n",
    }


def _issue_key(issue: dict) -> str:
    clause = str(issue.get("clause", "")).strip().lower()
    problem = str(issue.get("issue", "")).strip().lower()
    return f"{clause}|{problem}"


def _severity_rank(issue: dict) -> int:
    level = str(issue.get("level") or issue.get("severity") or "low").lower()
    return _SEVERITY_ORDER.get(level, 1)


def _annotate_issue_changes(issues: list[dict], changes: list[dict]) -> list[dict]:
    change_map = {
        _issue_key(change): change.get("change_type", "none")
        for change in changes
    }
    return [
        {
            **issue,
            "change_type": change_map.get(_issue_key(issue), "none"),
        }
        for issue in issues
    ]


def _build_finding_changes(initial_issues: list[dict], deep_issues: list[dict]) -> list[dict]:
    previous = {_issue_key(issue): issue for issue in initial_issues}
    changes: list[dict] = []

    for issue in deep_issues:
        prior = previous.get(_issue_key(issue))
        if prior is None:
            changes.append({**issue, "change_type": "new"})
            continue
        if _severity_rank(issue) > _severity_rank(prior):
            changes.append({**issue, "change_type": "upgraded"})

    return changes


def _build_review_summary(issues: list[dict], *, deep_complete: bool) -> str:
    critical = sum(1 for issue in issues if _severity_rank(issue) >= 4)
    high = sum(1 for issue in issues if _severity_rank(issue) == 3)
    medium = sum(1 for issue in issues if _severity_rank(issue) == 2)
    substantive = critical + high + medium

    if substantive == 0:
        return (
            "合同分析已完成，当前未发现明显不公平条款。"
            if deep_complete
            else "阶段性审查未发现明显不公平条款，正在补全完整分析。"
        )

    prefix = "合同分析已完成" if deep_complete else "阶段性审查已完成"
    return (
        f"{prefix}，已识别 {substantive} 处风险："
        f"{critical} 处高危、{high} 处高风险、{medium} 处提示。"
        + ("" if deep_complete else " 正在继续补全完整分析与报告。")
    )


async def _await_with_heartbeat(
    task: asyncio.Task[Any],
    *,
    session_id: str,
    stage: str,
    message: str,
    heartbeat_seconds: float,
) -> AsyncGenerator[dict, None]:
    while True:
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_seconds)
            yield _sse_event(
                "deep_review_heartbeat",
                {
                    "session_id": session_id,
                    "stage": stage,
                    "message": message,
                    "completed": True,
                },
            )
            yield {"event": "_task_result", "data": {"result": result}}
            return
        except asyncio.TimeoutError:
            yield _sse_event(
                "deep_review_heartbeat",
                {
                    "session_id": session_id,
                    "stage": stage,
                    "message": message,
                    "completed": False,
                },
            )


async def run_review_stream(
    contract_text: str,
    session_id: str,
    model_key: str | None = None,
    review_mode: str = "deep",
) -> AsyncGenerator[dict, None]:
    """
    Run the main review flow and emit SSE events.

    Event shape:
      - review_started
      - entity_extraction
      - routing
      - logic_review (initial cards)
      - initial_review_ready
      - deep_review_started
      - deep_review_update (optional)
      - deep_review_heartbeat (0..n)
      - final_report (0..n)
      - deep_review_complete
      - review_complete
    """
    settings = get_settings()
    initial_deadline = time.monotonic() + settings.review_initial_deadline_seconds

    yield _sse_event(
        "review_started",
        {
            "session_id": session_id,
            "message": "开始审查合同，请稍候...",
        },
    )

    rule_task = asyncio.create_task(_run_sync(rule_review_clauses, contract_text))
    entity_task = asyncio.create_task(_run_sync(extract_entities, contract_text, model_key))

    initial_issues: list[dict] = []
    initial_ready = False

    try:
        try:
            extracted_entities = await asyncio.wait_for(
                asyncio.shield(entity_task),
                timeout=settings.review_entity_timeout_seconds,
            )
        except asyncio.TimeoutError:
            extracted_entities = await _run_sync(_regex_fallback, contract_text)

        yield _sse_event(
            "entity_extraction",
            {
                "session_id": session_id,
                "entities": extracted_entities,
            },
        )

        routing_task = asyncio.create_task(_run_sync(decide_routing, contract_text, extracted_entities, model_key))
        try:
            routing = await asyncio.wait_for(
                asyncio.shield(routing_task),
                timeout=settings.review_routing_timeout_seconds,
            )
        except asyncio.TimeoutError:
            routing = await _run_sync(_default_routing, contract_text, extracted_entities)

        yield _sse_event(
            "routing",
            {
                "session_id": session_id,
                "routing": routing,
            },
        )

        pgvector_results = routing.get("pgvector_results", [])
        if pgvector_results and routing.get("primary_source") == "pgvector":
            yield _sse_event(
                "rag_retrieval",
                {
                    "source": "pgvector",
                    "documents": [
                        {
                            "title": chunk.get("metadata", {}).get("title", "法律条款"),
                            "content": chunk.get("chunk_text", ""),
                            "score": float(chunk.get("similarity", 0)),
                        }
                        for chunk in pgvector_results
                    ],
                },
            )

        rule_issues = await rule_task
        remaining = max(initial_deadline - time.monotonic(), 0.0)

        model_task: asyncio.Task[list[dict]] | None = None
        if remaining > 0:
            model_timeout = min(settings.review_model_timeout_seconds, remaining)
            model_task = asyncio.create_task(
                _run_sync(
                    model_review_clauses,
                    contract_text,
                    routing,
                    extracted_entities,
                    model_key,
                    timeout=model_timeout,
                    allow_retry=False,
                )
            )

        if model_task is None:
            initial_issues = rule_issues
        else:
            try:
                model_issues = await asyncio.wait_for(asyncio.shield(model_task), timeout=remaining)
                from ..agents.logic_review import _merge_issue_lists

                initial_issues = _merge_issue_lists(model_issues, rule_issues)
            except asyncio.TimeoutError:
                initial_issues = rule_issues
            except Exception as exc:
                print(f"[ReviewGraph] Model initial review failed: {exc}", flush=True)
                initial_issues = rule_issues

        initial_issues = _annotate_issue_changes(initial_issues, [])
        for issue in initial_issues:
            yield _sse_event(
                "logic_review",
                {
                    "session_id": session_id,
                    "issue": issue,
                },
            )

        yield _sse_event(
            "initial_review_ready",
            {
                "session_id": session_id,
                "review_stage": "initial",
                "summary": _build_review_summary(initial_issues, deep_complete=False),
                "issues": initial_issues,
                "used_rule_fallback": model_task is None or not model_task.done(),
            },
        )
        initial_ready = True

        yield _sse_event(
            "deep_review_started",
            {
                "session_id": session_id,
                "review_stage": "deep",
                "message": "阶段性结果已生成，正在补全完整分析与报告。",
            },
        )

        deep_issues = initial_issues
        model_review_degraded = False
        if model_task is not None and not model_task.done():
            try:
                async for heartbeat_event in _await_with_heartbeat(
                    model_task,
                    session_id=session_id,
                    stage="model_review",
                    message="合同分析仍在进行中...",
                    heartbeat_seconds=settings.review_heartbeat_interval_seconds,
                ):
                    if heartbeat_event["event"] == "_task_result":
                        model_issues = heartbeat_event["data"]["result"]
                        from ..agents.logic_review import _merge_issue_lists

                        deep_issues = _merge_issue_lists(model_issues, rule_issues)
                        break
                    yield heartbeat_event
            except Exception as exc:
                model_review_degraded = True
                print(f"[ReviewGraph] Deep model review failed, continuing with initial issues: {exc}", flush=True)
        elif model_task is not None:
            try:
                from ..agents.logic_review import _merge_issue_lists

                deep_issues = _merge_issue_lists(model_task.result(), rule_issues)
            except Exception as exc:
                model_review_degraded = True
                print(f"[ReviewGraph] Deep review merge skipped: {exc}", flush=True)

        finding_changes = _build_finding_changes(initial_issues, deep_issues)
        deep_issues = _annotate_issue_changes(deep_issues, finding_changes)
        if finding_changes or model_review_degraded:
            yield _sse_event(
                "deep_review_update",
                {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "summary": _build_review_summary(deep_issues, deep_complete=False),
                    "message": (
                        f"合同分析补充了 {len(finding_changes)} 处新的或升级后的分析结果。"
                        if finding_changes
                        else "模型暂时超时，已基于当前扫描结果继续生成完整报告。"
                    ),
                    "issues": deep_issues,
                    "changes": finding_changes,
                    "degraded": model_review_degraded,
                },
            )

        report_task = asyncio.create_task(_run_sync(generate_report, contract_text, deep_issues, model_key))
        paragraphs: list[str] = []
        async for heartbeat_event in _await_with_heartbeat(
            report_task,
            session_id=session_id,
            stage="report_generation",
            message="完整报告仍在生成中...",
            heartbeat_seconds=settings.review_heartbeat_interval_seconds,
        ):
            if heartbeat_event["event"] == "_task_result":
                paragraphs = heartbeat_event["data"]["result"]
                break
            yield heartbeat_event

        for index, paragraph in enumerate(paragraphs):
            yield _sse_event(
                "final_report",
                {
                    "session_id": session_id,
                    "paragraph": paragraph,
                    "is_last": index == len(paragraphs) - 1,
                },
            )

        yield _sse_event(
            "deep_review_complete",
            {
                "session_id": session_id,
                "review_stage": "deep",
                "summary": _build_review_summary(deep_issues, deep_complete=True),
                "message": "合同分析已完成，页面内容已自动更新。",
                "issues": deep_issues,
                "changes": finding_changes,
            },
        )
        yield _sse_event("review_complete", {"session_id": session_id})

    except Exception as exc:
        print(f"[ReviewGraph] Review stream failed: {exc}", flush=True)

        if not initial_ready:
            fallback_issues = initial_issues
            if not fallback_issues:
                try:
                    fallback_issues = await rule_task
                except Exception:
                    fallback_issues = await _run_sync(rule_review_clauses, contract_text)
            fallback_issues = _annotate_issue_changes(fallback_issues, [])

            if fallback_issues:
                for issue in fallback_issues:
                    yield _sse_event(
                        "logic_review",
                        {
                            "session_id": session_id,
                            "issue": issue,
                        },
                    )
                yield _sse_event(
                    "initial_review_ready",
                    {
                        "session_id": session_id,
                        "review_stage": "initial",
                        "summary": _build_review_summary(fallback_issues, deep_complete=False),
                        "issues": fallback_issues,
                        "used_rule_fallback": True,
                    },
                )
                initial_ready = True

        if initial_ready:
            yield _sse_event(
                "deep_review_failed",
                {
                    "session_id": session_id,
                    "message": "完整分析暂未补全，当前先展示阶段性审查结果。",
                },
            )
            yield _sse_event("review_complete", {"session_id": session_id, "degraded": True})
            return

        yield _sse_event("error", {"message": str(exc)})


async def run_aggregation_stream(
    contract_text: str,
    session_id: str,
    issues: list[dict],
    model_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Compatibility endpoint for older confirm/resume flows.
    """
    yield _sse_event("stream_resume", {"session_id": session_id})

    paragraphs = await _run_sync(generate_report, contract_text, issues, model_key)
    for index, paragraph in enumerate(paragraphs):
        yield _sse_event(
            "final_report",
            {
                "session_id": session_id,
                "paragraph": paragraph,
                "is_last": index == len(paragraphs) - 1,
            },
        )

    yield _sse_event("review_complete", {"session_id": session_id})


async def run_deep_review_stream(
    contract_text: str,
    session_id: str,
    issues: list[dict] | None = None,
    model_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Resume only the deep-review/report stage from an already available
    initial review result, without re-running OCR or re-emitting initial cards.
    """
    settings = get_settings()
    initial_issues = list(issues or [])

    if not initial_issues:
        try:
            initial_issues = await _run_sync(rule_review_clauses, contract_text)
        except Exception:
            initial_issues = []

    initial_issues = _annotate_issue_changes(initial_issues, [])

    yield _sse_event(
        "deep_review_started",
        {
            "session_id": session_id,
            "review_stage": "deep",
            "message": "正在继续补全完整分析与报告。",
        },
    )

    try:
        try:
            extracted_entities = await asyncio.wait_for(
                asyncio.shield(asyncio.create_task(_run_sync(extract_entities, contract_text, model_key))),
                timeout=settings.review_entity_timeout_seconds,
            )
        except asyncio.TimeoutError:
            extracted_entities = await _run_sync(_regex_fallback, contract_text)

        try:
            routing = await asyncio.wait_for(
                asyncio.shield(asyncio.create_task(_run_sync(decide_routing, contract_text, extracted_entities, model_key))),
                timeout=settings.review_routing_timeout_seconds,
            )
        except asyncio.TimeoutError:
            routing = await _run_sync(_default_routing, contract_text, extracted_entities)

        pgvector_results = routing.get("pgvector_results", [])
        if pgvector_results and routing.get("primary_source") == "pgvector":
            yield _sse_event(
                "rag_retrieval",
                {
                    "source": "pgvector",
                    "documents": [
                        {
                            "title": chunk.get("metadata", {}).get("title", "法律条款"),
                            "content": chunk.get("chunk_text", ""),
                            "score": float(chunk.get("similarity", 0)),
                        }
                        for chunk in pgvector_results
                    ],
                },
            )

        model_task = asyncio.create_task(
            _run_sync(
                model_review_clauses,
                contract_text,
                routing,
                extracted_entities,
                model_key,
                timeout=settings.review_model_timeout_seconds,
                allow_retry=True,
            )
        )

        deep_issues = initial_issues
        model_review_degraded = False
        try:
            async for heartbeat_event in _await_with_heartbeat(
                model_task,
                session_id=session_id,
                stage="model_review",
                message="合同分析仍在进行中...",
                heartbeat_seconds=settings.review_heartbeat_interval_seconds,
            ):
                if heartbeat_event["event"] == "_task_result":
                    model_issues = heartbeat_event["data"]["result"]
                    from ..agents.logic_review import _merge_issue_lists

                    deep_issues = _merge_issue_lists(model_issues, initial_issues) if initial_issues else model_issues
                    break
                yield heartbeat_event
        except Exception as exc:
            model_review_degraded = True
            print(f"[ReviewGraph] Deep model review resume failed, continuing with initial issues: {exc}", flush=True)

        finding_changes = _build_finding_changes(initial_issues, deep_issues)
        deep_issues = _annotate_issue_changes(deep_issues, finding_changes)
        if finding_changes or model_review_degraded:
            yield _sse_event(
                "deep_review_update",
                {
                    "session_id": session_id,
                    "review_stage": "deep",
                    "summary": _build_review_summary(deep_issues, deep_complete=False),
                    "message": (
                        f"合同分析补充了 {len(finding_changes)} 处新的或升级后的分析结果。"
                        if finding_changes
                        else "模型暂时超时，已基于当前扫描结果继续生成完整报告。"
                    ),
                    "issues": deep_issues,
                    "changes": finding_changes,
                    "degraded": model_review_degraded,
                },
            )

        report_task = asyncio.create_task(_run_sync(generate_report, contract_text, deep_issues, model_key))
        paragraphs: list[str] = []
        async for heartbeat_event in _await_with_heartbeat(
            report_task,
            session_id=session_id,
            stage="report_generation",
            message="完整报告仍在生成中...",
            heartbeat_seconds=settings.review_heartbeat_interval_seconds,
        ):
            if heartbeat_event["event"] == "_task_result":
                paragraphs = heartbeat_event["data"]["result"]
                break
            yield heartbeat_event

        for index, paragraph in enumerate(paragraphs):
            yield _sse_event(
                "final_report",
                {
                    "session_id": session_id,
                    "paragraph": paragraph,
                    "is_last": index == len(paragraphs) - 1,
                },
            )

        yield _sse_event(
            "deep_review_complete",
            {
                "session_id": session_id,
                "review_stage": "deep",
                "summary": _build_review_summary(deep_issues, deep_complete=True),
                "message": "合同分析已完成，页面内容已自动更新。",
                "issues": deep_issues,
                "changes": finding_changes,
            },
        )
        yield _sse_event("review_complete", {"session_id": session_id})
    except Exception as exc:
        print(f"[ReviewGraph] Deep review resume failed: {exc}", flush=True)
        yield _sse_event(
            "deep_review_failed",
            {
                "session_id": session_id,
                "message": "完整分析暂未补全，你可以再次补全分析。",
            },
        )
        yield _sse_event("review_complete", {"session_id": session_id, "degraded": True})
