from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import get_settings


class AliyunSmsError(RuntimeError):
    pass


API_VERSION = "2017-05-25"
API_ENDPOINT = "https://dypnsapi.aliyuncs.com"


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


def _base_params(access_key_id: str, action: str, region_id: str) -> dict[str, str]:
    return {
        "AccessKeyId": access_key_id,
        "Action": action,
        "Format": "JSON",
        "RegionId": region_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": secrets.token_hex(16),
        "SignatureVersion": "1.0",
        "Timestamp": _current_utc_timestamp(),
        "Version": API_VERSION,
    }


def _request(action: str, extra_params: dict[str, str]) -> dict[str, Any]:
    settings = get_settings()
    access_key_id = (settings.aliyun_sms_access_key_id or "").strip()
    access_key_secret = (settings.aliyun_sms_access_key_secret or "").strip()
    endpoint = (settings.aliyun_sms_endpoint or API_ENDPOINT).strip() or API_ENDPOINT

    if not access_key_id or not access_key_secret:
        raise AliyunSmsError("SMS verification service is not configured")

    params = {**_base_params(access_key_id, action, settings.aliyun_sms_region_id), **extra_params}
    query = _build_signed_query(params, access_key_secret)
    request_url = f"{endpoint}/?{query}"

    try:
        response = httpx.get(request_url, timeout=httpx.Timeout(15.0, connect=5.0))
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise AliyunSmsError(f"阿里云短信认证服务调用失败: {exc}") from exc

    if payload.get("Code") != "OK" or payload.get("Success") is False:
        raise AliyunSmsError(payload.get("Message") or "阿里云短信认证服务调用失败")

    return payload


def is_phone_verification_service_configured() -> bool:
    # 短信认证服务只需要 AccessKey，不需要签名和模板
    settings = get_settings()
    return bool(
        (settings.aliyun_sms_access_key_id or "").strip()
        and (settings.aliyun_sms_access_key_secret or "").strip()
    )


def send_phone_verification_code(phone: str, _code: str = "") -> dict[str, Any]:
    """
    发送短信验证码。使用阿里云短信认证服务（dypnsapi），
    验证码由阿里云生成和管理，_code 参数保留用于接口兼容，不传给 Aliyun。
    短信认证服务不需要签名和模板，参数从环境变量读取仅用于日志记录。
    """
    settings = get_settings()

    params: dict[str, str] = {
        "PhoneNumber": phone,
        "CountryCode": "86",
        "CodeLength": "6",
        "ValidTime": "300",
        "DuplicatePolicy": "1",
        "Interval": "60",
        "CodeType": "1",
        "AutoRetry": "1",
    }
    if settings.allow_dev_code_response:
        params["ReturnVerifyCode"] = "true"

    payload = _request("SendSmsVerifyCode", params)
    model = payload.get("Model") or {}
    result: dict[str, Any] = {
        "success": True,
        "request_id": payload.get("RequestId", ""),
        "biz_id": model.get("BizId", ""),
    }
    verify_code = model.get("VerifyCode")
    if isinstance(verify_code, str) and verify_code.strip():
        result["dev_code"] = verify_code.strip()
    return result


def check_phone_verification_code(phone: str, code: str) -> bool:
    """
    通过阿里云短信认证服务验证用户提交的验证码。
    """
    params: dict[str, str] = {
        "PhoneNumber": phone,
        "VerifyCode": code,
        "CountryCode": "86",
        "CaseAuthPolicy": "1",
    }
    try:
        payload = _request("CheckSmsVerifyCode", params)
    except AliyunSmsError:
        return False
    model = payload.get("Model") or {}
    return model.get("VerifyResult") == "PASS"
