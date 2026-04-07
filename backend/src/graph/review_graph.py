"""
LangGraph StateGraph — Contract Review Pipeline
Orchestrates: extraction -> routing -> retrieval -> review -> breakpoint -> aggregation
"""
import asyncio
import json
from typing import AsyncGenerator, Optional

from ..agents.entity_extraction import extract_entities
from ..agents.routing import decide_routing
from ..agents.logic_review import review_clauses
from ..agents.breakpoint import check_breakpoint
from ..agents.aggregation import generate_report


async def run_review_stream(
    contract_text: str,
    session_id: str,
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
    # ── Step 1: Started ──────────────────────────────────────────────
    yield _sse_event("review_started", {
        "session_id": session_id,
        "message": "开始审查合同，请稍候...",
    })
    await asyncio.sleep(0.5)

    # ── Step 2: Entity Extraction ───────────────────────────────────
    entities = extract_entities(contract_text)
    yield _sse_event("entity_extraction", {
        "session_id": session_id,
        "entities": entities,
    })
    await asyncio.sleep(0.8)

    # ── Step 3: Routing Decision ───────────────────────────────────
    routing = decide_routing(contract_text, entities)
    yield _sse_event("routing", {
        "session_id": session_id,
        "routing": routing,
    })
    await asyncio.sleep(0.8)

    # ── Step 4: Logic Review (per issue) ───────────────────────────
    issues = review_clauses(contract_text, routing)

    # RAG retrieval: yield actual pgvector results if available
    pgvector_results = routing.get("pgvector_results", [])
    if pgvector_results and routing["primary_source"] == "pgvector":
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

    for issue in issues:
        yield _sse_event("logic_review", {
            "session_id": session_id,
            "issue": issue,
        })
        await asyncio.sleep(0.4)

    # ── Step 5: Breakpoint ─────────────────────────────────────────
    breakpoint_data = check_breakpoint(issues)
    yield _sse_event("breakpoint", {
        "session_id": session_id,
        "breakpoint": breakpoint_data,
        "issues": issues,  # Pass issues so confirm can reuse them
    })

    # Return here — the generator is paused.
    # The /confirm endpoint will continue from aggregation.
    return

    # ── Step 6: Aggregation (reached after confirm) ────────────────
    # This code is only reached if the caller continues iterating after breakpoint.
    yield _sse_event("stream_resume", {"session_id": session_id})

    paragraphs = generate_report(contract_text, issues)
    for i, paragraph in enumerate(paragraphs):
        yield _sse_event("final_report", {
            "session_id": session_id,
            "paragraph": paragraph,
            "is_last": i == len(paragraphs) - 1,
        })
        await asyncio.sleep(0.3)

    yield _sse_event("review_complete", {"session_id": session_id})


async def run_aggregation_stream(
    contract_text: str,
    session_id: str,
    issues: list[dict],
) -> AsyncGenerator[dict, None]:
    """
    Phase 2: Run aggregation only (called by confirm endpoint).
    Reuses the issues from Phase 1 so LLM results are consistent.
    """
    yield _sse_event("stream_resume", {"session_id": session_id})

    paragraphs = generate_report(contract_text, issues)
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
