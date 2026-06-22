from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from ..commerce import ensure_commerce_schema
from ..vectorstore.connection import get_connection


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None


def _risk_level(issue: dict[str, Any]) -> str:
    level = str(issue.get("level") or issue.get("severity") or "").lower()
    if level in {"critical", "high", "medium", "low"}:
        return level
    score = int(issue.get("risk_level") or 0)
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def summarize_risks(issues: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in issues:
        counts[_risk_level(issue)] += 1

    if counts["critical"] or counts["high"]:
        overall = "high"
    elif counts["medium"]:
        overall = "medium"
    else:
        overall = "low"
    return overall, counts


def ensure_sync_schema() -> None:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_documents (
                    document_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    filename TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'direct',
                    content_text TEXT NOT NULL DEFAULT '',
                    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    document_id TEXT REFERENCES user_documents(document_id) ON DELETE SET NULL,
                    filename TEXT NOT NULL DEFAULT '',
                    contract_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    review_stage TEXT NOT NULL DEFAULT 'idle',
                    overall_risk TEXT NOT NULL DEFAULT 'low',
                    risk_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
                    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
                    report_paragraphs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    extracted_info JSONB,
                    routing_decision JSONB,
                    initial_summary TEXT,
                    deep_update_notice TEXT,
                    breakpoint_message TEXT,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS review_findings (
                    finding_id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES review_sessions(session_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    clause TEXT NOT NULL DEFAULT '',
                    issue TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'low',
                    risk_level INTEGER NOT NULL DEFAULT 0,
                    suggestion TEXT NOT NULL DEFAULT '',
                    legal_reference TEXT NOT NULL DEFAULT '',
                    matched_text TEXT NOT NULL DEFAULT '',
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'complete',
                    model TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_documents_user_updated ON user_documents(user_id, updated_at DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_review_sessions_user_updated ON review_sessions(user_id, updated_at DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at)"
            )
        conn.commit()


def create_document(
    *,
    user_id: str,
    filename: str,
    content_text: str,
    source_type: str,
    warnings: list[str] | None = None,
    status: str = "ready",
) -> dict[str, Any]:
    ensure_sync_schema()
    document_id = f"doc-{uuid.uuid4().hex}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_documents (
                    document_id, user_id, filename, source_type, content_text, warnings, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, user_id, filename, source_type, status, warnings, created_at, updated_at
                """,
                (
                    document_id,
                    user_id,
                    filename or "",
                    source_type or "direct",
                    content_text or "",
                    Json(warnings or []),
                    status,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _document_from_row(row)


def ensure_review_session(
    *,
    user_id: str,
    session_id: str,
    filename: str = "",
    contract_text: str = "",
    document_id: str | None = None,
    status: str = "reviewing",
    review_stage: str = "initial",
) -> dict[str, Any]:
    ensure_sync_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_sessions (
                    session_id, user_id, document_id, filename, contract_text, status, review_stage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET filename = COALESCE(NULLIF(EXCLUDED.filename, ''), review_sessions.filename),
                    contract_text = COALESCE(NULLIF(EXCLUDED.contract_text, ''), review_sessions.contract_text),
                    document_id = COALESCE(EXCLUDED.document_id, review_sessions.document_id),
                    status = EXCLUDED.status,
                    review_stage = EXCLUDED.review_stage,
                    updated_at = NOW()
                WHERE review_sessions.user_id = EXCLUDED.user_id
                RETURNING *
                """,
                (
                    session_id,
                    user_id,
                    document_id,
                    filename or "",
                    contract_text or "",
                    status,
                    review_stage,
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise PermissionError("无权访问该审查会话")
        conn.commit()
    return _session_from_row(row)


def save_review_result(
    *,
    user_id: str,
    session_id: str,
    filename: str,
    contract_text: str,
    issues: list[dict[str, Any]],
    report_paragraphs: list[str],
    status: str = "complete",
    review_stage: str = "complete",
    error_message: str | None = None,
) -> dict[str, Any]:
    ensure_sync_schema()
    document_id = _get_or_create_session_document(
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        contract_text=contract_text,
    )
    overall_risk, risk_counts = summarize_risks(issues)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_sessions (
                    session_id,
                    user_id,
                    document_id,
                    filename,
                    contract_text,
                    status,
                    review_stage,
                    overall_risk,
                    risk_counts,
                    issues,
                    report_paragraphs,
                    error_message,
                    completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (session_id) DO UPDATE
                SET document_id = COALESCE(EXCLUDED.document_id, review_sessions.document_id),
                    filename = COALESCE(NULLIF(EXCLUDED.filename, ''), review_sessions.filename),
                    contract_text = COALESCE(NULLIF(EXCLUDED.contract_text, ''), review_sessions.contract_text),
                    status = EXCLUDED.status,
                    review_stage = EXCLUDED.review_stage,
                    overall_risk = EXCLUDED.overall_risk,
                    risk_counts = EXCLUDED.risk_counts,
                    issues = EXCLUDED.issues,
                    report_paragraphs = EXCLUDED.report_paragraphs,
                    error_message = EXCLUDED.error_message,
                    completed_at = CASE WHEN EXCLUDED.status = 'complete' THEN NOW() ELSE review_sessions.completed_at END,
                    updated_at = NOW()
                WHERE review_sessions.user_id = EXCLUDED.user_id
                RETURNING *
                """,
                (
                    session_id,
                    user_id,
                    document_id,
                    filename or "",
                    contract_text or "",
                    status,
                    review_stage,
                    overall_risk,
                    Json(risk_counts),
                    Json(issues),
                    Json(report_paragraphs),
                    error_message,
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise PermissionError("无权访问该审查会话")
            cur.execute("DELETE FROM review_findings WHERE session_id = %s AND user_id = %s", (session_id, user_id))
            for issue in issues:
                cur.execute(
                    """
                    INSERT INTO review_findings (
                        session_id, user_id, clause, issue, level, risk_level,
                        suggestion, legal_reference, matched_text, payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        user_id,
                        str(issue.get("clause") or ""),
                        str(issue.get("issue") or ""),
                        _risk_level(issue),
                        int(issue.get("risk_level") or 0),
                        str(issue.get("suggestion") or ""),
                        str(issue.get("legal_reference") or ""),
                        str(issue.get("matched_text") or ""),
                        Json(issue),
                    ),
                )
        conn.commit()
    return _session_from_row(row)


def append_chat_message(
    *,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    status: str = "complete",
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_sync_schema()
    message_id = f"msg-{uuid.uuid4().hex}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (
                    message_id, session_id, user_id, role, content, status, model, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING message_id, session_id, role, content, status, model, metadata, created_at
                """,
                (
                    message_id,
                    session_id,
                    user_id,
                    role,
                    content,
                    status,
                    model,
                    Json(metadata or {}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _chat_message_from_row(row)


def list_documents(user_id: str, *, query: str = "", risk: str = "", limit: int = 50) -> list[dict[str, Any]]:
    ensure_sync_schema()
    filters = ["d.user_id = %s"]
    params: list[Any] = [user_id]
    if query:
        filters.append("(d.filename ILIKE %s OR d.content_text ILIKE %s)")
        params.extend([f"%{query}%", f"%{query}%"])
    if risk:
        filters.append("COALESCE(rs.overall_risk, 'low') = %s")
        params.append(risk)
    params.append(max(1, min(limit, 100)))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    d.document_id,
                    d.user_id,
                    d.filename,
                    d.source_type,
                    d.status,
                    d.warnings,
                    d.created_at,
                    d.updated_at,
                    rs.session_id,
                    rs.status,
                    rs.overall_risk,
                    rs.risk_counts,
                    rs.completed_at
                FROM user_documents d
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM review_sessions rs
                    WHERE rs.document_id = d.document_id
                      AND rs.user_id = d.user_id
                    ORDER BY rs.updated_at DESC
                    LIMIT 1
                ) rs ON TRUE
                WHERE {" AND ".join(filters)}
                ORDER BY COALESCE(rs.updated_at, d.updated_at) DESC
                LIMIT %s
                """,
                params,
            )
            return [_document_summary_from_row(row) for row in cur.fetchall()]


def get_document(user_id: str, document_id: str) -> dict[str, Any] | None:
    ensure_sync_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.document_id,
                    d.user_id,
                    d.filename,
                    d.source_type,
                    d.status,
                    d.warnings,
                    d.created_at,
                    d.updated_at,
                    d.content_text
                FROM user_documents d
                WHERE d.user_id = %s AND d.document_id = %s
                LIMIT 1
                """,
                (user_id, document_id),
            )
            row = cur.fetchone()
    return _document_detail_from_row(row) if row else None


def list_review_sessions(user_id: str, *, query: str = "", risk: str = "", limit: int = 50) -> list[dict[str, Any]]:
    ensure_sync_schema()
    filters = ["user_id = %s"]
    params: list[Any] = [user_id]
    if query:
        filters.append("(filename ILIKE %s OR contract_text ILIKE %s)")
        params.extend([f"%{query}%", f"%{query}%"])
    if risk:
        filters.append("overall_risk = %s")
        params.append(risk)
    params.append(max(1, min(limit, 100)))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM review_sessions
                WHERE {" AND ".join(filters)}
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                params,
            )
            return [_session_from_row(row, summary=True) for row in cur.fetchall()]


def get_review_session(user_id: str, session_id: str) -> dict[str, Any] | None:
    ensure_sync_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM review_sessions WHERE user_id = %s AND session_id = %s LIMIT 1",
                (user_id, session_id),
            )
            row = cur.fetchone()
    return _session_from_row(row) if row else None


def get_chat_messages(user_id: str, session_id: str) -> list[dict[str, Any]]:
    ensure_sync_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_id, session_id, role, content, status, model, metadata, created_at
                FROM chat_messages
                WHERE user_id = %s AND session_id = %s
                ORDER BY created_at ASC
                """,
                (user_id, session_id),
            )
            return [_chat_message_from_row(row) for row in cur.fetchall()]


def _get_or_create_session_document(*, user_id: str, session_id: str, filename: str, contract_text: str) -> str:
    ensure_sync_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM review_sessions WHERE user_id = %s AND session_id = %s",
                (user_id, session_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    document = create_document(
        user_id=user_id,
        filename=filename or "未命名合同",
        content_text=contract_text,
        source_type="review",
        status="reviewed",
    )
    return str(document["id"])


def _document_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "userId": row[1],
        "filename": row[2],
        "sourceType": row[3],
        "status": row[4],
        "warnings": row[5] or [],
        "createdAt": _isoformat(row[6]),
        "updatedAt": _isoformat(row[7]),
    }


def _document_summary_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "userId": row[1],
        "filename": row[2],
        "sourceType": row[3],
        "status": row[4],
        "warnings": row[5] or [],
        "createdAt": _isoformat(row[6]),
        "updatedAt": _isoformat(row[7]),
        "latestReview": {
            "sessionId": row[8],
            "status": row[9],
            "overallRisk": row[10],
            "riskCounts": row[11] or {},
            "completedAt": _isoformat(row[12]),
        } if row[8] else None,
    }


def _document_detail_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "userId": row[1],
        "filename": row[2],
        "sourceType": row[3],
        "status": row[4],
        "warnings": row[5] or [],
        "createdAt": _isoformat(row[6]),
        "updatedAt": _isoformat(row[7]),
        "contentText": row[8] or "",
    }


def _session_from_row(row: tuple[Any, ...], *, summary: bool = False) -> dict[str, Any]:
    payload = {
        "sessionId": row[0],
        "userId": row[1],
        "documentId": row[2],
        "filename": row[3],
        "status": row[5],
        "reviewStage": row[6],
        "overallRisk": row[7],
        "riskCounts": row[8] or {},
        "issues": row[9] or [],
        "reportParagraphs": row[10] or [],
        "extractedInfo": row[11],
        "routingDecision": row[12],
        "initialSummary": row[13],
        "deepUpdateNotice": row[14],
        "breakpointMessage": row[15],
        "errorMessage": row[16],
        "createdAt": _isoformat(row[17]),
        "updatedAt": _isoformat(row[18]),
        "completedAt": _isoformat(row[19]),
    }
    if not summary:
        payload["contractText"] = row[4] or ""
    return payload


def _chat_message_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "sessionId": row[1],
        "role": row[2],
        "content": row[3],
        "status": row[4],
        "model": row[5],
        "metadata": row[6] or {},
        "createdAt": _isoformat(row[7]),
    }
