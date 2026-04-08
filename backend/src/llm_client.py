"""
Shared LLM routing for review agents and chat Q&A.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import httpx
from openai import OpenAI

DEFAULT_MODEL_KEY = "gemma4"
FALLBACK_MODEL_KEY = "gemma4"

CLOUD_MODEL_LABELS = {
    "glm-5": "GLM-5",
    "minimax": "MiniMax M2.5",
    "qwen": "Qwen 3.5 Plus",
    "kimi": "Kimi K2.5",
}

LOCAL_MODEL_LABELS = {
    "gemma4": "Gemma4 (local)",
}


@dataclass(frozen=True)
class ResolvedModel:
    key: str
    model_id: str
    label: str
    is_local: bool


def get_primary_model_key() -> str:
    return os.getenv("PRIMARY_LLM_MODEL_KEY", DEFAULT_MODEL_KEY).strip() or DEFAULT_MODEL_KEY


def _cloud_model_ids() -> dict[str, str]:
    return {
        "glm-5": os.getenv("OPENAI_MODEL", "glm-5"),
        "minimax": os.getenv("MINIMAX_MODEL", "MiniMax-M2.5"),
        "qwen": os.getenv("QWEN_MODEL", "qwen-plus"),
        "kimi": os.getenv("KIMI_MODEL", "kimi-k2.5"),
    }


def _gemma_model_id() -> str:
    return os.getenv("GEMMA4_MODEL", "gemma3")


def _gemma_base_url() -> str:
    return os.getenv("GEMMA4_BASE_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def _ollama_api_base_url() -> str:
    base_url = _gemma_base_url().rstrip("/")
    return base_url.removesuffix("/v1")


def _cloud_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1"),
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


def _gemma_client() -> OpenAI:
    return OpenAI(
        api_key="ollama",
        base_url=_gemma_base_url(),
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def available_models() -> list[dict[str, str]]:
    models = [{"key": FALLBACK_MODEL_KEY, "label": LOCAL_MODEL_LABELS[FALLBACK_MODEL_KEY]}]
    models.extend({"key": key, "label": label} for key, label in CLOUD_MODEL_LABELS.items())
    return models


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
        label=LOCAL_MODEL_LABELS.get(DEFAULT_MODEL_KEY, DEFAULT_MODEL_KEY),
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


def create_chat_completion(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    **kwargs,
):
    """
    Call the requested model and fall back to Gemma4 when the primary model fails.
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
    if primary.key != FALLBACK_MODEL_KEY:
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
