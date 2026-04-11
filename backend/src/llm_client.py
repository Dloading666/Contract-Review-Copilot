"""
SiliconFlow LLM client using the OpenAI-compatible API.

- Review/chat model: configured via `review_model`
- OCR model: configured via `ocr_model`
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import time
from typing import Optional

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI

from .config import get_settings

DEFAULT_MODEL_KEY = "review"
FALLBACK_MODEL_KEY = DEFAULT_MODEL_KEY
OCR_UNREADABLE_MARKER = "OCR_UNREADABLE_CONTRACT_IMAGE"
TRANSIENT_LLM_ERRORS = (APIConnectionError, APITimeoutError)

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

DEFAULT_OCR_PROMPT = (
    "You are performing OCR for a contract review system. "
    "Extract only the text that is actually printed or handwritten in this image. "
    "Preserve paragraphs, line breaks, clause numbers, and punctuation. "
    "CRITICAL RULE - BLANK FORM FIELDS: If you see a label followed by blank underscores or dashes "
    "(e.g. '水表底: ___', '电表底: ___', '门锁: ___', '签字: ___'), output that label EXACTLY ONCE "
    "and then STOP. Do NOT repeat it. Do NOT continue generating more blank fields of the same type. "
    "CRITICAL RULE - NO HALLUCINATION: Never generate or repeat content that is not clearly visible. "
    "If a section contains many identical blank fields in a row, output only the first occurrence "
    "followed by '[...blank form section skipped...]' and move on. "
    "CRITICAL RULE - NO REPETITION: If you catch yourself about to output the same label twice, stop immediately. "
    f"If the image is not a contract or is unreadable, output only: {OCR_UNREADABLE_MARKER}. "
    "No Markdown, no explanations, no code blocks."
)

STRICT_OCR_PROMPT = (
    "Re-examine this contract image carefully. Output ONLY text that is genuinely printed or handwritten. "
    "STOP RULE: The moment you detect you are about to repeat any label or field name you already output, "
    "stop that section and write '[...repeated blank fields omitted...]' instead. "
    "Blank fields (underscores, dashes after a label) should each appear AT MOST ONCE. "
    "Do not fill in blank fields. Do not guess content. Do not generate template text. "
    f"If this is not a contract or is unreadable, output only: {OCR_UNREADABLE_MARKER}. "
    "Plain text only, reading order, no Markdown."
)

OCR_CORRECTION_SYSTEM_PROMPT = (
    "你是合同 OCR 校对助手。"
    "你只能修正明显的错别字、标点、断行、条款编号和阅读顺序问题。"
    "不能总结，不能解释，不能改写合同含义，也不能补充原文中不存在的内容。"
    "如果某些字词看不清，就保留原样，不要猜测。"
)


def get_primary_model_key() -> str:
    return DEFAULT_MODEL_KEY


def _get_client() -> OpenAI:
    """Get client for review/chat (MiniMax)."""
    settings = get_settings()
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or (settings.openai_api_key or ""),
        base_url=os.getenv("OPENAI_BASE_URL") or settings.openai_base_url,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def _get_ocr_client() -> OpenAI:
    """Get client for OCR (SiliconFlow PaddleOCR)."""
    settings = get_settings()
    api_key = (
        os.getenv("OCR_API_KEY")
        or settings.ocr_api_key
        or "sk-fhqbknokfwhselfchqjhsumfkwcwrhltmwujswbindgviwzs"
    )
    base_url = (
        os.getenv("OCR_BASE_URL")
        or settings.ocr_base_url
        or "https://api.siliconflow.cn/v1"
    )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(90.0, connect=10.0),
    )


def _resolve_model_id(model: Optional[str]) -> str:
    settings = get_settings()
    if not model or model in (DEFAULT_MODEL_KEY, FALLBACK_MODEL_KEY):
        return settings.review_model
    if model == "ocr":
        return settings.ocr_model
    return model


def available_models() -> list[dict[str, str]]:
    settings = get_settings()
    return [{"key": DEFAULT_MODEL_KEY, "label": settings.review_model}]


def _should_disable_thinking(model_id: str) -> bool:
    normalized_model = model_id.lower()
    return "qwen/qwen3" in normalized_model or normalized_model.startswith("qwen3")


def _apply_chat_extra_body_defaults(model_id: str, kwargs: dict) -> dict:
    request_kwargs = dict(kwargs)
    if not _should_disable_thinking(model_id):
        return request_kwargs

    extra_body = request_kwargs.get("extra_body")
    if isinstance(extra_body, dict):
        extra_body = dict(extra_body)
    elif extra_body is None:
        extra_body = {}
    else:
        return request_kwargs

    # Qwen3/3.5 can spend the whole token budget in reasoning_content.
    # Disabling thinking keeps normal chat replies in message.content.
    extra_body.setdefault("enable_thinking", False)
    request_kwargs["extra_body"] = extra_body
    return request_kwargs


def normalize_image_mime_type(mime_type: Optional[str], filename: Optional[str] = None) -> str:
    candidate = (mime_type or "").split(";", 1)[0].strip().lower()
    if candidate in SUPPORTED_IMAGE_MIME_TYPES:
        return candidate

    guessed_type, _ = mimetypes.guess_type(filename or "")
    guessed = (guessed_type or "").lower()
    if guessed in SUPPORTED_IMAGE_MIME_TYPES:
        return guessed

    raise ValueError("只支持 JPG、PNG、WEBP 图片格式。")


def image_bytes_to_base64(image_bytes: bytes) -> str:
    if not image_bytes:
        raise ValueError("图片内容不能为空。")
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


def _deduplicate_repeated_lines(text: str, max_repeats: int = 3) -> str:
    lines = text.splitlines()
    result_lines: list[str] = []
    line_counts: dict[str, int] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue

        normalized = re.sub(r"\s+", " ", stripped)
        count = line_counts.get(normalized, 0) + 1
        line_counts[normalized] = count

        if count <= max_repeats:
            result_lines.append(line)

    return "\n".join(result_lines)


def _deduplicate_repeated_phrases(text: str, max_repeats: int = 3) -> str:
    """
    Truncate repeated short label phrases within OCR text.
    Handles inline repetition like '水表底: ___水表底: ___...' across lines.
    Kicks in after max_repeats+1 occurrences of the same label.
    """
    from collections import Counter

    # Match short Chinese label (1-6 chars) + colon (half or full width) + optional blanks
    label_re = re.compile(r"([\u4e00-\u9fff]{1,6})[:：][\s_\u25a1\u2014\-]{0,10}")
    matches = list(label_re.finditer(text))
    if not matches:
        return text

    # Count by the Chinese label characters only (ignores colon style and trailing blanks)
    label_counts: Counter = Counter(m.group(1) for m in matches)

    # Truncate at the (max_repeats+1)-th occurrence of the most-repeated label
    for label_chars, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        if count <= max_repeats + 1:
            break  # sorted descending, no more candidates
        search_re = re.compile(re.escape(label_chars) + r"[:：][\s_\u25a1\u2014\-]{0,10}")
        positions = [m.start() for m in search_re.finditer(text)]
        if len(positions) > max_repeats:
            cutoff = positions[max_repeats]
            text = text[:cutoff].rstrip() + "\n\uff08\u4ee5\u4e0b\u76f8\u540c\u5185\u5bb9\u5df2\u7701\u7565\uff09"
            break

    return text


def _is_unreadable_ocr_marker(text: str) -> bool:
    return OCR_UNREADABLE_MARKER in text.strip()


def _is_suspicious_repetitive_ocr_text(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False

    blank_label_pattern = re.compile(
        r"^(地址|签约日期|日期|联系电话|电话|手机号|身份证号|姓名|甲方|乙方|出租方|承租方|签字|盖章)\s*[:：]\s*[□_\-\s]*$"
    )
    placeholder_line_pattern = re.compile(
        r"(?:_{2,}|□{2,}|从\s*[□_\-\s]*年\s*[□_\-\s]*月\s*[□_\-\s]*日|[□_\-\s]{6,})"
    )
    normalized_lines = [re.sub(r"\s+", " ", line) for line in lines]
    blank_label_lines = [line for line in lines if blank_label_pattern.match(line)]
    placeholder_lines = [line for line in lines if placeholder_line_pattern.search(line)]
    template_lines = [line for line in lines if blank_label_pattern.match(line) or placeholder_line_pattern.search(line)]
    repeated_line_count = max((normalized_lines.count(line) for line in set(normalized_lines)), default=0)
    template_line_ratio = len(template_lines) / len(lines)
    label_only_ratio = len(blank_label_lines) / len(lines)
    meaningful_text = re.sub(r"\s|[:：□_\-—年月日从至\.．/\\|,，。；;、（）()]", "", text)
    unique_visible_chars = len(set(meaningful_text))
    contract_signal_count = len(re.findall(
        r"(合同|协议|甲方|乙方|出租|承租|租赁|押金|租金|违约|条款|签订|签约|身份证|联系方式|民法典|中介|委托|付款|金额|费用|保证金)",
        text,
    ))
    has_strong_contract_context = (
        contract_signal_count >= 6
        and unique_visible_chars > 60
        and len(meaningful_text) >= 120
    )
    kana_count = len(re.findall(r"[\u3040-\u30ff\u31f0-\u31ff]", text))
    non_contract_noise = re.search(
        r"(ヘア|シャンプー|トリートメント|おすすめ|ランキング|レビュー|口コミ|商品|価格|Amazon|楽天)",
        text,
        flags=re.IGNORECASE,
    )

    if len(blank_label_lines) >= 6 and label_only_ratio >= 0.45:
        return True
    if (
        len(placeholder_lines) >= 4
        and template_line_ratio >= 0.35
        and (contract_signal_count < 4 or unique_visible_chars <= 36)
    ):
        return True
    if repeated_line_count >= 4 and not has_strong_contract_context and (
        unique_visible_chars <= 36 or repeated_line_count / len(lines) >= 0.35
    ):
        return True
    if len(meaningful_text) >= 80 and contract_signal_count == 0:
        return True
    if kana_count >= 20 and contract_signal_count < 2:
        return True
    if non_contract_noise and contract_signal_count < 2:
        return True
    return False


def create_chat_completion(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    allow_fallback: bool = False,
    **kwargs,
):
    del allow_fallback
    model_id = _resolve_model_id(model)
    request_kwargs = _apply_chat_extra_body_defaults(model_id, kwargs)

    for attempt in range(2):
        client = _get_client()
        print(f"[LLM] Calling: {model_id}", flush=True)
        try:
            return client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **request_kwargs,
            )
        except TRANSIENT_LLM_ERRORS as exc:
            if attempt == 1:
                raise
            print(f"[LLM] Transient error, retrying once: {type(exc).__name__}", flush=True)
            time.sleep(0.8)

    raise RuntimeError("LLM request failed unexpectedly")


def extract_text_from_image(
    image_bytes: bytes,
    mime_type: Optional[str],
    model: Optional[str] = None,
    filename: Optional[str] = None,
    prompt: str = DEFAULT_OCR_PROMPT,
    max_tokens: int = 4096,
    timeout: float = 60.0,
) -> tuple[str, str]:
    del model
    normalized_mime_type = normalize_image_mime_type(mime_type, filename)
    settings = get_settings()
    model_id = settings.ocr_model

    client = _get_ocr_client()
    image_url = _build_image_data_url(image_bytes, normalized_mime_type)

    def run_ocr(current_prompt: str):
        return client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": current_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    response = run_ocr(prompt)
    extracted_text = _sanitize_ocr_text(_extract_response_text(response))
    extracted_text = _deduplicate_repeated_lines(extracted_text, max_repeats=3)
    extracted_text = _deduplicate_repeated_phrases(extracted_text, max_repeats=3)
    if not extracted_text:
        raise RuntimeError(f"{model_id} 未返回可用的 OCR 文本。")

    if _is_unreadable_ocr_marker(extracted_text) or _is_suspicious_repetitive_ocr_text(extracted_text):
        retry_response = run_ocr(STRICT_OCR_PROMPT)
        retry_text = _sanitize_ocr_text(_extract_response_text(retry_response))
        retry_text = _deduplicate_repeated_lines(retry_text, max_repeats=3)
        retry_text = _deduplicate_repeated_phrases(retry_text, max_repeats=3)
        if (
            retry_text
            and not _is_unreadable_ocr_marker(retry_text)
            and not _is_suspicious_repetitive_ocr_text(retry_text)
        ):
            response = retry_response
            extracted_text = retry_text
        else:
            raise RuntimeError("OCR 结果疑似为模型补全的空白模板或非合同噪音，请上传更清晰的合同原图，或手动输入合同文字。")

    used_model = getattr(response, "model", model_id) or model_id
    print(f"[LLM] OCR using model: {used_model}", flush=True)
    return extracted_text, used_model


def correct_ocr_text(
    raw_text: str,
    *,
    page_label: str | None = None,
    low_confidence_lines: Optional[list[str]] = None,
    timeout: float = 90.0,
) -> tuple[str, str]:
    if not raw_text.strip():
        raise ValueError("OCR 原始文本不能为空。")

    hints = ""
    if low_confidence_lines:
        joined_hints = "\n".join(f"- {line}" for line in low_confidence_lines[:10])
        hints = f"\n低置信度片段（优先检查，但不要臆测补全）：\n{joined_hints}\n"

    label = page_label or "当前页面"
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
        raise RuntimeError("模型未返回可用的 OCR 校对文本。")

    settings = get_settings()
    used_model = getattr(response, "model", settings.review_model) or settings.review_model
    return corrected_text, used_model
