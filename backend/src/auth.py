from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import smtplib
import string
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import httpx
import jwt
from passlib.context import CryptContext

from .commerce import (
    AccountStateError,
    create_email_user,
    get_account_summary,
    get_user_by_email,
    get_user_by_id,
    update_user_password_credentials,
)
from .config import get_settings
from .password_policy import get_password_validation_error


def _load_jwt_secret() -> str:
    settings = get_settings()
    configured_secret = (settings.jwt_secret or "").strip()
    if configured_secret:
        return configured_secret

    secret_file = (settings.jwt_secret_file or "").strip()
    if not secret_file:
        secret_file = str(Path(__file__).resolve().parents[1] / ".runtime" / "jwt_secret")

    path = Path(secret_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        persisted_secret = path.read_text(encoding="utf-8").strip()
        if persisted_secret:
            return persisted_secret

    generated_secret = secrets.token_hex(32)
    path.write_text(generated_secret, encoding="utf-8")
    print(f"[Auth] JWT secret persisted to {path}", flush=True)
    return generated_secret


JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

_code_store: dict[str, dict] = {}
_user_cache: dict[str, dict] = {}
_PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD_RESET_CODE_KIND = "password_reset"


def _get_redis():
    try:
        from .cache.redis_cache import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _code_cache_key(kind: str, identifier: str) -> str:
    digest = hashlib.sha256(f"{kind}:{identifier}".encode("utf-8")).hexdigest()
    return f"contract-review:auth-code:{digest}"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _code_store_key(kind: str, identifier: str) -> str:
    return f"{kind}:{identifier}"


def _purge_expired_code_records(now: float | None = None) -> None:
    current_time = now or time.time()
    expired_keys = [
        key
        for key, record in _code_store.items()
        if current_time > float(record.get("expire_at", 0) or 0)
    ]
    for key in expired_keys:
        _code_store.pop(key, None)


def _save_code_record(kind: str, identifier: str, record: dict) -> None:
    _purge_expired_code_records()
    store_key = _code_store_key(kind, identifier)
    _code_store[store_key] = record

    client = _get_redis()
    if client is None:
        return

    try:
        client.setex(
            _code_cache_key(kind, identifier),
            get_settings().redis_auth_code_ttl_seconds,
            json.dumps(record, ensure_ascii=False),
        )
    except Exception as exc:
        print(f"[Auth] Redis save verification code failed: {exc}", flush=True)


def _load_code_record(kind: str, identifier: str) -> Optional[dict]:
    _purge_expired_code_records()
    store_key = _code_store_key(kind, identifier)
    record = _code_store.get(store_key)
    if record:
        return record

    client = _get_redis()
    if client is None:
        return None

    try:
        raw = client.get(_code_cache_key(kind, identifier))
        if not raw:
            return None
        record = json.loads(raw)
        if isinstance(record, dict):
            _code_store[store_key] = record
            return record
    except Exception as exc:
        print(f"[Auth] Redis load verification code failed: {exc}", flush=True)

    return None


def _delete_code_record(kind: str, identifier: str) -> None:
    _code_store.pop(_code_store_key(kind, identifier), None)

    client = _get_redis()
    if client is None:
        return

    try:
        client.delete(_code_cache_key(kind, identifier))
    except Exception as exc:
        print(f"[Auth] Redis delete verification code failed: {exc}", flush=True)


def _hash_password(password: str) -> str:
    return _PASSWORD_CONTEXT.hash(password)


def _verify_password(password: str, user: dict) -> bool:
    stored_hash = str(user.get("password_hash", "") or "")
    if not stored_hash:
        return False

    if stored_hash.startswith("$2"):
        return bool(_PASSWORD_CONTEXT.verify(password, stored_hash))

    legacy_hash = hashlib.sha256((str(user.get("salt", "")) + password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, stored_hash)


def _maybe_upgrade_legacy_password_hash(user: dict, password: str) -> None:
    stored_hash = str(user.get("password_hash", "") or "")
    if not stored_hash or stored_hash.startswith("$2"):
        return

    new_hash = _hash_password(password)
    update_user_password_credentials(str(user["id"]), new_hash, "")
    user["password_hash"] = new_hash
    user["salt"] = ""


def _make_email_user_id(email: str) -> str:
    normalized_email = _normalize_email(email)
    alias = normalized_email.split("@")[0] or "user"
    safe_alias = "".join(ch for ch in alias if ch.isalnum() or ch in {"-", "_"})[:24] or "user"
    return f"{safe_alias}_{secrets.token_hex(8)}"


def _cache_legacy_aliases(user: dict) -> None:
    user_id = user["id"]
    _user_cache[user_id] = user

    email = (user.get("email") or "").strip().lower()
    if email:
        local_alias = email.split("@", 1)[0]
        if local_alias:
            _user_cache[local_alias] = user


def _get_user(user_id: str) -> Optional[dict]:
    cached = _user_cache.get(user_id)
    if cached:
        return cached

    user = get_user_by_id(user_id)
    if user:
        _cache_legacy_aliases(user)
    return user


def _build_public_user(user: dict) -> dict:
    summary = get_account_summary(user["id"])
    summary["email"] = user.get("email")
    summary["hasPassword"] = bool((user.get("password_hash") or "").strip())
    return summary


def _create_token(user: dict) -> str:
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user["id"],
        "email": user.get("email"),
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def generate_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _send_email_code(email: str, code: str) -> dict:
    settings = get_settings()
    smtp_host = (settings.smtp_host or "").strip()
    smtp_user = (settings.smtp_user or "").strip()
    smtp_port = int(settings.smtp_port or 587)
    smtp_password = (settings.smtp_password or "").strip()
    from_email = (settings.from_email or smtp_user).strip()

    if not smtp_host or not smtp_user:
        print(f"[Auth] Dev mode - verification code for {email}: {code}", flush=True)
        if settings.allow_dev_code_response:
            return {"success": True, "dev_code": code}
        return {"success": False, "error": "Email verification service is not configured"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[Contract Review Copilot] Verification Code"
        msg["From"] = from_email
        msg["To"] = email
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <h1 style="color: #006a35; font-size: 20px;">合规智审 Copilot</h1>
            <p>您的验证码：</p>
            <div style="background: #006a35; color: white; font-size: 32px; font-weight: 700;
                letter-spacing: 8px; padding: 16px 32px; text-align: center;">{code}</div>
            <p style="color: #888; font-size: 12px;">验证码 5 分钟内有效。</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [email], msg.as_string())
        return {"success": True}
    except Exception as exc:
        print(f"[Auth] Failed to send email: {exc}", flush=True)
        return {"success": False, "error": "Failed to send verification email"}


def _send_code_with_kind(identifier: str, *, kind: str) -> dict:
    normalized_identifier = _normalize_email(identifier)
    code = generate_code()
    expire_at = time.time() + get_settings().redis_auth_code_ttl_seconds
    _save_code_record(kind, normalized_identifier, {"code": code, "expire_at": expire_at})
    result = _send_email_code(normalized_identifier, code)
    if not result.get("success"):
        _delete_code_record(kind, normalized_identifier)
    return result


def send_verification_code(email: str) -> dict:
    return _send_code_with_kind(email, kind="email")


def send_password_reset_code_for_user(user_id: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "error": "用户不存在"}

    email = _normalize_email(str(user.get("email") or ""))
    if not email:
        return {"success": False, "error": "当前账号未绑定邮箱，暂不支持邮箱改密"}

    return _send_code_with_kind(email, kind=PASSWORD_RESET_CODE_KIND)


def send_password_reset_code_for_email(email: str) -> dict:
    normalized_email = _normalize_email(email)
    user = get_user_by_email(normalized_email)
    if not user:
        return {"success": True, "sent": False}

    user_email = _normalize_email(str(user.get("email") or ""))
    if not user_email:
        return {"success": True, "sent": False}

    result = _send_code_with_kind(user_email, kind=PASSWORD_RESET_CODE_KIND)
    return {"sent": True, **result}


def verify_code_only(identifier: str, code: str, *, kind: str = "email") -> bool:
    normalized_identifier = _normalize_email(identifier)
    record = _load_code_record(kind, normalized_identifier)
    if not record:
        return False
    if time.time() > float(record.get("expire_at", 0)):
        _delete_code_record(kind, normalized_identifier)
        return False
    return hmac.compare_digest(str(record.get("code", "")), str(code))


def consume_code(identifier: str, code: str, *, kind: str = "email") -> bool:
    normalized_identifier = _normalize_email(identifier)
    if not verify_code_only(normalized_identifier, code, kind=kind):
        return False
    _delete_code_record(kind, normalized_identifier)
    return True


def register_user(email: str, code: str, password: str) -> dict:
    normalized_email = _normalize_email(email)
    if get_user_by_email(normalized_email):
        return {"success": False, "error": "该邮箱已注册，请直接登录"}

    if not consume_code(normalized_email, code, kind="email"):
        return {"success": False, "error": "验证码无效或已过期"}

    password_error = get_password_validation_error(password)
    if password_error:
        return {"success": False, "error": password_error}

    password_hash = _hash_password(password)
    try:
        user = create_email_user(
            user_id=_make_email_user_id(normalized_email),
            email=normalized_email,
            password_hash=password_hash,
            salt="",
        )
    except AccountStateError as exc:
        return {"success": False, "error": str(exc)}

    _cache_legacy_aliases(user)
    return {"success": True, "user": _build_public_user(user)}


def login_with_password(email: str, password: str) -> Optional[str]:
    normalized_email = _normalize_email(email)
    user = get_user_by_email(normalized_email)
    if not user:
        return None

    if not _verify_password(password, user):
        return None

    _maybe_upgrade_legacy_password_hash(user, password)
    _cache_legacy_aliases(user)
    return _create_token(user)


def login_with_github(code: str) -> dict:
    settings = get_settings()
    client_id = (settings.github_client_id or "").strip()
    client_secret = (settings.github_client_secret or "").strip()
    if not client_id or not client_secret:
        return {"success": False, "error": "GitHub OAuth 未配置"}

    try:
        token_response = httpx.post(
            "https://github.com/login/oauth/access_token",
            json={"client_id": client_id, "client_secret": client_secret, "code": code},
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return {"success": False, "error": "GitHub 授权失败，请重试"}

        emails_response = httpx.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10.0,
        )
        emails = emails_response.json()
        primary_email = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        if not primary_email:
            primary_email = next((e["email"] for e in emails if e.get("verified")), None)
        if not primary_email:
            return {"success": False, "error": "无法获取 GitHub 邮箱，请在 GitHub 设置中公开你的邮箱"}
    except Exception as exc:
        print(f"[Auth] GitHub OAuth failed: {exc}", flush=True)
        return {"success": False, "error": "GitHub 登录失败，请稍后重试"}

    normalized_email = _normalize_email(primary_email)
    user = get_user_by_email(normalized_email)
    if not user:
        try:
            user = create_email_user(
                user_id=_make_email_user_id(normalized_email),
                email=normalized_email,
                password_hash="",
                salt="",
            )
        except AccountStateError:
            user = get_user_by_email(normalized_email)
    if not user:
        return {"success": False, "error": "创建账户失败"}

    _cache_legacy_aliases(user)
    return {
        "success": True,
        "token": _create_token(user),
        "user": _build_public_user(user),
    }


def reset_password_with_email_code(user_id: str, code: str, new_password: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "error": "用户不存在"}

    email = _normalize_email(str(user.get("email") or ""))
    if not email:
        return {"success": False, "error": "当前账号未绑定邮箱，暂不支持邮箱改密"}

    password_error = get_password_validation_error(new_password)
    if password_error:
        return {"success": False, "error": password_error}

    if not consume_code(email, code.strip(), kind=PASSWORD_RESET_CODE_KIND):
        return {"success": False, "error": "验证码无效或已过期"}

    password_hash = _hash_password(new_password.strip())
    update_user_password_credentials(str(user["id"]), password_hash, "")
    user["password_hash"] = password_hash
    user["salt"] = ""
    _cache_legacy_aliases(user)
    return {"success": True, "user": _build_public_user(user)}


def reset_password_by_email_code(email: str, code: str, new_password: str) -> dict:
    normalized_email = _normalize_email(email)
    password_error = get_password_validation_error(new_password)
    if password_error:
        return {"success": False, "error": password_error}

    user = get_user_by_email(normalized_email)
    if not user:
        return {"success": False, "error": "验证码无效或已过期"}

    if not consume_code(normalized_email, code.strip(), kind=PASSWORD_RESET_CODE_KIND):
        return {"success": False, "error": "验证码无效或已过期"}

    password_hash = _hash_password(new_password.strip())
    update_user_password_credentials(str(user["id"]), password_hash, "")
    user["password_hash"] = password_hash
    user["salt"] = ""
    _cache_legacy_aliases(user)
    return {"success": True}


def verify_code(email: str, code: str) -> Optional[str]:
    normalized_email = _normalize_email(email)
    if not consume_code(normalized_email, code, kind="email"):
        return None

    user = get_user_by_email(normalized_email)
    if not user:
        try:
            user = create_email_user(
                user_id=_make_email_user_id(normalized_email),
                email=normalized_email,
                password_hash="",
                salt="",
            )
        except AccountStateError:
            user = get_user_by_email(normalized_email)
    if not user:
        return None

    _cache_legacy_aliases(user)
    return _create_token(user)


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
    if not user_id:
        return None

    user = _get_user(user_id)
    if not user:
        return None

    return _build_public_user(user)
