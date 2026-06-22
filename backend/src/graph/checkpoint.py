"""PostgreSQL checkpoint management for LangGraph."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from ..config import get_settings

# Global reference to the checkpointer
_checkpointer = None
_checkpointer_cm = None


async def init_checkpointer():
    """Initialize AsyncPostgresSaver at app startup."""
    global _checkpointer, _checkpointer_cm
    settings = get_settings()

    if not settings.review_checkpoint_enabled:
        return

    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        database_url = settings.database_url
        if not database_url:
            raise RuntimeError("DATABASE_URL required for checkpoint")

        _checkpointer_cm = AsyncPostgresSaver.from_conn_string(database_url)
        _checkpointer = await _checkpointer_cm.__aenter__()
        await _checkpointer.setup()
        print("LangGraph AsyncPostgresSaver initialized", flush=True)
    except Exception as exc:
        raise RuntimeError(
            f"Checkpoint enabled but initialization failed: {exc}"
        ) from exc


async def close_checkpointer():
    """Clean up checkpointer at shutdown."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer_cm is not None:
        try:
            await _checkpointer_cm.__aexit__(None, None, None)
        except Exception as exc:
            print(f"Checkpoint cleanup error: {exc}", flush=True)
    _checkpointer = None
    _checkpointer_cm = None


def get_checkpointer():
    """Return the active checkpointer, or None if disabled."""
    return _checkpointer
