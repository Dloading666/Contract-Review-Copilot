"""
SiliconFlow LLM 客户端（OpenAI 兼容）。
- 推理/审查/问答：Qwen/Qwen3.5-4B
- 图片 OCR：PaddlePaddle/PaddleOCR-VL-1.5
"""
from __future__ import annotations

import base64
import mimetypes
import os
from typing import Optional

import httpx
from openai import OpenAI

from .config import get_settings

# 向后兼容常量，agents 里的代码通过这些 key 调用
DEFAULT_MODEL_KEY = "review"
FALLBACK_MODEL_KEY = DEFAULT_MODEL_KEY

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
    "你只能修正明显的错别字、标点、断行、条款编号和阅读顺序问题。"
    "不能总结，不能解释，不能改写合同含义，不能补充原文不存在的内容。"
    "如果某些字词看不清，就保留原样，不要猜测。"
)


def get_primary_model_key() -> str:
    return DEFAULT_MODEL_KEY


def _get_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or (settings.openai_api_key or ""),
        base_url=os.getenv("OPENAI_BASE_URL") or settings.openai_base_url,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def _resolve_model_id(model: Optional[str]) -> str:
    """将模型 key 映射到实际模型 ID。"""
    settings = get_settings()
    if not model or model in (DEFAULT_MODEL_KEY, FALLBACK_MODEL_KEY):
        return settings.review_model
    if model == "ocr":
        return settings.ocr_model
    return model  # 当作字面模型 ID 直接使用


def available_models() -> list[dict[str, str]]:
    settings = get_settings()
    return [{"key": DEFAULT_MODEL_KEY, "label": settings.review_model}]


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
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
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


def create_chat_completion(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    allow_fallback: bool = False,
    **kwargs,
):
    """调用 SiliconFlow 推理模型。allow_fallback 保留签名兼容性，无实际效果。"""
    del allow_fallback
    model_id = _resolve_model_id(model)
    client = _get_client()
    print(f"[LLM] Calling: {model_id}", flush=True)
    return client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        **kwargs,
    )


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
    settings = get_settings()
    # OCR 固定使用视觉模型
    model_id = settings.ocr_model

    client = _get_client()
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": _build_image_data_url(image_bytes, normalized_mime_type)},
                    },
                ],
            }
        ],
        temperature=0,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    extracted_text = _sanitize_ocr_text(_extract_response_text(response))
    if not extracted_text:
        raise RuntimeError(f"{model_id} 未返回可用的 OCR 文本")

    used_model = getattr(response, "model", model_id) or model_id
    print(f"[LLM] OCR using model: {used_model}", flush=True)
    return extracted_text, used_model


def correct_ocr_text_with_kimi(
    raw_text: str,
    *,
    page_label: str | None = None,
    low_confidence_lines: Optional[list[str]] = None,
    timeout: float = 90.0,
) -> tuple[str, str]:
    """OCR 文本校对（函数名保留向后兼容，实际使用推理模型）。"""
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
        raise RuntimeError("模型未返回可用的 OCR 校对文本")

    settings = get_settings()
    used_model = getattr(response, "model", settings.review_model) or settings.review_model
    return corrected_text, used_model
