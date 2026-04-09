"""
Shared LLM routing for review agents, chat Q&A, and image OCR.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import httpx
from openai import OpenAI

from .config import get_settings

DEFAULT_MODEL_KEY = "kimi"
FALLBACK_MODEL_KEY = "gemma4"

CLOUD_MODEL_LABELS = {
    "glm-5": "GLM-5",
    "minimax": "MiniMax M2.5",
    "qwen": "Qwen 3.5 Plus",
    "kimi": "Kimi K2.5",
}

LOCAL_MODEL_LABELS = {
    "gemma4": "Gemma4（免费模型）",
}

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

DEFAULT_OCR_PROMPT = (
    "请准确提取这张合同图片中的全部可见文字，尽量保留原有段落与换行结构。"
    "不要总结，不要解释，不要补充，不要输出 Markdown 标题或代码块。"
    "看不清的字可以保留原样或用□表示。"
)

OCR_CORRECTION_SYSTEM_PROMPT = (
    "你是合同 OCR 校对助手。"
    "你只能修正明显的错别字、标点、断行、条款编号和阅读顺序问题，"
    "不能总结，不能解释，不能改写合同含义，不能补充原文不存在的内容。"
    "如果某些字词看不清，就保留原样，不要猜测。"
)


@dataclass(frozen=True)
class ResolvedModel:
    key: str
    model_id: str
    label: str
    is_local: bool


def get_primary_model_key() -> str:
    settings = get_settings()
    return (
        os.getenv("PRIMARY_LLM_MODEL_KEY", settings.primary_llm_model_key).strip()
        or DEFAULT_MODEL_KEY
    )


def _cloud_model_ids() -> dict[str, str]:
    settings = get_settings()
    return {
        "glm-5": os.getenv("OPENAI_MODEL", settings.openai_model),
        "minimax": os.getenv("MINIMAX_MODEL", settings.minimax_model),
        "qwen": os.getenv("QWEN_MODEL", settings.qwen_model),
        "kimi": os.getenv("KIMI_MODEL", settings.kimi_model),
    }


def _gemma_model_id() -> str:
    settings = get_settings()
    return os.getenv("GEMMA4_MODEL", settings.gemma4_model)


def _gemma_base_url() -> str:
    settings = get_settings()
    return (
        os.getenv("GEMMA4_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or settings.gemma4_base_url
        or settings.ollama_base_url
    )


def _ollama_api_base_url() -> str:
    base_url = _gemma_base_url().rstrip("/")
    return base_url.removesuffix("/v1")


def _cloud_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or (settings.openai_api_key or ""),
        base_url=os.getenv("OPENAI_BASE_URL") or settings.openai_base_url,
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


def _gemma_client() -> OpenAI:
    return OpenAI(
        api_key="ollama",
        base_url=_gemma_base_url(),
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def available_models() -> list[dict[str, str]]:
    return [{"key": DEFAULT_MODEL_KEY, "label": CLOUD_MODEL_LABELS[DEFAULT_MODEL_KEY]}]


def is_supported_model_key(model_key: str) -> bool:
    return model_key in CLOUD_MODEL_LABELS or model_key in LOCAL_MODEL_LABELS


def resolve_model(model: Optional[str]) -> ResolvedModel:
    requested = (model or get_primary_model_key()).strip()
    cloud_model_ids = _cloud_model_ids()
    gemma_model_id = _gemma_model_id()

    if requested == FALLBACK_MODEL_KEY or requested == gemma_model_id:
        return ResolvedModel(
            key=FALLBACK_MODEL_KEY,
            model_id=gemma_model_id,
            label=LOCAL_MODEL_LABELS[FALLBACK_MODEL_KEY],
            is_local=True,
        )

    if requested in cloud_model_ids:
        return ResolvedModel(
            key=requested,
            model_id=cloud_model_ids[requested],
            label=CLOUD_MODEL_LABELS[requested],
            is_local=False,
        )

    for key, model_id in cloud_model_ids.items():
        if requested == model_id:
            return ResolvedModel(
                key=key,
                model_id=model_id,
                label=CLOUD_MODEL_LABELS[key],
                is_local=False,
            )

    return ResolvedModel(
        key=DEFAULT_MODEL_KEY,
        model_id=requested,
        label=CLOUD_MODEL_LABELS.get(DEFAULT_MODEL_KEY, DEFAULT_MODEL_KEY),
        is_local=False,
    )


def get_client_for_model(model_key: str) -> tuple[OpenAI, str]:
    if model_key == FALLBACK_MODEL_KEY:
        return _gemma_client(), _gemma_model_id()
    if model_key not in _cloud_model_ids():
        raise ValueError(f"Unsupported model key: {model_key}")
    return _cloud_client(), _cloud_model_ids()[model_key]


def _get_client_for_resolved_model(resolved_model: ResolvedModel) -> OpenAI:
    return _gemma_client() if resolved_model.is_local else _cloud_client()


def _chat_completion(client: OpenAI, model_id: str, request_kwargs: dict):
    return client.chat.completions.create(model=model_id, **request_kwargs)


def _ollama_native_chat_completion(model_id: str, request_kwargs: dict):
    timeout_value = float(request_kwargs.get("timeout", 60.0))
    options = {
        "temperature": request_kwargs.get("temperature", 0.1),
        "num_predict": request_kwargs.get("max_tokens", 2048),
    }
    if "top_p" in request_kwargs:
        options["top_p"] = request_kwargs["top_p"]
    if "stop" in request_kwargs:
        options["stop"] = request_kwargs["stop"]

    payload = {
        "model": model_id,
        "messages": request_kwargs["messages"],
        "stream": False,
        "think": False,
        "options": options,
    }

    response = httpx.post(
        f"{_ollama_api_base_url()}/api/chat",
        json=payload,
        timeout=httpx.Timeout(timeout_value, connect=min(timeout_value, 10.0)),
    )
    response.raise_for_status()

    data = response.json()
    message = data.get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        content = (message.get("thinking") or "").strip()
    if not content:
        raise RuntimeError(f"Ollama model {model_id} returned an empty response")

    return SimpleNamespace(
        model=data.get("model", model_id),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=content,
                )
            )
        ],
    )


def normalize_image_mime_type(mime_type: Optional[str], filename: Optional[str] = None) -> str:
    candidate = (mime_type or "").split(";", 1)[0].strip().lower()
    if candidate in SUPPORTED_IMAGE_MIME_TYPES:
        return candidate

    guessed_type, _ = mimetypes.guess_type(filename or "")
    guessed = (guessed_type or "").lower()
    if guessed in SUPPORTED_IMAGE_MIME_TYPES:
        return guessed

    raise ValueError("只支持 JPG、PNG、WEBP 图片格式")


def image_bytes_to_base64(image_bytes: bytes) -> str:
    if not image_bytes:
        raise ValueError("图片内容不能为空")
    return base64.b64encode(image_bytes).decode("ascii")


def _build_image_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{image_bytes_to_base64(image_bytes)}"


def _extract_response_text(response) -> str:
    if not getattr(response, "choices", None):
        return ""

    content = getattr(response.choices[0].message, "content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        fragments: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
        return "\n".join(fragments).strip()

    return ""


def _sanitize_ocr_text(text: str) -> str:
    sanitized = text.strip()
    if sanitized.startswith("```"):
        sanitized = sanitized.strip("`")
        if "\n" in sanitized:
            sanitized = sanitized.split("\n", 1)[1]
    if sanitized.endswith("```"):
        sanitized = sanitized[:-3].rstrip()
    return sanitized.strip()


def _cloud_vision_completion(
    resolved_model: ResolvedModel,
    prompt: str,
    image_bytes: bytes,
    mime_type: str,
    max_tokens: int,
    timeout: float,
):
    client = _get_client_for_resolved_model(resolved_model)
    return _chat_completion(
        client,
        resolved_model.model_id,
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _build_image_data_url(image_bytes, mime_type),
                            },
                        },
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "timeout": timeout,
        },
    )


def _ollama_native_vision_completion(
    model_id: str,
    prompt: str,
    image_bytes: bytes,
    max_tokens: int,
    timeout: float,
):
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_bytes_to_base64(image_bytes)],
            }
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": max_tokens,
        },
    }

    response = httpx.post(
        f"{_ollama_api_base_url()}/api/chat",
        json=payload,
        timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
    )
    response.raise_for_status()

    data = response.json()
    message = data.get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError(f"Ollama model {model_id} returned an empty OCR response")

    return SimpleNamespace(
        model=data.get("model", model_id),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=content,
                )
            )
        ],
    )


def create_chat_completion(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    allow_fallback: bool = False,
    **kwargs,
):
    """
    Call the requested model. Fallback is opt-in for non-user-facing diagnostics only.
    """
    request_kwargs = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        **kwargs,
    }

    primary = resolve_model(model)
    attempts = [primary]
    if allow_fallback and primary.key != FALLBACK_MODEL_KEY:
        attempts.append(resolve_model(FALLBACK_MODEL_KEY))

    errors: list[str] = []
    attempted_keys: set[str] = set()

    for resolved in attempts:
        if resolved.key in attempted_keys:
            continue
        attempted_keys.add(resolved.key)

        try:
            if resolved.is_local:
                response = _ollama_native_chat_completion(resolved.model_id, request_kwargs)
            else:
                client = _get_client_for_resolved_model(resolved)
                response = _chat_completion(client, resolved.model_id, request_kwargs)
            print(f"[LLM] Using model: {resolved.label} ({resolved.model_id})", flush=True)
            return response
        except Exception as exc:  # pragma: no cover - exercised via tests and integration
            errors.append(f"{resolved.label}({resolved.model_id}): {exc}")
            print(f"[LLM] Model call failed: {errors[-1]}", flush=True)

    raise RuntimeError("; ".join(errors) or "No LLM model is available")


def extract_text_from_image(
    image_bytes: bytes,
    mime_type: Optional[str],
    model: Optional[str] = None,
    filename: Optional[str] = None,
    prompt: str = DEFAULT_OCR_PROMPT,
    max_tokens: int = 4096,
    timeout: float = 90.0,
) -> tuple[str, str]:
    normalized_mime_type = normalize_image_mime_type(mime_type, filename)
    resolved = resolve_model(model)

    if resolved.is_local:
        response = _ollama_native_vision_completion(
            resolved.model_id,
            prompt,
            image_bytes,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    else:
        response = _cloud_vision_completion(
            resolved,
            prompt,
            image_bytes,
            normalized_mime_type,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    extracted_text = _sanitize_ocr_text(_extract_response_text(response))
    if not extracted_text:
        raise RuntimeError(f"{resolved.label} 未返回可用的 OCR 文本")

    used_model = getattr(response, "model", resolved.model_id) or resolved.model_id
    print(f"[LLM] OCR using model: {resolved.label} ({used_model})", flush=True)
    return extracted_text, used_model


def correct_ocr_text_with_kimi(
    raw_text: str,
    *,
    page_label: str | None = None,
    low_confidence_lines: Optional[list[str]] = None,
    timeout: float = 90.0,
) -> tuple[str, str]:
    if not raw_text.strip():
        raise ValueError("OCR 原始文本不能为空")

    hints = ""
    if low_confidence_lines:
        joined_hints = "\n".join(f"- {line}" for line in low_confidence_lines[:10])
        hints = f"\n低置信度片段（优先检查，但不要臆测补全）：\n{joined_hints}\n"

    label = page_label or "当前页"
    user_prompt = (
        f"请校对{label}的合同 OCR 结果。\n"
        "要求：\n"
        "1. 保留原文含义和合同格式。\n"
        "2. 删除明显属于手机状态栏、截图界面、图片预览控件的噪音文字。\n"
        "3. 仅输出校对后的纯文本，不要加标题、解释或代码块。"
        f"{hints}\n"
        "OCR 原文如下：\n"
        f"{raw_text}"
    )

    response = create_chat_completion(
        model="kimi",
        messages=[
            {"role": "system", "content": OCR_CORRECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=min(max(len(raw_text) * 2, 2048), 8192),
        timeout=timeout,
    )
    corrected_text = _sanitize_ocr_text(_extract_response_text(response))
    if not corrected_text:
        raise RuntimeError("Kimi 未返回可用的 OCR 校对文本")

    used_model = getattr(response, "model", resolve_model("kimi").model_id) or resolve_model("kimi").model_id
    return corrected_text, used_model


def is_local_model_available() -> bool:
    try:
        response = httpx.get(
            f"{_ollama_api_base_url()}/api/tags",
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        response.raise_for_status()
        models = response.json().get("models", [])
        return any((model.get("name") or "").startswith(_gemma_model_id()) for model in models)
    except Exception:
        return False


def check_model_status() -> dict[str, bool]:
    status: dict[str, bool] = {}
    probe_messages = [{"role": "user", "content": "hi"}]

    for model in available_models():
        resolved = resolve_model(model["key"])
        try:
            if resolved.is_local:
                _ollama_native_chat_completion(
                    resolved.model_id,
                    {
                        "messages": probe_messages,
                        "max_tokens": 8,
                        "temperature": 0,
                        "timeout": 10.0,
                    },
                )
            else:
                client = _get_client_for_resolved_model(resolved)
                _chat_completion(
                    client,
                    resolved.model_id,
                    {
                        "messages": probe_messages,
                        "max_tokens": 1,
                        "temperature": 0,
                        "timeout": 5.0,
                    },
                )
            status[model["key"]] = True
        except Exception:
            status[model["key"]] = False

    return status


if __name__ == "__main__":  # pragma: no cover - manual diagnostics only
    print("[LLM] Checking model availability...", flush=True)
    for model_key, available in check_model_status().items():
        print(f"  {model_key}: {'available' if available else 'unavailable'}", flush=True)
