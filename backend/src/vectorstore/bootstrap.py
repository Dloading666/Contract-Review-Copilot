"""
Bootstrap helpers for containerized pgvector startup.
"""
import os
import time

from .builtin_seed import seed_builtin_legal_knowledge
from .connection import DATABASE_URL, close_pool, get_connection


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def wait_for_database(timeout_seconds: int = 60, interval_seconds: int = 2) -> bool:
    """Wait for the configured database to accept queries."""
    if not DATABASE_URL:
        print("[bootstrap] DATABASE_URL not set; skipping database wait.", flush=True)
        return False

    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            print("[bootstrap] Database is ready.", flush=True)
            return True
        except Exception as exc:  # pragma: no cover - retry loop
            last_error = exc
            time.sleep(interval_seconds)

    print(
        f"[bootstrap] Database was not ready after {timeout_seconds}s: {last_error}",
        flush=True,
    )
    return False


def bootstrap_vectorstore() -> None:
    """Optionally seed the built-in legal knowledge after database startup."""
    timeout_seconds = int(os.getenv("DATABASE_WAIT_TIMEOUT", "60"))
    database_ready = wait_for_database(timeout_seconds=timeout_seconds)

    if not database_ready:
        close_pool()
        return

    if not _is_truthy(os.getenv("AUTO_SEED_LEGAL_KNOWLEDGE", "0")):
        print(
            "[bootstrap] AUTO_SEED_LEGAL_KNOWLEDGE is disabled; skipping built-in seed.",
            flush=True,
        )
        close_pool()
        return

    try:
        chunk_count = seed_builtin_legal_knowledge()
        print(
            f"[bootstrap] Built-in legal knowledge ready with {chunk_count} new chunks.",
            flush=True,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[bootstrap] Optional seed failed: {exc}", flush=True)
    finally:
        close_pool()
