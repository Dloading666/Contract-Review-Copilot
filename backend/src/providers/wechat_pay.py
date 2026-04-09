from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509 import load_pem_x509_certificate

from ..config import get_settings


class WechatPayError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeOrderResult:
    order_id: str
    code_url: str
    response_payload: dict[str, Any]


def _load_private_key():
    settings = get_settings()
    pem = (settings.wechat_pay_private_key_pem or "").strip()
    path = (settings.wechat_pay_private_key_path or "").strip()
    if not pem and path:
        with open(path, "rb") as file:
            pem = file.read().decode("utf-8")
    if not pem:
        raise WechatPayError("缺少微信支付商户私钥配置")
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


def _load_platform_public_key():
    settings = get_settings()
    pem = (settings.wechat_pay_platform_cert_pem or "").strip()
    path = (settings.wechat_pay_platform_cert_path or "").strip()
    if not pem and path:
        with open(path, "rb") as file:
            pem = file.read().decode("utf-8")
    if not pem:
        raise WechatPayError("缺少微信支付平台证书配置")
    certificate = load_pem_x509_certificate(pem.encode("utf-8"))
    return certificate.public_key()


def _sign_message(message: str) -> str:
    private_key = _load_private_key()
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _build_authorization(method: str, path: str, body: str) -> str:
    settings = get_settings()
    mchid = (settings.wechat_pay_mchid or "").strip()
    serial_no = (settings.wechat_pay_serial_no or "").strip()
    if not mchid or not serial_no:
        raise WechatPayError("缺少微信支付商户号或证书序列号配置")

    timestamp = str(int(time.time()))
    nonce_str = secrets.token_hex(16)
    message = f"{method}\n{path}\n{timestamp}\n{nonce_str}\n{body}\n"
    signature = _sign_message(message)
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{mchid}",'
        f'nonce_str="{nonce_str}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{serial_no}"'
    )


def _api_base_url() -> str:
    settings = get_settings()
    return (settings.wechat_pay_api_base_url or "https://api.mch.weixin.qq.com").rstrip("/")


def _notify_url() -> str:
    settings = get_settings()
    notify_url = (settings.wechat_pay_notify_url or "").strip()
    if not notify_url:
        raise WechatPayError("缺少微信支付回调地址配置")
    return notify_url


def create_native_order(order_id: str, amount_fen: int, description: str) -> NativeOrderResult:
    settings = get_settings()
    appid = (settings.wechat_pay_appid or "").strip()
    mchid = (settings.wechat_pay_mchid or "").strip()
    if not appid or not mchid:
        raise WechatPayError("缺少微信支付 appid 或 mchid 配置")

    path = "/v3/pay/transactions/native"
    payload = {
        "appid": appid,
        "mchid": mchid,
        "description": description,
        "out_trade_no": order_id,
        "notify_url": _notify_url(),
        "amount": {
            "total": amount_fen,
            "currency": "CNY",
        },
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    authorization = _build_authorization("POST", path, body)

    response = httpx.post(
        f"{_api_base_url()}{path}",
        content=body.encode("utf-8"),
        headers={
            "Authorization": authorization,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "contract-review-copilot/1.0",
        },
        timeout=httpx.Timeout(20.0, connect=5.0),
    )

    try:
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network/config driven
        detail = response.text if response.text else str(exc)
        raise WechatPayError(f"微信支付下单失败: {detail}") from exc

    payload = response.json()
    code_url = payload.get("code_url")
    if not code_url:
        raise WechatPayError("微信支付未返回 code_url")

    return NativeOrderResult(order_id=order_id, code_url=code_url, response_payload=payload)


def query_order_by_out_trade_no(order_id: str) -> dict[str, Any]:
    settings = get_settings()
    mchid = (settings.wechat_pay_mchid or "").strip()
    if not mchid:
        raise WechatPayError("缺少微信支付 mchid 配置")

    path = f"/v3/pay/transactions/out-trade-no/{order_id}?mchid={mchid}"
    authorization = _build_authorization("GET", path, "")

    response = httpx.get(
        f"{_api_base_url()}{path}",
        headers={
            "Authorization": authorization,
            "Accept": "application/json",
            "User-Agent": "contract-review-copilot/1.0",
        },
        timeout=httpx.Timeout(20.0, connect=5.0),
    )

    try:
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network/config driven
        detail = response.text if response.text else str(exc)
        raise WechatPayError(f"查询微信支付订单失败: {detail}") from exc

    return response.json()


def _verify_callback_signature(
    headers: dict[str, str],
    body: bytes,
) -> None:
    timestamp = headers.get("wechatpay-timestamp", "")
    nonce = headers.get("wechatpay-nonce", "")
    signature = headers.get("wechatpay-signature", "")
    serial = headers.get("wechatpay-serial", "")
    settings = get_settings()
    configured_serial = (settings.wechat_pay_platform_serial_no or "").strip()

    if not timestamp or not nonce or not signature or not serial:
        raise WechatPayError("缺少微信支付回调签名头")
    if configured_serial and serial != configured_serial:
        raise WechatPayError("微信支付平台证书序列号不匹配")

    message = f"{timestamp}\n{nonce}\n{body.decode('utf-8')}\n".encode("utf-8")
    public_key = _load_platform_public_key()
    try:
        public_key.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:  # pragma: no cover - crypto/config driven
        raise WechatPayError("微信支付回调签名校验失败") from exc


def _decrypt_callback_resource(resource: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    api_v3_key = (settings.wechat_pay_api_v3_key or "").strip()
    if len(api_v3_key) != 32:
        raise WechatPayError("微信支付 APIv3 Key 必须为 32 位")

    nonce = resource.get("nonce", "")
    ciphertext = resource.get("ciphertext", "")
    associated_data = resource.get("associated_data", "")
    if not nonce or not ciphertext:
        raise WechatPayError("微信支付回调资源内容不完整")

    aesgcm = AESGCM(api_v3_key.encode("utf-8"))
    plaintext = aesgcm.decrypt(
        nonce.encode("utf-8"),
        base64.b64decode(ciphertext),
        associated_data.encode("utf-8"),
    )
    return json.loads(plaintext.decode("utf-8"))


def parse_payment_callback(headers: dict[str, str], body: bytes) -> dict[str, Any]:
    _verify_callback_signature(headers, body)
    payload = json.loads(body.decode("utf-8"))
    resource = payload.get("resource")
    if not isinstance(resource, dict):
        raise WechatPayError("微信支付回调缺少 resource 字段")
    payment_data = _decrypt_callback_resource(resource)
    return {
        "event_type": payload.get("event_type", ""),
        "resource_type": payload.get("resource_type", ""),
        "payment": payment_data,
        "raw_payload": payload,
    }
