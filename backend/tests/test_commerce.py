from __future__ import annotations

from datetime import datetime, timezone

from src import commerce


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params or ()))

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, row):
        self.cursor_instance = _FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


def test_user_from_row_normalizes_database_fields():
    created_at = datetime(2026, 4, 9, tzinfo=timezone.utc)
    updated_at = datetime(2026, 4, 10, tzinfo=timezone.utc)

    user = commerce._user_from_row((
        "user-1",
        "demo@example.com",
        True,
        "13800138000",
        False,
        "hash",
        "",
        "active",
        created_at,
        updated_at,
    ))

    assert user == {
        "id": "user-1",
        "email": "demo@example.com",
        "email_verified": True,
        "phone": "13800138000",
        "phone_verified": False,
        "password_hash": "hash",
        "salt": "",
        "account_status": "active",
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def test_account_summary_uses_current_user_fields(monkeypatch):
    created_at = datetime(2026, 4, 9, tzinfo=timezone.utc)
    row = (
        "user-1",
        "demo@example.com",
        True,
        None,
        False,
        "hash",
        "",
        "active",
        created_at,
        created_at,
    )

    monkeypatch.setattr(commerce, "ensure_commerce_schema", lambda: None)
    monkeypatch.setattr(commerce, "get_connection", lambda: _FakeConnection(row))

    summary = commerce.get_account_summary("user-1")

    assert summary == {
        "id": "user-1",
        "email": "demo@example.com",
        "emailVerified": True,
        "accountStatus": "active",
        "createdAt": created_at.isoformat(),
    }
