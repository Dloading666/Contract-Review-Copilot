"""
LangGraph StateGraph — Contract Review Pipeline
Orchestrates: extraction -> routing -> retrieval -> review -> breakpoint -> aggregation
"""
import atexit
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, AsyncGenerator

from langgraph.graph import END, StateGraph

from .state import ReviewState
from ..agents.entity_extraction import extract_entities
from ..agents.routing import decide_routing
from ..agents.logic_review import review_clauses
from ..agents.breakpoint import check_breakpoint
from ..agents.aggregation import generate_report

_GRAPH_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="review-graph")
atexit.register(_GRAPH_EXECUTOR.shutdown, wait=False, cancel_futures=True)


async def _run_sync(func: Any, *args: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_GRAPH_EXECUTOR, lambda: func(*args))


async def entity_extraction_node(state: ReviewState) -> dict:
    entities = await _run_sync(
        extract_entities,
        state["contract_text"],
        state.get("model_key"),
    )
    return {"extracted_entities": entities}


async def routing_node(state: ReviewState) -> dict:
    routing = await _run_sync(
        decide_routing,
        state["contract_text"],
        state.get("extracted_entities") or {},
        state.get("model_key"),
    )
    return {"routing_decision": routing}


async def logic_review_node(state: ReviewState) -> dict:
    issues = await _run_sync(
        review_clauses,
        state["contract_text"],
        state.get("routing_decision") or {},
        state.get("extracted_entities") or {},
        state.get("model_key"),
    )
    return {"logic_review_results": issues}


async def breakpoint_node(state: ReviewState) -> dict:
    issues = state.get("logic_review_results") or []
    return {
        "breakpoint_data": check_breakpoint(issues),
        "logic_review_results": issues,
    }


async def aggregation_node(state: ReviewState) -> dict:
    paragraphs = await _run_sync(
        generate_report,
        state["contract_text"],
        state.get("logic_review_results") or [],
        state.get("model_key"),
    )
    return {"final_report": paragraphs}


@lru_cache(maxsize=1)
def get_review_graph():
    workflow = StateGraph(ReviewState)
    workflow.add_node("entity_extraction", entity_extraction_node)
    workflow.add_node("routing", routing_node)
    workflow.add_node("logic_review", logic_review_node)
    workflow.add_node("breakpoint", breakpoint_node)
    workflow.set_entry_point("entity_extraction")
    workflow.add_edge("entity_extraction", "routing")
    workflow.add_edge("routing", "logic_review")
    workflow.add_edge("logic_review", "breakpoint")
    workflow.add_edge("breakpoint", END)
    return workflow.compile()


@lru_cache(maxsize=1)
def get_aggregation_graph():
    workflow = StateGraph(ReviewState)
    workflow.add_node("aggregation", aggregation_node)
    workflow.set_entry_point("aggregation")
    workflow.add_edge("aggregation", END)
    return workflow.compile()


async def run_review_stream(
    contract_text: str,
    session_id: str,
    model_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Main entry point. Runs the full pipeline and yields SSE-formatted events.

    Pipeline:
        1. review_started
        2. entity_extraction  → extracted_entities
        3. routing            → routing_decision
        4. logic_review (per issue) → issues[]
        5. rag_retrieval (if pgvector) → documents[]
        6. breakpoint          → needs_human_review
        [PAUSE — waiting for confirm call]
        6. aggregation (per paragraph) → final_report[]
        7. review_complete
    """
    yield _sse_event("review_started", {
        "session_id": session_id,
        "message": "开始审查合同，请稍候...",
    })
    await asyncio.sleep(0.5)

    graph = get_review_graph()
    state_snapshot: ReviewState = {
        "contract_text": contract_text,
        "session_id": session_id,
        "model_key": model_key,
    }

    async for update in graph.astream(state_snapshot, stream_mode="updates"):
        for node_name, delta in update.items():
            state_snapshot.update(delta)

            if node_name == "entity_extraction":
                yield _sse_event("entity_extraction", {
                    "session_id": session_id,
                    "entities": state_snapshot.get("extracted_entities"),
                })
                await asyncio.sleep(0.8)

            elif node_name == "routing":
                routing = state_snapshot.get("routing_decision") or {}
                yield _sse_event("routing", {
                    "session_id": session_id,
                    "routing": routing,
                })
                pgvector_results = routing.get("pgvector_results", [])
                if pgvector_results and routing.get("primary_source") == "pgvector":
                    yield _sse_event("rag_retrieval", {
                        "source": "pgvector",
                        "documents": [
                            {
                                "title": chunk.get("metadata", {}).get("title", "法律条款"),
                                "content": chunk.get("chunk_text", ""),
                                "score": float(chunk.get("similarity", 0)),
                            }
                            for chunk in pgvector_results
                        ],
                    })
                await asyncio.sleep(0.8)

            elif node_name == "logic_review":
                issues = state_snapshot.get("logic_review_results") or []
                for issue in issues:
                    yield _sse_event("logic_review", {
                        "session_id": session_id,
                        "issue": issue,
                    })
                    await asyncio.sleep(0.4)

            elif node_name == "breakpoint":
                breakpoint_data = state_snapshot.get("breakpoint_data") or {}
                if breakpoint_data.get("needs_review"):
                    yield _sse_event("breakpoint", {
                        "session_id": session_id,
                        "breakpoint": breakpoint_data,
                        "issues": state_snapshot.get("logic_review_results") or [],
                    })
                    return

    yield _sse_event("review_complete", {"session_id": session_id})


async def run_aggregation_stream(
    contract_text: str,
    session_id: str,
    issues: list[dict],
    model_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Phase 2: Run aggregation only (called by confirm endpoint).
    Reuses the issues from Phase 1 so LLM results are consistent.
    """
    yield _sse_event("stream_resume", {"session_id": session_id})

    graph = get_aggregation_graph()
    state_snapshot: ReviewState = {
        "contract_text": contract_text,
        "session_id": session_id,
        "model_key": model_key,
        "logic_review_results": issues,
    }

    paragraphs: list[str] = []
    async for update in graph.astream(state_snapshot, stream_mode="updates"):
        for node_name, delta in update.items():
            state_snapshot.update(delta)
            if node_name == "aggregation":
                paragraphs = state_snapshot.get("final_report") or []

    for i, paragraph in enumerate(paragraphs):
        yield _sse_event("final_report", {
            "session_id": session_id,
            "paragraph": paragraph,
            "is_last": i == len(paragraphs) - 1,
        })
        await asyncio.sleep(0.3)

    yield _sse_event("review_complete", {"session_id": session_id})


def _sse_event(event_type: str, data: dict) -> dict:
    """Format a dict as an SSE-compatible event."""
    return {
        "event": event_type,
        "data": data,
        "_raw": f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n",
    }
