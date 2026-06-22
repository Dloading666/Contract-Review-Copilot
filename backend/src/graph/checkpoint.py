"""PostgreSQL checkpoint management for LangGraph."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import os
from ..config import get_settings

_checkpointer = None
_checkpointer_cm = None


async def init_checkpointer():
    """Initialize AsyncPostgresSaver at app startup.

    Raises RuntimeError if checkpoint is enabled but initialization fails.
    Does nothing if checkpoint is disabled.
    """
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
        logger.info("LangGraph AsyncPostgresSaver initialized")
    except Exception as exc:
        _checkpointer = None
        _checkpointer_cm = None
        raise RuntimeError(
            f"Checkpoint enabled but initialization failed: {exc}"
        ) from exc


async def close_checkpointer():
    """Clean up checkpointer at shutdown. No-op if not initialized."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer_cm is not None:
        try:
            await _checkpointer_cm.__aexit__(None, None, None)
        except Exception as exc:
            logger.exception("Checkpoint cleanup error: %s", exc)
    _checkpointer = None
    _checkpointer_cm = None


def get_checkpointer():
    """Return the active checkpointer, or None if disabled."""
    return _checkpointer
