"""
Contract review stream orchestration via LangGraph.

Single entry point: run_review_stream dispatches to LangGraph graph.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from ..config import get_settings

logger = logging.getLogger(__name__)


async def run_review_stream(
    contract_text: str,
    session_id: str,
    model_key: str | None = None,
    *,
    user_id: str | None = None,
    filename: str = "",
    resume: bool = False,
):
    """Run the LangGraph review pipeline and yield SSE events."""
    from .langgraph_builder import build_review_graph
    from .sse_adapter import graph_to_sse_events
    from .checkpoint import get_checkpointer

    settings = get_settings()

    checkpointer = None
    if settings.review_checkpoint_enabled:
        checkpointer = get_checkpointer()
        if checkpointer is None:
            raise RuntimeError(
                "Checkpoint enabled but checkpointer not initialized. "
                "Check that init_checkpointer() was called at startup."
            )

    graph = build_review_graph(checkpointer=checkpointer)

    config = None
    if checkpointer is not None:
        config = {
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": "contract_review_v1",
            }
        }

    if resume and checkpointer is not None:
        from ..services import sync_store
        from asyncio import to_thread
        if user_id:
            session = await to_thread(sync_store.get_review_session, user_id, session_id)
            if not session:
                yield _sse_event("error", {"message": "Session not found or access denied"})
                return
        try:
            existing = await checkpointer.aget(config)
            if existing is None:
                logger.info("No checkpoint for %s, full rerun", session_id)
                initial_state = _build_initial_state(session_id, contract_text, model_key, user_id, filename)
            else:
                logger.info("Resuming from checkpoint for %s", session_id)
                initial_state = None
        except Exception as exc:
            logger.warning("Checkpoint lookup failed for %s: %s, full rerun", session_id, exc)
            initial_state = _build_initial_state(session_id, contract_text, model_key, user_id, filename)
    else:
        initial_state = _build_initial_state(session_id, contract_text, model_key, user_id, filename)

    stream_kwargs: dict[str, Any] = {"stream_mode": "updates"}
    if checkpointer is not None:
        stream_kwargs["durability"] = settings.review_checkpoint_durability

    try:
        async for event in graph_to_sse_events(
            graph.astream(initial_state, config=config, **stream_kwargs),
            session_id,
        ):
            yield event
    except Exception as exc:
        logger.exception("LangGraph review stream failed for %s", session_id)
        _err_data = json.dumps({"message": str(exc)}, ensure_ascii=False)
        yield {
            "event": "error",
            "data": {"message": str(exc)},
            "_raw": f"event: error\ndata: {_err_data}\n\n",
        }


def _build_initial_state(
    session_id: str,
    contract_text: str,
    model_key: str | None,
    user_id: str | None,
    filename: str,
) -> dict:
    return {
        "session_id": session_id,
        "contract_text": contract_text,
        "model_key": model_key,
        "user_id": user_id,
        "filename": filename,
    }


def _sse_event(event_type: str, data: dict) -> dict:
    return {
        "event": event_type,
        "data": data,
        "_raw": f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n",
    }


# --- Compatibility stubs for deep review / aggregation (used by UUMit endpoint) ---

async def run_aggregation_stream(contract_text, session_id, issues=None, model_key=None):
    """Stub: generates report paragraphs directly."""
    from ..agents.aggregation import generate_report
    from asyncio import get_running_loop
    from concurrent.futures import ThreadPoolExecutor

    loop = get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    paragraphs = await loop.run_in_executor(
        executor, lambda: generate_report(contract_text, issues, model_key)
    )
    yield _sse_event("stream_resume", {"session_id": session_id})
    for index, paragraph in enumerate(paragraphs):
        yield _sse_event("final_report", {
            "session_id": session_id,
            "paragraph": paragraph,
            "is_last": index == len(paragraphs) - 1,
        })
    yield _sse_event("review_complete", {"session_id": session_id})


async def run_deep_review_stream(contract_text, session_id, issues=None, model_key=None):
    """Stub: runs the full LangGraph pipeline (same as run_review_stream)."""
    async for event in run_review_stream(
        contract_text, session_id, model_key,
    ):
        yield event
