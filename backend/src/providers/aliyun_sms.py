from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timezone

import httpx

from ..config import get_settings


class AliyunSmsError(RuntimeError):
    pass


def _percent_encode(value: str) -> str:
    return urllib.parse.quote(value, safe="~")


def _build_signed_query(params: dict[str, str], access_key_secret: str) -> str:
    sorted_pairs = sorted((key, value) for key, value in params.items())
    canonicalized = "&".join(
        f"{_percent_encode(key)}={_percent_encode(value)}"
        for key, value in sorted_pairs
    )
    string_to_sign = f"GET&%2F&{_percent_encode(canonicalized)}"
    signature = base64.b64encode(
        hmac.new(
            f"{access_key_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")
    return f"Signature={_percent_encode(signature)}&{canonicalized}"


def _current_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_phone_verification_code(phone: str, code: str) -> dict:
    settings = get_settings()
    access_key_id = (settings.aliyun_sms_access_key_id or "").strip()
    access_key_secret = (settings.aliyun_sms_access_key_secret or "").strip()
    sign_name = (settings.aliyun_sms_sign_name or "").strip()
    template_code = (settings.aliyun_sms_template_code or "").strip()
    endpoint = (settings.aliyun_sms_endpoint or "https://dysmsapi.aliyuncs.com").strip()

    if not access_key_id or not access_key_secret or not sign_name or not template_code:
        print(f"[SMS] Dev mode - verification code for {phone}: {code}", flush=True)
        if settings.allow_dev_code_response:
            return {"success": True, "dev_code": code}
        return {"success": False, "error": "SMS verification service is not configured"}

    params = {
        "AccessKeyId": access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": settings.aliyun_sms_region_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": secrets.token_hex(16),
        "SignatureVersion": "1.0",
        "SignName": sign_name,
        "TemplateCode": template_code,
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False, separators=(",", ":")),
        "Timestamp": _current_utc_timestamp(),
        "Version": "2017-05-25",
    }
    query = _build_signed_query(params, access_key_secret)
    request_url = f"{endpoint}/?{query}"

    try:
        response = httpx.get(request_url, timeout=httpx.Timeout(15.0, connect=5.0))
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network/config driven
        raise AliyunSmsError(f"阿里云短信发送失败: {exc}") from exc

    if payload.get("Code") != "OK":
        raise AliyunSmsError(payload.get("Message") or "阿里云短信发送失败")

    return {"success": True, "request_id": payload.get("RequestId", "")}
