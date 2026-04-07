"""
JWT Authentication — simple email code flow.
"""
import os
import jwt
import smtplib
import random
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

# In-memory code store: email -> {code, expire_at, user_id}
_code_store: dict[str, dict] = {}

# In-memory user store: user_id -> {email, created_at}
_user_store: dict[str, dict] = {}


def generate_code() -> str:
    """Generate a 6-digit verification code."""
    return "".join(random.choices(string.digits, k=6))


def send_verification_code(email: str) -> dict:
    """
    Send a 6-digit verification code to the given email.
    Returns {"success": True} or {"success": False, "error": "..."}
    """
    # Generate code
    code = generate_code()
    expire_at = time.time() + 300  # 5 minutes

    # Store in memory
    _code_store[email] = {
        "code": code,
        "expire_at": expire_at,
    }

    # If no SMTP configured, return code directly (for dev/testing)
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user:
        # Dev mode: print code to logs
        print(f"[Auth] Dev mode — verification code for {email}: {code}")
        return {"success": True, "dev_code": code}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【合规智审 Copilot】您的登录验证码"
        msg["From"] = from_email
        msg["To"] = email

        html_body = f"""
        <div style="font-family: 'Inter', Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #004ac6; font-size: 24px; font-weight: 700; margin: 0;">合规智审 Copilot</h1>
            </div>
            <div style="background: #f7f9fb; border-radius: 12px; padding: 32px; text-align: center;">
                <p style="color: #434655; font-size: 14px; margin: 0 0 24px;">您的登录验证码为：</p>
                <div style="background: #004ac6; color: white; font-size: 32px; font-weight: 700;
                    letter-spacing: 8px; padding: 16px 32px; border-radius: 8px;
                    font-family: 'Courier New', monospace;">{code}</div>
                <p style="color: #737686; font-size: 12px; margin: 24px 0 0;">
                    验证码将在 <strong>5 分钟</strong>后失效，请勿告知他人。
                </p>
            </div>
            <p style="color: #737686; font-size: 12px; text-align: center; margin-top: 24px;">
                如果您未请求此验证码，请忽略此邮件。
            </p>
        </div>
        """

        part = MIMEText(html_body, "html")
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [email], msg.as_string())

        print(f"[Auth] Verification code sent to {email}")
        return {"success": True}

    except Exception as e:
        print(f"[Auth] Failed to send email to {email}: {e}")
        # Fallback: still allow with dev code
        print(f"[Auth] Dev mode — verification code for {email}: {code}")
        return {"success": True, "dev_code": code}


def verify_code(email: str, code: str) -> Optional[str]:
    """
    Verify the code for an email. Returns a JWT token if valid, None otherwise.
    """
    record = _code_store.get(email)
    if not record:
        return None

    if time.time() > record["expire_at"]:
        del _code_store[email]
        return None

    if record["code"] != code:
        return None

    # Code valid — delete it (one-time use)
    del _code_store[email]

    # Get or create user
    user_id = email.split("@")[0]
    if user_id not in _user_store:
        _user_store[user_id] = {
            "email": email,
            "created_at": datetime.now().isoformat(),
        }

    # Generate JWT
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


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload if valid, None otherwise."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_from_token(token: str) -> Optional[dict]:
    """Get user info from a JWT token."""
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        return None

    existing_user = _user_store.get(user_id)
    if existing_user:
        return {
            "id": user_id,
            "email": existing_user.get("email", email),
            "created_at": existing_user.get("created_at"),
        }

    # Recover the user from the JWT payload so persisted tokens remain usable
    # after a backend restart clears the in-memory store.
    recovered_user = {
        "id": user_id,
        "email": email,
        "created_at": datetime.now().isoformat(),
    }
    _user_store[user_id] = recovered_user
    return recovered_user
