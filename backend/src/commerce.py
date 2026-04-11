from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from .vectorstore.connection import get_connection


class CommerceError(RuntimeError):
    pass


class AccountStateError(CommerceError):
    pass


_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None


def _user_from_row(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "email_verified": bool(row[2]),
        "phone": row[3],
        "phone_verified": bool(row[4]),
        "password_hash": row[5] or "",
        "salt": row[6] or "",
        "account_status": row[7] or "active",
        "created_at": _isoformat(row[8]),
        "updated_at": _isoformat(row[9]),
    }


def _column_is_not_null(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "NO")


def ensure_commerce_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_users (
                        user_id TEXT PRIMARY KEY,
                        email TEXT UNIQUE,
                        password_hash TEXT NOT NULL DEFAULT '',
                        salt TEXT NOT NULL DEFAULT '',
                        phone TEXT UNIQUE,
                        email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                        phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
                        account_status TEXT NOT NULL DEFAULT 'active',
                        free_review_remaining INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                if _column_is_not_null(cur, "auth_users", "email"):
                    cur.execute("ALTER TABLE auth_users ALTER COLUMN email DROP NOT NULL")
                cur.execute("ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS phone TEXT UNIQUE")
                cur.execute(
                    "ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cur.execute(
                    "ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cur.execute(
                    "ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active'"
                )
                cur.execute(
                    "ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS free_review_remaining INTEGER NOT NULL DEFAULT 0"
                )
                cur.execute(
                    "ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                )
            conn.commit()

        _SCHEMA_READY = True


_USER_LOOKUP_SQL: dict[Literal["user_id", "email", "phone"], str] = {
    "user_id": "u.user_id = %s",
    "email": "LOWER(u.email) = %s",
    "phone": "u.phone = %s",
}


def _fetch_user(cur, lookup_field: Literal["user_id", "email", "phone"], value: str) -> dict[str, Any] | None:
    where_clause = _USER_LOOKUP_SQL[lookup_field]
    cur.execute(
        f"""
        SELECT
            u.user_id,
            u.email,
            u.email_verified,
            u.phone,
            u.phone_verified,
            u.password_hash,
            u.salt,
            u.account_status,
            u.created_at,
            u.updated_at
        FROM auth_users u
        WHERE {where_clause}
        LIMIT 1
        """,
        (value,),
    )
    return _user_from_row(cur.fetchone())


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _fetch_user(cur, "user_id", user_id)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    ensure_commerce_schema()
    normalized_email = email.strip().lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _fetch_user(cur, "email", normalized_email)



def update_user_password_credentials(user_id: str, password_hash: str, salt: str) -> None:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_users
                    SET password_hash = %s,
                        salt = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (password_hash, salt, user_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def create_email_user(
    *,
    user_id: str,
    email: str,
    password_hash: str,
    salt: str,
) -> dict[str, Any]:
    ensure_commerce_schema()
    normalized_email = email.strip().lower()

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                if _fetch_user(cur, "email", normalized_email):
                    raise AccountStateError("该邮箱已注册，请直接登录")

                cur.execute(
                    """
                    INSERT INTO auth_users (
                        user_id,
                        email,
                        password_hash,
                        salt,
                        email_verified,
                        phone_verified,
                        account_status,
                        free_review_remaining,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, TRUE, FALSE, 'active', 0, NOW(), NOW())
                    """,
                    (user_id, normalized_email, password_hash, salt),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    user = get_user_by_id(user_id)
    if not user:
        raise CommerceError("创建邮箱账户失败")
    return user



def get_account_summary(user_id: str) -> dict[str, Any]:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            user = _fetch_user(cur, "user_id", user_id)
    if not user:
        raise AccountStateError("用户不存在")

    return {
        "id": user["id"],
        "email": user.get("email"),
        "emailVerified": bool(user.get("email_verified")),
        "accountStatus": user.get("account_status", "active"),
        "createdAt": user.get("created_at"),
    }
