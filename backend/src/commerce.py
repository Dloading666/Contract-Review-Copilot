from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from .config import get_settings
from .vectorstore.connection import get_connection


class CommerceError(RuntimeError):
    pass


class AccountStateError(CommerceError):
    pass


class InsufficientFundsError(CommerceError):
    pass


class ResourceNotFoundError(CommerceError):
    pass


@dataclass(frozen=True)
class ChatChargeReservation:
    session_id: str
    user_id: str
    charged_fen: int
    transaction_id: str | None
    question_quota_total: int
    question_quota_used: int
    extra_question_price_fen: int


_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


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
        "free_review_remaining": int(row[8] or 0),
        "created_at": _isoformat(row[9]),
        "updated_at": _isoformat(row[10]),
        "wallet_balance_fen": int(row[11] or 0),
        "must_bind_phone": not bool(row[4]),
    }


def _review_session_from_row(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "review_session_id": row[0],
        "user_id": row[1],
        "filename": row[2] or "",
        "billing_type": row[3],
        "review_price_fen": int(row[4] or 0),
        "wallet_charge_fen": int(row[5] or 0),
        "question_quota_total": int(row[6] or 0),
        "question_quota_used": int(row[7] or 0),
        "extra_question_price_fen": int(row[8] or 0),
        "status": row[9] or "reserved",
        "charge_transaction_id": row[10],
        "charge_refunded": bool(row[11]),
        "error_message": row[12],
        "created_at": _isoformat(row[13]),
        "updated_at": _isoformat(row[14]),
        "contract_excerpt": row[15] or "",
    }


def _order_from_row(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "order_id": row[0],
        "user_id": row[1],
        "amount_fen": int(row[2] or 0),
        "status": row[3],
        "channel": row[4],
        "description": row[5] or "",
        "code_url": row[6] or "",
        "provider_transaction_id": row[7],
        "provider_payload": json.loads(row[8]) if row[8] else None,
        "provider_callback": json.loads(row[9]) if row[9] else None,
        "paid_at": _isoformat(row[10]),
        "created_at": _isoformat(row[11]),
        "updated_at": _isoformat(row[12]),
    }


def _transaction_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "transaction_id": row[0],
        "transaction_type": row[1],
        "amount_fen": int(row[2] or 0),
        "balance_after_fen": int(row[3] or 0),
        "reference_type": row[4] or "",
        "reference_id": row[5] or "",
        "description": row[6] or "",
        "metadata": json.loads(row[7]) if row[7] else None,
        "created_at": _isoformat(row[8]),
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

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_accounts (
                        user_id TEXT PRIMARY KEY REFERENCES auth_users(user_id) ON DELETE CASCADE,
                        balance_fen INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_transactions (
                        transaction_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                        transaction_type TEXT NOT NULL,
                        amount_fen INTEGER NOT NULL,
                        balance_after_fen INTEGER NOT NULL,
                        reference_type TEXT NOT NULL,
                        reference_id TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        metadata_json TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_created
                    ON wallet_transactions (user_id, created_at DESC)
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recharge_orders (
                        order_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                        amount_fen INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        channel TEXT NOT NULL DEFAULT 'wechat_native',
                        description TEXT NOT NULL DEFAULT '',
                        code_url TEXT,
                        provider_transaction_id TEXT,
                        provider_payload_json TEXT,
                        provider_callback_json TEXT,
                        paid_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recharge_orders_user_created
                    ON recharge_orders (user_id, created_at DESC)
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_sessions (
                        review_session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                        filename TEXT NOT NULL DEFAULT '',
                        billing_type TEXT NOT NULL,
                        review_price_fen INTEGER NOT NULL DEFAULT 100,
                        wallet_charge_fen INTEGER NOT NULL DEFAULT 0,
                        question_quota_total INTEGER NOT NULL DEFAULT 15,
                        question_quota_used INTEGER NOT NULL DEFAULT 0,
                        extra_question_price_fen INTEGER NOT NULL DEFAULT 8,
                        status TEXT NOT NULL DEFAULT 'reserved',
                        charge_transaction_id TEXT,
                        charge_refunded BOOLEAN NOT NULL DEFAULT FALSE,
                        error_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        contract_excerpt TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_review_sessions_user_created
                    ON review_sessions (user_id, created_at DESC)
                    """
                )
            conn.commit()

        _SCHEMA_READY = True


def _ensure_wallet_account(conn, user_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wallet_accounts (user_id, balance_fen)
            VALUES (%s, 0)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id,),
        )


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
            u.free_review_remaining,
            u.created_at,
            u.updated_at,
            COALESCE(w.balance_fen, 0)
        FROM auth_users u
        LEFT JOIN wallet_accounts w ON w.user_id = u.user_id
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


def get_user_by_phone(phone: str) -> dict[str, Any] | None:
    ensure_commerce_schema()
    normalized_phone = phone.strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _fetch_user(cur, "phone", normalized_phone)


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


def _restore_initial_free_reviews_if_eligible(user_id: str) -> dict[str, Any] | None:
    ensure_commerce_schema()
    settings = get_settings()

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                user = _fetch_user(cur, "user_id", user_id)
                if not user:
                    return None
                if not user.get("phone_verified") or int(user.get("free_review_remaining", 0)) > 0:
                    return user

                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM review_sessions WHERE user_id = %s)",
                    (user_id,),
                )
                has_review_sessions = bool(cur.fetchone()[0])
                if has_review_sessions:
                    return user

                cur.execute(
                    """
                    UPDATE auth_users
                    SET free_review_remaining = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND phone_verified = TRUE
                      AND COALESCE(free_review_remaining, 0) <= 0
                    """,
                    (settings.free_review_count, user_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return get_user_by_id(user_id)


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
                _ensure_wallet_account(conn, user_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    user = get_user_by_id(user_id)
    if not user:
        raise CommerceError("创建邮箱账户失败")
    return user


def create_phone_user(*, user_id: str, phone: str) -> dict[str, Any]:
    ensure_commerce_schema()
    normalized_phone = phone.strip()
    settings = get_settings()

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                if _fetch_user(cur, "phone", normalized_phone):
                    raise AccountStateError("该手机号已绑定其他账户")

                cur.execute(
                    """
                    INSERT INTO auth_users (
                        user_id,
                        email,
                        password_hash,
                        salt,
                        phone,
                        email_verified,
                        phone_verified,
                        account_status,
                        free_review_remaining,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, NULL, '', '', %s, FALSE, TRUE, 'active', %s, NOW(), NOW())
                    """,
                    (user_id, normalized_phone, settings.free_review_count),
                )
                _ensure_wallet_account(conn, user_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    user = get_user_by_id(user_id)
    if not user:
        raise CommerceError("创建手机号账户失败")
    return user


def attach_phone_to_existing_user(user_id: str, phone: str) -> dict[str, Any]:
    ensure_commerce_schema()
    normalized_phone = phone.strip()
    settings = get_settings()

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                user = _fetch_user(cur, "user_id", user_id)
                if not user:
                    raise ResourceNotFoundError("用户不存在")
                if user.get("phone_verified"):
                    raise AccountStateError("当前账户已绑定手机号")

                existing_phone_owner = _fetch_user(cur, "phone", normalized_phone)
                if existing_phone_owner and existing_phone_owner["id"] != user_id:
                    raise AccountStateError("该手机号已绑定其他账户")

                cur.execute(
                    """
                    UPDATE auth_users
                    SET phone = %s,
                        free_review_remaining = CASE
                            WHEN COALESCE(free_review_remaining, 0) > 0 THEN free_review_remaining
                            ELSE %s
                        END,
                        phone_verified = TRUE,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (normalized_phone, settings.free_review_count, user_id),
                )
                _ensure_wallet_account(conn, user_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    user = get_user_by_id(user_id)
    if not user:
        raise CommerceError("绑定手机号失败")
    return user


def get_account_summary(user_id: str) -> dict[str, Any]:
    user = _restore_initial_free_reviews_if_eligible(user_id)
    if not user:
        raise ResourceNotFoundError("用户不存在")

    return {
        "id": user["id"],
        "email": user.get("email"),
        "emailVerified": bool(user.get("email_verified")),
        "phone": user.get("phone"),
        "phoneVerified": bool(user.get("phone_verified")),
        "accountStatus": user.get("account_status", "active"),
        "freeReviewRemaining": int(user.get("free_review_remaining", 0)),
        "walletBalanceFen": int(user.get("wallet_balance_fen", 0)),
        "mustBindPhone": bool(user.get("must_bind_phone")),
        "createdAt": user.get("created_at"),
    }


def list_wallet_transactions(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    transaction_id,
                    transaction_type,
                    amount_fen,
                    balance_after_fen,
                    reference_type,
                    reference_id,
                    description,
                    metadata_json,
                    created_at
                FROM wallet_transactions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_transaction_from_row(row) for row in cur.fetchall()]


def list_recharge_orders(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    order_id,
                    user_id,
                    amount_fen,
                    status,
                    channel,
                    description,
                    code_url,
                    provider_transaction_id,
                    provider_payload_json,
                    provider_callback_json,
                    paid_at,
                    created_at,
                    updated_at
                FROM recharge_orders
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_order_from_row(row) for row in cur.fetchall()]


def create_recharge_order(
    *,
    user_id: str,
    amount_fen: int,
    description: str,
    code_url: str,
    provider_payload: dict[str, Any] | None = None,
    order_id: str | None = None,
) -> dict[str, Any]:
    ensure_commerce_schema()
    order_id = order_id or f"recharge-{uuid.uuid4().hex}"

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                if not _fetch_user(cur, "user_id", user_id):
                    raise ResourceNotFoundError("用户不存在")
                cur.execute(
                    """
                    INSERT INTO recharge_orders (
                        order_id,
                        user_id,
                        amount_fen,
                        status,
                        channel,
                        description,
                        code_url,
                        provider_payload_json,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, 'pending', 'wechat_native', %s, %s, %s, NOW(), NOW())
                    """,
                    (
                        order_id,
                        user_id,
                        amount_fen,
                        description,
                        code_url,
                        _json_dumps(provider_payload) if provider_payload else None,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    order = get_recharge_order(order_id, user_id=user_id)
    if not order:
        raise CommerceError("创建充值订单失败")
    return order


def get_recharge_order(order_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT
                        order_id,
                        user_id,
                        amount_fen,
                        status,
                        channel,
                        description,
                        code_url,
                        provider_transaction_id,
                        provider_payload_json,
                        provider_callback_json,
                        paid_at,
                        created_at,
                        updated_at
                    FROM recharge_orders
                    WHERE order_id = %s AND user_id = %s
                    LIMIT 1
                    """,
                    (order_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        order_id,
                        user_id,
                        amount_fen,
                        status,
                        channel,
                        description,
                        code_url,
                        provider_transaction_id,
                        provider_payload_json,
                        provider_callback_json,
                        paid_at,
                        created_at,
                        updated_at
                    FROM recharge_orders
                    WHERE order_id = %s
                    LIMIT 1
                    """,
                    (order_id,),
                )
            return _order_from_row(cur.fetchone())


def mark_recharge_order_paid(
    *,
    order_id: str,
    provider_transaction_id: str | None,
    callback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        order_id,
                        user_id,
                        amount_fen,
                        status,
                        channel,
                        description,
                        code_url,
                        provider_transaction_id,
                        provider_payload_json,
                        provider_callback_json,
                        paid_at,
                        created_at,
                        updated_at
                    FROM recharge_orders
                    WHERE order_id = %s
                    FOR UPDATE
                    """,
                    (order_id,),
                )
                order = _order_from_row(cur.fetchone())
                if not order:
                    raise ResourceNotFoundError("充值订单不存在")

                if order["status"] != "paid":
                    cur.execute(
                        """
                        UPDATE recharge_orders
                        SET status = 'paid',
                            provider_transaction_id = COALESCE(%s, provider_transaction_id),
                            provider_callback_json = %s,
                            paid_at = NOW(),
                            updated_at = NOW()
                        WHERE order_id = %s
                        """,
                        (
                            provider_transaction_id,
                            _json_dumps(callback_payload) if callback_payload else None,
                            order_id,
                        ),
                    )
                    _ensure_wallet_account(conn, order["user_id"])
                    cur.execute(
                        """
                        SELECT transaction_id
                        FROM wallet_transactions
                        WHERE reference_type = 'recharge_order'
                          AND reference_id = %s
                          AND transaction_type = 'recharge'
                        LIMIT 1
                        """,
                        (order_id,),
                    )
                    existing_txn = cur.fetchone()
                    if not existing_txn:
                        transaction_id, _ = _change_wallet_balance(
                            cur,
                            user_id=order["user_id"],
                            delta_fen=int(order["amount_fen"]),
                            transaction_type="recharge",
                            reference_type="recharge_order",
                            reference_id=order_id,
                            description=order["description"] or "钱包充值",
                            metadata={"provider_transaction_id": provider_transaction_id},
                        )
                        print(
                            f"[Commerce] Credited recharge order {order_id} via transaction {transaction_id}",
                            flush=True,
                        )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    updated_order = get_recharge_order(order_id)
    if not updated_order:
        raise CommerceError("更新充值订单失败")
    return updated_order


def _change_wallet_balance(
    cur,
    *,
    user_id: str,
    delta_fen: int,
    transaction_type: str,
    reference_type: str,
    reference_id: str,
    description: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, int]:
    cur.execute("SELECT balance_fen FROM wallet_accounts WHERE user_id = %s FOR UPDATE", (user_id,))
    wallet_row = cur.fetchone()
    current_balance = int(wallet_row[0] if wallet_row else 0)
    next_balance = current_balance + delta_fen
    if next_balance < 0:
        raise InsufficientFundsError("钱包余额不足，请先充值")

    cur.execute(
        """
        UPDATE wallet_accounts
        SET balance_fen = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (next_balance, user_id),
    )
    transaction_id = f"txn-{uuid.uuid4().hex}"
    cur.execute(
        """
        INSERT INTO wallet_transactions (
            transaction_id,
            user_id,
            transaction_type,
            amount_fen,
            balance_after_fen,
            reference_type,
            reference_id,
            description,
            metadata_json,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            transaction_id,
            user_id,
            transaction_type,
            delta_fen,
            next_balance,
            reference_type,
            reference_id,
            description,
            _json_dumps(metadata) if metadata else None,
        ),
    )
    return transaction_id, next_balance


def reserve_review_session(
    *,
    user_id: str,
    session_id: str,
    filename: str,
    contract_excerpt: str,
) -> dict[str, Any]:
    ensure_commerce_schema()
    settings = get_settings()

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                user = _fetch_user(cur, "user_id", user_id)
                if not user:
                    raise ResourceNotFoundError("用户不存在")
                if user["account_status"] != "active":
                    raise AccountStateError("当前账户状态不可用")
                if not user["phone_verified"]:
                    raise AccountStateError("请先绑定并验证手机号后再使用完整审查")

                _ensure_wallet_account(conn, user_id)
                charge_transaction_id: str | None = None
                billing_type = "free_review"
                wallet_charge_fen = 0

                cur.execute(
                    "SELECT free_review_remaining FROM auth_users WHERE user_id = %s FOR UPDATE",
                    (user_id,),
                )
                free_row = cur.fetchone()
                free_remaining = int(free_row[0] if free_row else 0)

                if free_remaining > 0:
                    cur.execute(
                        """
                        UPDATE auth_users
                        SET free_review_remaining = free_review_remaining - 1,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (user_id,),
                    )
                else:
                    billing_type = "wallet_paid"
                    wallet_charge_fen = settings.review_price_fen
                    charge_transaction_id, _ = _change_wallet_balance(
                        cur,
                        user_id=user_id,
                        delta_fen=-settings.review_price_fen,
                        transaction_type="review_charge",
                        reference_type="review_session",
                        reference_id=session_id,
                        description="完整合同审查扣费",
                    )

                cur.execute(
                    """
                    INSERT INTO review_sessions (
                        review_session_id,
                        user_id,
                        filename,
                        billing_type,
                        review_price_fen,
                        wallet_charge_fen,
                        question_quota_total,
                        question_quota_used,
                        extra_question_price_fen,
                        status,
                        charge_transaction_id,
                        charge_refunded,
                        error_message,
                        created_at,
                        updated_at,
                        contract_excerpt
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, 0, %s, 'reserved', %s, FALSE, NULL, NOW(), NOW(), %s
                    )
                    ON CONFLICT (review_session_id) DO UPDATE
                    SET filename = EXCLUDED.filename,
                        billing_type = EXCLUDED.billing_type,
                        review_price_fen = EXCLUDED.review_price_fen,
                        wallet_charge_fen = EXCLUDED.wallet_charge_fen,
                        question_quota_total = EXCLUDED.question_quota_total,
                        question_quota_used = 0,
                        extra_question_price_fen = EXCLUDED.extra_question_price_fen,
                        status = 'reserved',
                        charge_transaction_id = EXCLUDED.charge_transaction_id,
                        charge_refunded = FALSE,
                        error_message = NULL,
                        updated_at = NOW(),
                        contract_excerpt = EXCLUDED.contract_excerpt
                    """,
                    (
                        session_id,
                        user_id,
                        filename,
                        billing_type,
                        settings.review_price_fen,
                        wallet_charge_fen,
                        settings.review_question_quota,
                        settings.extra_question_price_fen,
                        charge_transaction_id,
                        contract_excerpt[:500],
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    session = get_review_session(session_id, user_id=user_id)
    if not session:
        raise CommerceError("创建审查会话失败")
    return session


def get_review_session(session_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
    ensure_commerce_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT
                        review_session_id,
                        user_id,
                        filename,
                        billing_type,
                        review_price_fen,
                        wallet_charge_fen,
                        question_quota_total,
                        question_quota_used,
                        extra_question_price_fen,
                        status,
                        charge_transaction_id,
                        charge_refunded,
                        error_message,
                        created_at,
                        updated_at,
                        contract_excerpt
                    FROM review_sessions
                    WHERE review_session_id = %s AND user_id = %s
                    LIMIT 1
                    """,
                    (session_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        review_session_id,
                        user_id,
                        filename,
                        billing_type,
                        review_price_fen,
                        wallet_charge_fen,
                        question_quota_total,
                        question_quota_used,
                        extra_question_price_fen,
                        status,
                        charge_transaction_id,
                        charge_refunded,
                        error_message,
                        created_at,
                        updated_at,
                        contract_excerpt
                    FROM review_sessions
                    WHERE review_session_id = %s
                    LIMIT 1
                    """,
                    (session_id,),
                )
            return _review_session_from_row(cur.fetchone())


def update_review_session_status(session_id: str, status: str, *, error_message: str | None = None) -> None:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE review_sessions
                    SET status = %s,
                        error_message = %s,
                        updated_at = NOW()
                    WHERE review_session_id = %s
                    """,
                    (status, error_message, session_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rollback_reserved_review_session(session_id: str, *, reason: str) -> dict[str, Any] | None:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        review_session_id,
                        user_id,
                        filename,
                        billing_type,
                        review_price_fen,
                        wallet_charge_fen,
                        question_quota_total,
                        question_quota_used,
                        extra_question_price_fen,
                        status,
                        charge_transaction_id,
                        charge_refunded,
                        error_message,
                        created_at,
                        updated_at,
                        contract_excerpt
                    FROM review_sessions
                    WHERE review_session_id = %s
                    FOR UPDATE
                    """,
                    (session_id,),
                )
                session = _review_session_from_row(cur.fetchone())
                if not session:
                    return None
                if session["status"] != "reserved" or session["charge_refunded"]:
                    return session

                if session["billing_type"] == "free_review":
                    cur.execute(
                        """
                        UPDATE auth_users
                        SET free_review_remaining = free_review_remaining + 1,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (session["user_id"],),
                    )
                elif session["wallet_charge_fen"] > 0:
                    _ensure_wallet_account(conn, session["user_id"])
                    _change_wallet_balance(
                        cur,
                        user_id=session["user_id"],
                        delta_fen=session["wallet_charge_fen"],
                        transaction_type="review_refund",
                        reference_type="review_session",
                        reference_id=session_id,
                        description="完整合同审查退款",
                        metadata={"reason": reason},
                    )

                cur.execute(
                    """
                    UPDATE review_sessions
                    SET charge_refunded = TRUE,
                        status = 'failed',
                        error_message = %s,
                        updated_at = NOW()
                    WHERE review_session_id = %s
                    """,
                    (reason, session_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return get_review_session(session_id)


def reserve_chat_turn(user_id: str, session_id: str) -> ChatChargeReservation:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        review_session_id,
                        user_id,
                        filename,
                        billing_type,
                        review_price_fen,
                        wallet_charge_fen,
                        question_quota_total,
                        question_quota_used,
                        extra_question_price_fen,
                        status,
                        charge_transaction_id,
                        charge_refunded,
                        error_message,
                        created_at,
                        updated_at,
                        contract_excerpt
                    FROM review_sessions
                    WHERE review_session_id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (session_id, user_id),
                )
                session = _review_session_from_row(cur.fetchone())
                if not session:
                    raise ResourceNotFoundError("审查会话不存在")
                if session["status"] not in {"reviewing", "awaiting_confirmation", "completed"}:
                    raise AccountStateError("当前审查会话暂不可问答")

                charged_fen = 0
                transaction_id: str | None = None
                next_used = session["question_quota_used"] + 1
                if session["question_quota_used"] >= session["question_quota_total"]:
                    charged_fen = session["extra_question_price_fen"]
                    _ensure_wallet_account(conn, user_id)
                    transaction_id, _ = _change_wallet_balance(
                        cur,
                        user_id=user_id,
                        delta_fen=-charged_fen,
                        transaction_type="chat_charge",
                        reference_type="review_session",
                        reference_id=session_id,
                        description="合同追问扣费",
                    )

                cur.execute(
                    """
                    UPDATE review_sessions
                    SET question_quota_used = %s,
                        updated_at = NOW()
                    WHERE review_session_id = %s
                    """,
                    (next_used, session_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return ChatChargeReservation(
        session_id=session_id,
        user_id=user_id,
        charged_fen=charged_fen,
        transaction_id=transaction_id,
        question_quota_total=session["question_quota_total"],
        question_quota_used=next_used,
        extra_question_price_fen=session["extra_question_price_fen"],
    )


def rollback_chat_turn(reservation: ChatChargeReservation, *, reason: str) -> None:
    ensure_commerce_schema()
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE review_sessions
                    SET question_quota_used = GREATEST(question_quota_used - 1, 0),
                        updated_at = NOW()
                    WHERE review_session_id = %s AND user_id = %s
                    """,
                    (reservation.session_id, reservation.user_id),
                )
                if reservation.charged_fen > 0:
                    _ensure_wallet_account(conn, reservation.user_id)
                    _change_wallet_balance(
                        cur,
                        user_id=reservation.user_id,
                        delta_fen=reservation.charged_fen,
                        transaction_type="chat_refund",
                        reference_type="review_session",
                        reference_id=reservation.session_id,
                        description="合同追问退款",
                        metadata={"reason": reason},
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_chat_session_summary(user_id: str, session_id: str) -> dict[str, Any]:
    session = get_review_session(session_id, user_id=user_id)
    if not session:
        raise ResourceNotFoundError("审查会话不存在")
    return {
        "reviewSessionId": session["review_session_id"],
        "billingType": session["billing_type"],
        "questionQuotaTotal": session["question_quota_total"],
        "questionQuotaUsed": session["question_quota_used"],
        "extraQuestionPriceFen": session["extra_question_price_fen"],
        "reviewPriceFen": session["review_price_fen"],
        "status": session["status"],
    }
