from __future__ import annotations

import hashlib
from types import SimpleNamespace

from src import auth


class _FakeOAuthResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


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


def test_reset_password_with_email_code_updates_password_hash(monkeypatch):
    user = {
        "id": "user-1",
        "email": "demo@example.com",
        "password_hash": "old-hash",
        "salt": "legacy",
    }
    captured: dict[str, str] = {}

    monkeypatch.setattr(auth, "get_user_by_id", lambda user_id: user if user_id == "user-1" else None)
    monkeypatch.setattr(
        auth,
        "consume_code",
        lambda email, code, kind="email": (
            email == "demo@example.com"
            and code == "123456"
            and kind == auth.PASSWORD_RESET_CODE_KIND
        ),
    )
    monkeypatch.setattr(auth, "_hash_password", lambda raw_password: f"bcrypt::{raw_password}")
    monkeypatch.setattr(
        auth,
        "update_user_password_credentials",
        lambda user_id, password_hash, salt: captured.update(
            {"user_id": user_id, "password_hash": password_hash, "salt": salt}
        ),
    )
    monkeypatch.setattr(auth, "_build_public_user", lambda current_user: {"id": current_user["id"], "email": current_user["email"]})

    result = auth.reset_password_with_email_code("user-1", "123456", "newSecret123")

    assert result == {"success": True, "user": {"id": "user-1", "email": "demo@example.com"}}
    assert captured == {"user_id": "user-1", "password_hash": "bcrypt::newSecret123", "salt": ""}
    assert user["password_hash"] == "bcrypt::newSecret123"
    assert user["salt"] == ""


def test_reset_password_with_email_code_rejects_user_without_email(monkeypatch):
    monkeypatch.setattr(auth, "get_user_by_id", lambda user_id: {"id": user_id, "email": ""})

    result = auth.reset_password_with_email_code("user-1", "123456", "newSecret123")

    assert result == {"success": False, "error": "当前账号未绑定邮箱，暂不支持邮箱改密"}


def test_login_with_google_creates_user_from_verified_email(monkeypatch):
    captured_post: dict = {}
    captured_get: dict = {}
    created_users: list[dict] = []

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(google_client_id="google-client", google_client_secret="google-secret"),
    )

    def fake_post(url: str, **kwargs):
        captured_post.update({"url": url, **kwargs})
        return _FakeOAuthResponse({"access_token": "google-access-token"})

    def fake_get(url: str, **kwargs):
        captured_get.update({"url": url, **kwargs})
        return _FakeOAuthResponse({"email": "User@Example.com", "email_verified": True})

    def fake_create_email_user(*, user_id: str, email: str, password_hash: str, salt: str):
        user = {"id": user_id, "email": email, "password_hash": password_hash, "salt": salt}
        created_users.append(user)
        return user

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    monkeypatch.setattr(auth.httpx, "get", fake_get)
    monkeypatch.setattr(auth, "get_user_by_email", lambda _email: None)
    monkeypatch.setattr(auth, "create_email_user", fake_create_email_user)
    monkeypatch.setattr(auth, "_create_token", lambda user: f"token-for-{user['email']}")
    monkeypatch.setattr(auth, "_build_public_user", lambda user: {"id": user["id"], "email": user["email"]})

    result = auth.login_with_google("oauth-code", "https://ctsafe.top/gateway/auth/google/callback")

    assert result["success"] is True
    assert result["token"] == "token-for-user@example.com"
    assert result["user"]["email"] == "user@example.com"
    assert created_users[0]["password_hash"] == ""
    assert captured_post["url"] == "https://oauth2.googleapis.com/token"
    assert captured_post["data"]["redirect_uri"] == "https://ctsafe.top/gateway/auth/google/callback"
    assert captured_get["headers"]["Authorization"] == "Bearer google-access-token"


def test_login_with_google_rejects_unverified_email(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(google_client_id="google-client", google_client_secret="google-secret"),
    )
    monkeypatch.setattr(auth.httpx, "post", lambda *_args, **_kwargs: _FakeOAuthResponse({"access_token": "token"}))
    monkeypatch.setattr(
        auth.httpx,
        "get",
        lambda *_args, **_kwargs: _FakeOAuthResponse({"email": "user@example.com", "email_verified": False}),
    )

    result = auth.login_with_google("oauth-code", "https://ctsafe.top/gateway/auth/google/callback")

    assert result == {"success": False, "error": "无法获取已验证的 Google 邮箱"}
