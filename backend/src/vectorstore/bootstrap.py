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


def ensure_vectorstore_schema() -> None:
    """Bring legacy database tables up to the current pgvector schema."""
    if not DATABASE_URL:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS contracts (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    lessor TEXT,
                    lessee TEXT,
                    source_type TEXT NOT NULL DEFAULT 'contract',
                    source_path TEXT,
                    source_key TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    contract_id BIGINT NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
                    chunk_text TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    embedding vector(1024) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (contract_id, chunk_index)
                )
                """
            )

            cur.execute(
                """
                ALTER TABLE contracts
                ADD COLUMN IF NOT EXISTS contract_type TEXT,
                ADD COLUMN IF NOT EXISTS lessor TEXT,
                ADD COLUMN IF NOT EXISTS lessee TEXT,
                ADD COLUMN IF NOT EXISTS source_type TEXT,
                ADD COLUMN IF NOT EXISTS source_path TEXT,
                ADD COLUMN IF NOT EXISTS source_key TEXT,
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                """
            )
            cur.execute(
                """
                ALTER TABLE contract_chunks
                ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                """
            )

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'contracts'
                """
            )
            contract_columns = {row[0] for row in cur.fetchall()}

            if "file_path" in contract_columns:
                cur.execute(
                    """
                    UPDATE contracts
                    SET source_path = COALESCE(source_path, file_path)
                    WHERE source_path IS NULL
                    """
                )

            cur.execute("UPDATE contracts SET contract_type = COALESCE(contract_type, '未知合同')")
            cur.execute("UPDATE contracts SET source_type = COALESCE(source_type, 'contract')")
            cur.execute(
                """
                UPDATE contracts
                SET source_key = CONCAT('legacy-contract-', id)
                WHERE source_key IS NULL OR BTRIM(source_key) = ''
                """
            )

            cur.execute("ALTER TABLE contracts ALTER COLUMN contract_type SET NOT NULL")
            cur.execute("ALTER TABLE contracts ALTER COLUMN source_type SET NOT NULL")
            cur.execute("ALTER TABLE contracts ALTER COLUMN source_key SET NOT NULL")

            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_source_key
                ON contracts (source_key)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_contracts_source_type
                ON contracts (source_type)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_contract_chunks_contract_id
                ON contract_chunks (contract_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_contract_chunks_embedding
                ON contract_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )

            conn.commit()


def bootstrap_vectorstore() -> None:
    """Optionally seed the built-in legal knowledge after database startup."""
    timeout_seconds = int(os.getenv("DATABASE_WAIT_TIMEOUT", "60"))
    database_ready = wait_for_database(timeout_seconds=timeout_seconds)

    if not database_ready:
        close_pool()
        return

    try:
        ensure_vectorstore_schema()
        print("[bootstrap] Vectorstore schema is ready.", flush=True)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[bootstrap] Schema migration failed: {exc}", flush=True)
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
