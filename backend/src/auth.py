"""
JWT authentication for email/password login plus email verification code flows.

User data persistence strategy:
- PostgreSQL as the primary user store.
- Redis as a cache / fast lookup layer.
- In-memory dict as process-local cache.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import smtplib
import string
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Lock
from typing import Optional

import jwt

from .config import get_settings

# JWT config


def _load_jwt_secret() -> str:
    configured_secret = (get_settings().jwt_secret or "").strip()
    if configured_secret:
        return configured_secret

    generated_secret = secrets.token_hex(32)
    print("[Auth] JWT_SECRET not set; using an ephemeral per-process secret", flush=True)
    return generated_secret


JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# One-time verification code store: email -> {code, expire_at}
_code_store: dict[str, dict] = {}

# Process-local user cache
_user_cache: dict[str, dict] = {}

# Backward-compatible alias used by legacy tests.
_user_store = _user_cache

_REDIS_USER_PREFIX = "contract-review:user:"
_PG_USER_TABLE_READY = False
_PG_USER_TABLE_LOCK = Lock()
_VERIFICATION_CODE_TTL_SECONDS = 300


def _get_redis():
    """Lazy import to avoid circular dependencies at module import time."""
    try:
        from .cache.redis_cache import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _verification_code_cache_key(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"contract-review:auth-code:{digest}"


def _save_code_record(email: str, record: dict) -> None:
    normalized_email = email.strip().lower()
    _code_store[normalized_email] = record

    client = _get_redis()
    if client is None:
        return

    try:
        client.setex(
            _verification_code_cache_key(normalized_email),
            _VERIFICATION_CODE_TTL_SECONDS,
            json.dumps(record, ensure_ascii=False),
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Redis save verification code failed: {exc}")


def _load_code_record(email: str) -> Optional[dict]:
    normalized_email = email.strip().lower()
    record = _code_store.get(normalized_email)
    if record:
        return record

    client = _get_redis()
    if client is None:
        return None

    try:
        raw = client.get(_verification_code_cache_key(normalized_email))
        if not raw:
            return None
        record = json.loads(raw)
        if isinstance(record, dict):
            _code_store[normalized_email] = record
            return record
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Redis load verification code failed: {exc}")

    return None


def _delete_code_record(email: str) -> None:
    normalized_email = email.strip().lower()
    _code_store.pop(normalized_email, None)

    client = _get_redis()
    if client is None:
        return

    try:
        client.delete(_verification_code_cache_key(normalized_email))
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Redis delete verification code failed: {exc}")


def _save_user_to_redis(user_id: str, user: dict) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        client.set(f"{_REDIS_USER_PREFIX}{user_id}", json.dumps(user, ensure_ascii=False))
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Redis save user failed: {exc}")


def _load_user_from_redis(user_id: str) -> Optional[dict]:
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(f"{_REDIS_USER_PREFIX}{user_id}")
        if raw:
            return json.loads(raw)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Redis load user failed: {exc}")
    return None


def _get_pg_connection_factory():
    """Return backend vectorstore connection context manager factory."""
    try:
        from .vectorstore.connection import get_connection

        return get_connection
    except Exception:
        return None


def _format_created_at(created_at: object) -> str:
    if isinstance(created_at, datetime):
        return created_at.isoformat()
    if isinstance(created_at, str) and created_at:
        return created_at
    return datetime.now().isoformat()


def _ensure_pg_user_table() -> bool:
    global _PG_USER_TABLE_READY
    if _PG_USER_TABLE_READY:
        return True

    with _PG_USER_TABLE_LOCK:
        if _PG_USER_TABLE_READY:
            return True

        connection_factory = _get_pg_connection_factory()
        if connection_factory is None:
            return False

        try:
            with connection_factory() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS auth_users (
                            user_id TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            salt TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                conn.commit()

            _PG_USER_TABLE_READY = True
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[Auth] PostgreSQL user table init failed: {exc}")
            return False


def _save_user_to_postgres(user_id: str, user: dict) -> None:
    if not _ensure_pg_user_table():
        return

    connection_factory = _get_pg_connection_factory()
    if connection_factory is None:
        return

    try:
        with connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_users (user_id, email, password_hash, salt, created_at)
                    VALUES (%s, %s, %s, %s, %s::timestamptz)
                    ON CONFLICT (user_id) DO UPDATE
                    SET
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        salt = EXCLUDED.salt
                    """,
                    (
                        user_id,
                        user.get("email", ""),
                        user.get("password_hash", ""),
                        user.get("salt", ""),
                        _format_created_at(user.get("created_at")),
                    ),
                )
            conn.commit()
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] PostgreSQL save user failed: {exc}")


def _load_user_from_postgres(user_id: str) -> Optional[dict]:
    if not _ensure_pg_user_table():
        return None

    connection_factory = _get_pg_connection_factory()
    if connection_factory is None:
        return None

    try:
        with connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email, password_hash, salt, created_at
                    FROM auth_users
                    WHERE user_id = %s
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "email": row[0],
                    "password_hash": row[1],
                    "salt": row[2],
                    "created_at": _format_created_at(row[3]),
                }
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] PostgreSQL load user failed: {exc}")
    return None


def _get_user(user_id: str) -> Optional[dict]:
    """Get user from in-memory cache, Redis, then PostgreSQL."""
    if user_id in _user_cache:
        return _user_cache[user_id]

    user = _load_user_from_redis(user_id)
    if user:
        _user_cache[user_id] = user
        _cache_legacy_user_alias(user_id, user)
        # Opportunistic migration: old Redis-only users are moved to PostgreSQL.
        _save_user_to_postgres(user_id, user)
        return user

    user = _load_user_from_postgres(user_id)
    if user:
        _user_cache[user_id] = user
        _cache_legacy_user_alias(user_id, user)
        _save_user_to_redis(user_id, user)
        return user

    return None


def _cache_legacy_user_alias(user_id: str, user: dict) -> None:
    """Mirror the user under its email local-part for backward-compatible cache lookups."""
    email = (user.get("email") or "").strip().lower()
    if not email:
        return

    alias = email.split("@", 1)[0]
    if not alias or alias == user_id:
        return

    cached = _user_cache.get(alias)
    if cached and cached.get("email") not in ("", email):
        return

    _user_cache[alias] = user


def _put_user(user_id: str, user: dict) -> None:
    """Write-through to memory, Redis and PostgreSQL."""
    _user_cache[user_id] = user
    _cache_legacy_user_alias(user_id, user)
    _save_user_to_redis(user_id, user)
    _save_user_to_postgres(user_id, user)


def _cache_user_without_db(user_id: str, user: dict) -> None:
    """Cache-only write (for JWT recovery / legacy no-password paths)."""
    _user_cache[user_id] = user
    _cache_legacy_user_alias(user_id, user)
    _save_user_to_redis(user_id, user)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _make_user_id(email: str) -> str:
    return email.split("@")[0] + "_" + hashlib.md5(email.encode()).hexdigest()[:6]


def generate_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def send_verification_code(email: str) -> dict:
    code = generate_code()
    expire_at = time.time() + _VERIFICATION_CODE_TTL_SECONDS
    _save_code_record(email, {"code": code, "expire_at": expire_at})

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user:
        print(f"[Auth] Dev mode - verification code for {email}: {code}")
        return {"success": True, "dev_code": code}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[Contract Review Copilot] Verification Code"
        msg["From"] = from_email
        msg["To"] = email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <h1 style="color: #ff8c00; font-size: 20px;">Contract Review Copilot</h1>
            <p>Your verification code:</p>
            <div style="background: #ff8c00; color: white; font-size: 32px; font-weight: 700;
                letter-spacing: 8px; padding: 16px 32px; text-align: center;">{code}</div>
            <p style="color: #888; font-size: 12px;">Code expires in 5 minutes.</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [email], msg.as_string())

        return {"success": True}
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[Auth] Failed to send email: {exc}")
        print(f"[Auth] Dev fallback - verification code for {email}: {code}")
        return {"success": True, "dev_code": code}


def verify_code_only(email: str, code: str) -> bool:
    record = _load_code_record(email)
    if not record:
        return False
    if time.time() > record["expire_at"]:
        _delete_code_record(email)
        return False
    return hmac.compare_digest(str(record["code"]), str(code))


def consume_code(email: str, code: str) -> bool:
    if not verify_code_only(email, code):
        return False
    _delete_code_record(email)
    return True


def register_user(email: str, code: str, password: str) -> dict:
    """
    Register a new user with email verification.
    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    user_id = _make_user_id(email)
    if _get_user(user_id) is not None:
        return {"success": False, "error": "该邮箱已注册，请直接登录"}

    if not consume_code(email, code):
        return {"success": False, "error": "验证码无效或已过期"}

    if len(password) < 6:
        return {"success": False, "error": "密码不能少于6位"}

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    user = {
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "created_at": datetime.now().isoformat(),
    }
    _put_user(user_id, user)

    print(f"[Auth] Registered new user: {email}")
    return {"success": True}


def login_with_password(email: str, password: str) -> Optional[str]:
    """Authenticate with email + password. Returns JWT token or None."""
    user_id = _make_user_id(email)
    user = _get_user(user_id)
    if not user:
        return None

    expected = _hash_password(password, user.get("salt", ""))
    if not hmac.compare_digest(expected, user.get("password_hash", "")):
        return None

    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "iat": datetime.utcnow(),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def verify_code(email: str, code: str) -> Optional[str]:
    """
    Legacy code-only login path for backward compatibility.
    """
    if not consume_code(email, code):
        return None

    user_id = _make_user_id(email)
    if _get_user(user_id) is None:
        recovered = {
            "email": email,
            "password_hash": "",
            "salt": "",
            "created_at": datetime.now().isoformat(),
        }
        _cache_user_without_db(user_id, recovered)

    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": expire, "iat": datetime.utcnow()},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_user_from_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        return None

    user = _get_user(user_id)
    if user:
        return {"id": user_id, "email": user["email"], "created_at": user.get("created_at")}

    recovered = {
        "email": email,
        "password_hash": "",
        "salt": "",
        "created_at": datetime.now().isoformat(),
    }
    _cache_user_without_db(user_id, recovered)
    return {"id": user_id, "email": email, "created_at": recovered["created_at"]}
