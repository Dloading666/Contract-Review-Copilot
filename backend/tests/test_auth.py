from __future__ import annotations

import hashlib
from types import SimpleNamespace

from src import auth


def test_login_with_password_upgrades_legacy_hash(monkeypatch):
    legacy_salt = "legacy-salt"
    password = "Secret123"
    legacy_hash = hashlib.sha256((legacy_salt + password).encode("utf-8")).hexdigest()
    user = {
        "id": "user-1",
        "email": "legacy@example.com",
        "password_hash": legacy_hash,
        "salt": legacy_salt,
    }
    captured: dict[str, str] = {}

    monkeypatch.setattr(auth, "get_user_by_email", lambda email: user if email == "legacy@example.com" else None)
    monkeypatch.setattr(
        auth,
        "update_user_password_credentials",
        lambda user_id, password_hash, salt: captured.update(
            {"user_id": user_id, "password_hash": password_hash, "salt": salt}
        ),
    )
    monkeypatch.setattr(auth, "_hash_password", lambda raw_password: f"bcrypt::{raw_password}")
    monkeypatch.setattr(auth, "_create_token", lambda current_user: f"token-for-{current_user['id']}")

    token = auth.login_with_password("legacy@example.com", password)

    assert token == "token-for-user-1"
    assert captured["user_id"] == "user-1"
    assert captured["salt"] == ""
    assert captured["password_hash"] == "bcrypt::Secret123"


def test_send_email_code_requires_explicit_dev_flag(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="",
            smtp_user="",
            smtp_port=587,
            smtp_password="",
            from_email="",
            allow_dev_code_response=False,
        ),
    )

    result = auth._send_email_code("demo@example.com", "123456")  # noqa: SLF001 - unit test

    assert result == {"success": False, "error": "Email verification service is not configured"}
