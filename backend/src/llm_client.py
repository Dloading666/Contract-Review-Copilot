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
from typing import Optional

import httpx
from openai import OpenAI

from .config import get_settings

DEFAULT_MODEL_KEY = "review"
FALLBACK_MODEL_KEY = DEFAULT_MODEL_KEY
OCR_UNREADABLE_MARKER = "OCR_UNREADABLE_CONTRACT_IMAGE"

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

DEFAULT_OCR_PROMPT = (
    "You are performing OCR for a contract review system. "
    "Extract only the text actually visible in this contract image, strictly in top-to-bottom, left-to-right reading order. "
    "Preserve original paragraphs, line breaks, table rows, clause numbers, and punctuation. "
    "Never summarize, explain, rewrite, supplement, guess, or generate contract template fields not present in the image. "
    "Never fill in blank contract templates with repeated placeholder content like dates or blank lines. "
    "If a field is blank in the image (e.g. a label followed by blank lines), do not output that field. Mark unreadable text with the symbol [?]. "
    "IMPORTANT: Never output the same field name (e.g. the same label like a room item label) more than 2 times. "
    "IMPORTANT: Never output repeated blank placeholder lines. If the same line repeats more than 3 times, output it once only. "
    f"If the image is not a contract, or the contract text is severely blurry and unreadable, output only: {OCR_UNREADABLE_MARKER}. "
    "Do not output Markdown headings, bullet lists, explanations, or code blocks."
)

STRICT_OCR_PROMPT = (
    "Re-examine this contract image. You may only output text that is genuinely visible in the image. "
    "Do not fill in blank fields such as address, date, party names, or signature lines based on common contract formats. "
    "Do not repeat the same short label. Do not output repeated blank placeholder lines. "
    "If a label has no visible content after it, skip that line entirely. "
    f"If this is not a contract page or the text is unreadable, output only: {OCR_UNREADABLE_MARKER}. "
    "Maintain natural reading order. No explanations, no summaries, no Markdown."
)

OCR_CORRECTION_SYSTEM_PROMPT = (
    "\u4f60\u662f\u5408\u540c OCR \u6821\u5bf9\u52a9\u624b\u3002"
    "\u4f60\u53ea\u80fd\u4fee\u6b63\u660e\u663e\u7684\u9519\u522b\u5b57\u3001\u6807\u70b9\u3001\u65ad\u884c\u3001\u6761\u6b3e\u7f16\u53f7\u548c\u9605\u8bfb\u987a\u5e8f\u95ee\u9898\u3002"
    "\u4e0d\u80fd\u603b\u7ed3\uff0c\u4e0d\u80fd\u89e3\u91ca\uff0c\u4e0d\u80fd\u6539\u5199\u5408\u540c\u542b\u4e49\uff0c\u4e5f\u4e0d\u80fd\u8865\u5145\u539f\u6587\u4e2d\u4e0d\u5b58\u5728\u7684\u5185\u5bb9\u3002"
    "\u5982\u679c\u67d0\u4e9b\u5b57\u8bcd\u770b\u4e0d\u6e05\uff0c\u5c31\u4fdd\u7559\u539f\u6837\uff0c\u4e0d\u8981\u731c\u6d4b\u3002"
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
    settings = get_settings()
    if not model or model in (DEFAULT_MODEL_KEY, FALLBACK_MODEL_KEY):
        return settings.review_model
    if model == "ocr":
        return settings.ocr_model
    return model


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

    raise ValueError("\u53ea\u652f\u6301 JPG\u3001PNG\u3001WEBP \u56fe\u7247\u683c\u5f0f\u3002")


def image_bytes_to_base64(image_bytes: bytes) -> str:
    if not image_bytes:
        raise ValueError("\u56fe\u7247\u5185\u5bb9\u4e0d\u80fd\u4e3a\u7a7a\u3002")
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
        elif count == max_repeats + 1:
            result_lines.append("(\u4ee5\u4e0b\u76f8\u540c\u5185\u5bb9\u5df2\u7701\u7565)")

    return "\n".join(result_lines)


def _is_unreadable_ocr_marker(text: str) -> bool:
    return OCR_UNREADABLE_MARKER in text.strip()


def _is_suspicious_repetitive_ocr_text(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False

    blank_label_pattern = re.compile(
        r"^(\u5730\u5740|\u7b7e\u7ea6\u65e5\u671f|\u65e5\u671f|\u8054\u7cfb\u7535\u8bdd|\u7535\u8bdd|\u624b\u673a\u53f7|\u8eab\u4efd\u8bc1\u53f7|\u59d3\u540d|\u7532\u65b9|\u4e59\u65b9|\u51fa\u租\u65b9|\u627f\u79df\u65b9|\u7b7e\u5b57|\u76d6\u7ae0)\s*[::\u003a]\s*[\u25a1_\-\s]*$"
    )
    placeholder_line_pattern = re.compile(
        r"(?:_{2,}|\u25a1{2,}|\u4ece\s*[\u25a1_\-\s]*\u5e74\s*[\u25a1_\-\s]*\u6708\s*[\u25a1_\-\s]*\u65e5|[\u25a1_\-\s]{6,})"
    )
    normalized_lines = [re.sub(r"\s+", " ", line) for line in lines]
    blank_label_lines = [line for line in lines if blank_label_pattern.match(line)]
    placeholder_lines = [line for line in lines if placeholder_line_pattern.search(line)]
    template_lines = [line for line in lines if blank_label_pattern.match(line) or placeholder_line_pattern.search(line)]
    repeated_line_count = max((normalized_lines.count(line) for line in set(normalized_lines)), default=0)
    template_line_ratio = len(template_lines) / len(lines)
    label_only_ratio = len(blank_label_lines) / len(lines)
    meaningful_text = re.sub(r"\s|[::\u003a\u25a1_\-\u2014\u5e74\u6708\u65e5\u4ece\u81f3\..\uff0f\\|,\uff0c\u3002\uff1b;\u3001\uff08\uff09()]", "", text)
    unique_visible_chars = len(set(meaningful_text))
    contract_signal_count = len(re.findall(
        r"(\u5408\u540c|\u534f\u8bae|\u7532\u65b9|\u4e59\u65b9|\u51fa\u79df|\u627f\u79df|\u79df\u8d41|\u62bc\u91d1|\u79df\u91d1|\u8fdd\u7ea6|\u6761\u6b3e|\u7b7e\u8ba2|\u7b7e\u7ea6|\u8eab\u4efd\u8bc1|\u8054\u7cfb\u65b9\u5f0f|\u6c11\u6cd5\u5178|\u4e2d\u4ecb|\u59d3\u540d|\u59d3\u540d|\u5f59\u6b3e|\u91d1\u989d|\u8d39\u7528|\u4fdd\u8bc1\u91d1)",
        text,
    ))
    has_strong_contract_context = (
        contract_signal_count >= 6
        and unique_visible_chars > 60
        and len(meaningful_text) >= 120
    )
    kana_count = len(re.findall(r"[\u3040-\u30ff\u31f0-\u31ff]", text))
    non_contract_noise = re.search(
        r"(\u30d8\u30a2|\u30b7\u30e3\u30f3\u30d7\u30fc|\u30c8\u30ea\u30fc\u30c8\u30e1\u30f3\u30c8|\u304a\u3059\u3059\u3081|\u30e9\u30f3\u30ad\u30f3\u30b0|\u30ec\u30d3\u30e5\u30fc|\u53e3\u30b3\u30df|\u5546\u54c1|\u4fa1\u683c|Amazon|\u697d\u5929)",
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
    del model
    normalized_mime_type = normalize_image_mime_type(mime_type, filename)
    settings = get_settings()
    model_id = settings.ocr_model

    client = _get_client()
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
    if not extracted_text:
        raise RuntimeError(f"{model_id} \u672a\u8fd4\u56de\u53ef\u7528\u7684 OCR \u6587\u672c\u3002")

    if _is_unreadable_ocr_marker(extracted_text) or _is_suspicious_repetitive_ocr_text(extracted_text):
        retry_response = run_ocr(STRICT_OCR_PROMPT)
        retry_text = _sanitize_ocr_text(_extract_response_text(retry_response))
        retry_text = _deduplicate_repeated_lines(retry_text, max_repeats=3)
        if (
            retry_text
            and not _is_unreadable_ocr_marker(retry_text)
            and not _is_suspicious_repetitive_ocr_text(retry_text)
        ):
            response = retry_response
            extracted_text = retry_text
        else:
            raise RuntimeError("OCR \u7ed3\u679c\u7591\u4f3c\u4e3a\u6a21\u578b\u8865\u5168\u7684\u7a7a\u767d\u6a21\u677f\u6216\u975e\u5408\u540c\u566a\u97f3\uff0c\u8bf7\u4e0a\u4f20\u66f4\u6e05\u6670\u7684\u5408\u540c\u539f\u56fe\uff0c\u6216\u624b\u52a8\u8f93\u5165\u5408\u540c\u6587\u5b57\u3002")

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
        raise ValueError("OCR \u539f\u59cb\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a\u3002")

    hints = ""
    if low_confidence_lines:
        joined_hints = "\n".join(f"- {line}" for line in low_confidence_lines[:10])
        hints = f"\n\u4f4e\u7f6e\u4fe1\u5ea6\u7247\u6bb5\uff08\u4f18\u5148\u68c0\u67e5\uff0c\u4f46\u4e0d\u8981\u81c6\u6d4b\u8865\u5168\uff09\uff1a\n{joined_hints}\n"

    label = page_label or "\u5f53\u524d\u9875\u9762"
    user_prompt = (
        f"\u8bf7\u6821\u5bf9{label}\u7684\u5408\u540c OCR \u7ed3\u679c\u3002\n"
        "\u8981\u6c42\uff1a\n"
        "1. \u4fdd\u7559\u539f\u6587\u542b\u4e49\u548c\u5408\u540c\u683c\u5f0f\u3002\n"
        "2. \u5220\u9664\u660e\u663e\u5c5e\u4e8e\u624b\u673a\u72b6\u6001\u680f\u3001\u622a\u56fe\u754c\u9762\u3001\u56fe\u7247\u9884\u89c8\u63a7\u4ef6\u7684\u566a\u97f3\u6587\u5b57\u3002\n"
        "3. \u4ec5\u8f93\u51fa\u6821\u5bf9\u540e\u7684\u7eaf\u6587\u672c\uff0c\u4e0d\u8981\u52a0\u6807\u9898\u3001\u89e3\u91ca\u6216\u4ee3\u7801\u5757\u3002"
        f"{hints}\n"
        "OCR \u539f\u6587\u5982\u4e0b\uff1a\n"
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
        raise RuntimeError("\u6a21\u578b\u672a\u8fd4\u56de\u53ef\u7528\u7684 OCR \u6821\u5bf9\u6587\u672c\u3002")

    settings = get_settings()
    used_model = getattr(response, "model", settings.review_model) or settings.review_model
    return corrected_text, used_model
