from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src import commerce
from src.vectorstore.connection import get_connection


def _delete_user(user_id: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_users WHERE user_id = %s", (user_id,))
        conn.commit()


def _build_test_phone(seed: str) -> str:
    numeric_tail = str(int(seed[:9], 16) % 1_000_000_000).zfill(9)
    return f"13{numeric_tail}"


def test_attach_phone_awards_free_reviews_for_first_phone_bind(monkeypatch):
    commerce.ensure_commerce_schema()

    suffix = uuid4().hex
    user_id = f"email_user_{suffix[:12]}"
    email = f"bind-{suffix[:12]}@example.com"
    phone = _build_test_phone(suffix)

    _delete_user(user_id)

    try:
        created_user = commerce.create_email_user(
            user_id=user_id,
            email=email,
            password_hash="hash",
            salt="salt",
        )
        assert created_user["free_review_remaining"] == 0

        monkeypatch.setattr(commerce, "get_settings", lambda: SimpleNamespace(free_review_count=2))

        updated_user = commerce.attach_phone_to_existing_user(user_id, phone)

        assert updated_user["phone"] == phone
        assert updated_user["phone_verified"] is True
        assert updated_user["free_review_remaining"] == 2
    finally:
        _delete_user(user_id)


def test_account_summary_restores_missing_free_reviews_for_new_phone_account(monkeypatch):
    commerce.ensure_commerce_schema()

    suffix = uuid4().hex
    user_id = f"restored_user_{suffix[:12]}"
    email = f"restore-{suffix[:12]}@example.com"
    phone = _build_test_phone(suffix)

    _delete_user(user_id)

    try:
        monkeypatch.setattr(commerce, "get_settings", lambda: SimpleNamespace(free_review_count=2))

        with get_connection() as conn:
            with conn.cursor() as cur:
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
                    VALUES (%s, %s, '', '', %s, TRUE, TRUE, 'active', 0, NOW(), NOW())
                    """,
                    (user_id, email, phone),
                )
            conn.commit()

        summary = commerce.get_account_summary(user_id)

        assert summary["phoneVerified"] is True
        assert summary["freeReviewRemaining"] == 2
    finally:
        _delete_user(user_id)
