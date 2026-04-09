"""
Local PaddleOCR integration with lightweight image preprocessing.
"""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

LOW_CONFIDENCE_THRESHOLD = 0.88
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


@dataclass(frozen=True)
class OcrExtractionResult:
    text: str
    lines: list[str]
    average_confidence: float | None
    low_confidence_lines: list[str]
    warnings: list[str]


def _normalize_image_mime_type(mime_type: str | None, filename: str | None = None) -> str:
    candidate = (mime_type or "").split(";", 1)[0].strip().lower()
    if candidate in SUPPORTED_IMAGE_MIME_TYPES:
        return candidate

    guessed_type, _ = mimetypes.guess_type(filename or "")
    guessed = (guessed_type or "").lower()
    if guessed in SUPPORTED_IMAGE_MIME_TYPES:
        return guessed

    raise ValueError("只支持 JPG、PNG、WEBP 图片格式")


def _suffix_for_mime_type(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[mime_type]


@lru_cache(maxsize=1)
def _get_paddle_ocr_engine():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - depends on runtime installation
        raise RuntimeError(
            "PaddleOCR 未安装。请先安装 paddlepaddle==3.2.0 和 paddleocr。"
        ) from exc

    return PaddleOCR(
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_textline_orientation=False,
    )


def _load_cv2():  # pragma: no cover - depends on runtime installation
    import cv2
    import numpy as np

    return cv2, np


def _trim_borders(image):
    cv2, _ = _load_cv2()
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)[1]
    coords = cv2.findNonZero(mask)
    if coords is None:
        return image

    x, y, w, h = cv2.boundingRect(coords)
    padding = max(12, int(min(image.shape[0], image.shape[1]) * 0.01))
    x0 = max(x - padding, 0)
    y0 = max(y - padding, 0)
    x1 = min(x + w + padding, image.shape[1])
    y1 = min(y + h + padding, image.shape[0])
    return image[y0:y1, x0:x1]


def _upscale_if_needed(image):
    cv2, _ = _load_cv2()
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge >= 1800:
        return image

    scale = min(2.2, 1800 / max(long_edge, 1))
    if scale <= 1:
        return image

    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _estimate_skew_angle(gray_image) -> float:
    cv2, np = _load_cv2()
    threshold = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(threshold > 0))
    if len(coords) < 200:
        return 0.0

    angle = cv2.minAreaRect(coords[:, ::-1])[ -1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    return float(angle)


def _rotate_image(image, angle: float):
    cv2, _ = _load_cv2()
    if abs(angle) < 0.5:
        return image

    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _preprocess_image_bytes(image_bytes: bytes) -> bytes:
    try:
        cv2, np = _load_cv2()
    except Exception:  # pragma: no cover - runtime fallback
        return image_bytes

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法读取上传的图片内容")

    image = _trim_borders(image)
    image = _upscale_if_needed(image)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = _rotate_image(gray, _estimate_skew_angle(gray))
    gray = _trim_borders(gray)
    processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    success, encoded = cv2.imencode(".png", processed)
    if not success:
        return image_bytes
    return encoded.tobytes()


def _extract_page_payload(page_result: Any) -> dict[str, Any]:
    if isinstance(page_result, dict):
        payload = page_result.get("res")
        return payload if isinstance(payload, dict) else page_result

    payload = getattr(page_result, "res", None)
    if isinstance(payload, dict):
        return payload

    to_dict = getattr(page_result, "to_dict", None)
    if callable(to_dict):
        maybe_dict = to_dict()
        if isinstance(maybe_dict, dict):
            payload = maybe_dict.get("res")
            return payload if isinstance(payload, dict) else maybe_dict

    return {}


def _resolve_polygons(payload: dict[str, Any], expected_length: int) -> list[Any]:
    for key in ("rec_polys", "dt_polys", "textline_polys", "rec_boxes", "dt_boxes"):
        polygons = payload.get(key)
        if isinstance(polygons, list) and len(polygons) >= expected_length:
            return polygons
    return []


def _polygon_sort_key(polygon: Any, fallback_index: int) -> tuple[float, float, int]:
    try:
        _, np = _load_cv2()
        points = np.asarray(polygon, dtype=float)
        if points.ndim == 1 and len(points) % 2 == 0:
            points = points.reshape(-1, 2)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError

        min_x = float(points[:, 0].min())
        min_y = float(points[:, 1].min())
        height = float(points[:, 1].max() - points[:, 1].min())
        row_bucket = round(min_y / max(height * 0.8, 12.0))
        return (row_bucket, min_x, fallback_index)
    except Exception:
        return (float(fallback_index), 0.0, fallback_index)


def _extract_lines_from_result(result_pages: list[Any]) -> tuple[list[str], float | None, list[str]]:
    ordered_entries: list[tuple[str, float | None, Any, int]] = []

    for page in result_pages:
        payload = _extract_page_payload(page)
        rec_texts = payload.get("rec_texts") or []
        rec_scores = payload.get("rec_scores") or []
        polygons = _resolve_polygons(payload, len(rec_texts))

        for index, raw_text in enumerate(rec_texts):
            if not isinstance(raw_text, str):
                continue
            text = raw_text.strip()
            if not text:
                continue

            score: float | None = None
            if index < len(rec_scores):
                try:
                    score = float(rec_scores[index])
                except (TypeError, ValueError):
                    score = None

            polygon = polygons[index] if index < len(polygons) else None
            ordered_entries.append((text, score, polygon, len(ordered_entries)))

    ordered_entries.sort(key=lambda item: _polygon_sort_key(item[2], item[3]))

    lines: list[str] = []
    confidences: list[float] = []
    low_confidence_lines: list[str] = []
    for text, score, _polygon, _index in ordered_entries:
        lines.append(text)
        if score is not None:
            confidences.append(score)
            if score < LOW_CONFIDENCE_THRESHOLD:
                low_confidence_lines.append(text)

    average_confidence = sum(confidences) / len(confidences) if confidences else None
    return lines, average_confidence, low_confidence_lines


def extract_contract_text_from_image(
    image_bytes: bytes,
    mime_type: str | None,
    filename: str | None = None,
) -> OcrExtractionResult:
    if not image_bytes:
        raise ValueError("上传的图片内容为空")

    normalized_mime_type = _normalize_image_mime_type(mime_type, filename)
    suffix = _suffix_for_mime_type(normalized_mime_type)
    engine = _get_paddle_ocr_engine()
    processed_bytes = _preprocess_image_bytes(image_bytes)

    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(processed_bytes)
        temp_path = Path(temp_file.name)

    try:
        raw_result = engine.predict(str(temp_path))
        result_pages = list(raw_result) if raw_result is not None else []
    finally:
        temp_path.unlink(missing_ok=True)

    lines, average_confidence, low_confidence_lines = _extract_lines_from_result(result_pages)
    extracted_text = "\n".join(lines).strip()
    if not extracted_text:
        raise RuntimeError("PaddleOCR 未识别到可用文字，请检查图片是否清晰")

    warnings: list[str] = []
    if average_confidence is not None and average_confidence < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("当前页识别置信度偏低，建议重点检查错字和漏字。")
    if low_confidence_lines:
        warnings.append(f"检测到 {len(low_confidence_lines)} 行低置信度文字，建议优先检查。")

    return OcrExtractionResult(
        text=extracted_text,
        lines=lines,
        average_confidence=average_confidence,
        low_confidence_lines=low_confidence_lines,
        warnings=warnings,
    )
