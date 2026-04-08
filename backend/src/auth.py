"""
JWT Authentication — email+password login, email code registration.
Users are persisted in Redis so they survive backend restarts.
"""
import hashlib
import json
import os
import jwt
import smtplib
import random
import secrets
import string
import time
from datetime import datetime, timedelta
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# JWT config
JWT_SECRET = os.getenv("JWT_SECRET", "contract-review-copilot-secret-2024")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# In-memory code store: email -> {code, expire_at}
_code_store: dict[str, dict] = {}

# In-memory user cache (write-through to Redis)
_user_cache: dict[str, dict] = {}

_REDIS_USER_PREFIX = "contract-review:user:"


# ── Redis helpers (lazy import to avoid circular deps) ────────────────────────

def _get_redis():
    try:
        from .cache.redis_cache import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _save_user_to_redis(user_id: str, user: dict) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        client.set(f"{_REDIS_USER_PREFIX}{user_id}", json.dumps(user, ensure_ascii=False))
    except Exception as e:
        print(f"[Auth] Redis save user failed: {e}")


def _load_user_from_redis(user_id: str) -> Optional[dict]:
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(f"{_REDIS_USER_PREFIX}{user_id}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        print(f"[Auth] Redis load user failed: {e}")
    return None


def _get_user(user_id: str) -> Optional[dict]:
    """Get user from cache or Redis."""
    if user_id in _user_cache:
        return _user_cache[user_id]
    user = _load_user_from_redis(user_id)
    if user:
        _user_cache[user_id] = user
    return user


def _put_user(user_id: str, user: dict) -> None:
    """Save user to cache and Redis."""
    _user_cache[user_id] = user
    _save_user_to_redis(user_id, user)


# ── Password helpers ──────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _make_user_id(email: str) -> str:
    return email.split("@")[0] + "_" + hashlib.md5(email.encode()).hexdigest()[:6]


# ── Verification code ─────────────────────────────────────────────────────────

def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def send_verification_code(email: str) -> dict:
    code = generate_code()
    expire_at = time.time() + 300  # 5 minutes
    _code_store[email] = {"code": code, "expire_at": expire_at}

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user:
        print(f"[Auth] Dev mode — verification code for {email}: {code}")
        return {"success": True, "dev_code": code}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【合规智审 Copilot】邮箱验证码"
        msg["From"] = from_email
        msg["To"] = email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <h1 style="color: #ff8c00; font-size: 20px;">Doge 合规助手</h1>
            <p>您的注册验证码为：</p>
            <div style="background: #ff8c00; color: white; font-size: 32px; font-weight: 700;
                letter-spacing: 8px; padding: 16px 32px; text-align: center;">{code}</div>
            <p style="color: #888; font-size: 12px;">验证码 5 分钟内有效，请勿告知他人。</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [email], msg.as_string())

        return {"success": True}
    except Exception as e:
        print(f"[Auth] Failed to send email: {e}")
        print(f"[Auth] Dev mode — verification code for {email}: {code}")
        return {"success": True, "dev_code": code}


def verify_code_only(email: str, code: str) -> bool:
    """Check code without consuming it (for registration pre-check)."""
    record = _code_store.get(email)
    if not record:
        return False
    if time.time() > record["expire_at"]:
        del _code_store[email]
        return False
    return record["code"] == code


def consume_code(email: str, code: str) -> bool:
    """Verify and consume a code (one-time use)."""
    if not verify_code_only(email, code):
        return False
    del _code_store[email]
    return True


# ── Registration ──────────────────────────────────────────────────────────────

def register_user(email: str, code: str, password: str) -> dict:
    """
    Register a new user with email verification.
    Returns {"success": True} or {"success": False, "error": "..."}
    """
    if not consume_code(email, code):
        return {"success": False, "error": "验证码无效或已过期"}

    user_id = _make_user_id(email)
    if _get_user(user_id) is not None:
        return {"success": False, "error": "该邮箱已注册，请直接登录"}

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


# ── Login with password ───────────────────────────────────────────────────────

def login_with_password(email: str, password: str) -> Optional[str]:
    """
    Authenticate with email + password. Returns JWT token or None.
    """
    user_id = _make_user_id(email)
    user = _get_user(user_id)

    if not user:
        return None

    expected = _hash_password(password, user["salt"])
    if expected != user["password_hash"]:
        return None

    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "iat": datetime.utcnow(),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return token


# ── Legacy code-only login (kept for backwards compat) ───────────────────────

def verify_code(email: str, code: str) -> Optional[str]:
    """Legacy: verify code and return token (no password)."""
    if not consume_code(email, code):
        return None

    user_id = _make_user_id(email)
    if _get_user(user_id) is None:
        salt = secrets.token_hex(16)
        _put_user(user_id, {
            "email": email,
            "password_hash": "",
            "salt": salt,
            "created_at": datetime.now().isoformat(),
        })

    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": user_id, "email": email, "exp": expire, "iat": datetime.utcnow()},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return token


# ── Token helpers ─────────────────────────────────────────────────────────────

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

    # Recover from JWT (after backend restart with no Redis)
    recovered = {"email": email, "password_hash": "", "salt": "", "created_at": datetime.now().isoformat()}
    _put_user(user_id, recovered)
    return {"id": user_id, "email": email, "created_at": recovered["created_at"]}
