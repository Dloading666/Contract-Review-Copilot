"""
Contract Review Copilot FastAPI backend.
"""
from __future__ import annotations

import json
import re
import uuid
import asyncio
import traceback
import httpx
from asyncio import to_thread
from contextlib import asynccontextmanager
from io import BytesIO
from threading import Lock, Thread
from typing import AsyncGenerator, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import auth
from .cache import build_cache_key, close_redis_client, delete_json, get_json, get_ttl_seconds, set_json
from .chat_retrieval import (
    build_answer_evidence_context,
    build_chat_search_queries,
    rerank_evidence_items,
    retrieve_general_web_evidence,
    retrieve_pgvector_evidence,
    retrieve_targeted_legal_evidence,
    should_search_general_web,
    should_search_targeted_legal,
)
from .config import get_settings
from .graph.review_graph import run_aggregation_stream, run_deep_review_stream, run_review_stream
from .llm_client import (
    CHAT_MODEL_KEY,
    DEFAULT_MODEL_KEY,
    available_models,
    create_chat_completion,
    extract_stream_delta_text,
    stream_chat_completion,
)
from .ocr import UploadedContractFile, ingest_contract_files, validate_contract_uploads
from .ocr.task_storage import stage_ocr_task_files
from .rate_limit import RateLimitRule, enforce_rate_limits, get_request_ip
from .report_export import build_report_docx, build_report_download_name
from .services import queue_service
from .workers import ocr_worker, review_worker
from .schemas import (
    ChatRequest,
    ConfirmRequest,
    ContractReviewRequest,
    DeepReviewRequest,
    ExportReportRequest,
    HealthResponse,
    LoginRequest,
    PasswordResetCodeRequest,
    PublicPasswordResetRequest,
    RegisterRequest,
    SecurityResetPasswordRequest,
    SendCodeRequest,
)


paused_sessions: dict[str, dict] = {}
_paused_sessions_lock = Lock()


def _session_cache_key(session_id: str) -> str:
    return build_cache_key("session", {"session_id": session_id})


def store_paused_session(session_id: str, session_data: dict) -> None:
    with _paused_sessions_lock:
        paused_sessions[session_id] = session_data
    set_json(_session_cache_key(session_id), session_data, get_ttl_seconds("session"))


def load_paused_session(session_id: str) -> dict | None:
    cached_session = get_json(_session_cache_key(session_id))
    if isinstance(cached_session, dict):
        with _paused_sessions_lock:
            paused_sessions[session_id] = cached_session
        return cached_session
    with _paused_sessions_lock:
        return paused_sessions.get(session_id)


def delete_paused_session(session_id: str) -> None:
    with _paused_sessions_lock:
        paused_sessions.pop(session_id, None)
    delete_json(_session_cache_key(session_id))


def pop_paused_session(session_id: str) -> dict | None:
    session_data = load_paused_session(session_id)
    if session_data is not None:
        delete_paused_session(session_id)
    return session_data


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print("Contract Review Copilot API started", flush=True)
    yield
    with _paused_sessions_lock:
        paused_sessions.clear()
    close_redis_client()
    print("Contract Review Copilot API stopped", flush=True)


app = FastAPI(
    title="Contract Review Copilot API",
    description="AI-powered contract review with LangGraph agent orchestration",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
EMPTY_CHAT_REPLY_TEXT = "模型没有返回可见内容，请再试一次。"
INVISIBLE_CHAT_REPLY_PATTERN = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
THINK_TAG_PATTERN = re.compile(r"</?think>", re.IGNORECASE)
AUTH_BOT_GUARD_MESSAGE = "检测到异常注册行为，请刷新后重试"
AUTH_SEND_CODE_MIN_ELAPSED_MS = 600
AUTH_REGISTER_MIN_ELAPSED_MS = 1200



def normalize_chat_reply(reply: object) -> str:
    if isinstance(reply, str):
        text = reply
    elif isinstance(reply, list):
        fragments: list[str] = []
        for block in reply:
            block_text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if isinstance(block_text, str) and block_text.strip():
                fragments.append(block_text.strip())
        text = "\n".join(fragments)
    else:
        text = ""

    text = THINK_BLOCK_PATTERN.sub("", text)
    text = THINK_TAG_PATTERN.sub("", text)
    visible_text = INVISIBLE_CHAT_REPLY_PATTERN.sub("", text).strip()
    return visible_text or EMPTY_CHAT_REPLY_TEXT


def extract_chat_reply(response: object) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return EMPTY_CHAT_REPLY_TEXT

    message = getattr(choices[0], "message", None)
    if message is None:
        return EMPTY_CHAT_REPLY_TEXT

    for candidate in (
        getattr(message, "content", ""),
        getattr(message, "text", ""),
    ):
        reply = normalize_chat_reply(candidate)
        if reply != EMPTY_CHAT_REPLY_TEXT:
            return reply

    return EMPTY_CHAT_REPLY_TEXT


def build_empty_chat_fallback_reply(risk_summary: str) -> str:
    normalized_risk_summary = risk_summary.strip()
    if not normalized_risk_summary:
        return EMPTY_CHAT_REPLY_TEXT

    return (
        "这次模型没有返回完整回复。我先按当前审查结果给你一个可执行方向：\n"
        f"{normalized_risk_summary[:600]}\n\n"
        "建议优先处理高风险条款，把违约金、押金扣除、单方免责等内容改成金额合理、条件明确、双方责任对等的表述。"
    )

def build_chat_system_prompt(
    *,
    contract_text: str,
    risk_summary: str,
    evidence_context: str = "",
) -> str:
    context_sections: list[str] = []
    if contract_text:
        context_sections.append(f"合同原文（节选）：\n{contract_text[:2200]}")
    if risk_summary:
        context_sections.append(f"已识别风险条款：\n{risk_summary[:1200]}")
    if evidence_context:
        context_sections.append(f"检索到的支持依据：\n{evidence_context}")

    prompt = (
        "你是一个专业的合同审查助手。请基于合同原文、已识别风险和检索证据回答用户问题。"
        "先给结论，再解释风险和影响，最后给出可执行建议。"
        "如果外部证据不足，要明确说明依据有限。"
        "不要输出 HTML 标签。"
    )
    if context_sections:
        prompt = f"{prompt}\n\n" + "\n\n".join(context_sections)
    return prompt


allowed_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def format_sse(event_type: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8")


def _api_error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, "code": code})


def _build_sse_error_payload(message: str, code: str) -> dict:
    return {"message": message, "code": code}


def _log_internal_exception(context: str, exc: Exception) -> None:
    print(f"[{context}] {exc}", flush=True)
    traceback.print_exc()


def _require_task_owner(task_id: str, authorization: Optional[str], *, task_type: str = "review") -> dict:
    user = require_current_user(authorization)
    task = queue_service.get_task(task_id, task_type=task_type)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="无权访问该任务")
    return task


def get_current_user(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return auth.get_user_from_token(token)


def require_current_user(authorization: Optional[str]) -> dict:
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user



def _build_user_payload(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "emailVerified": bool(user.get("emailVerified")),
        "accountStatus": user.get("accountStatus", "active"),
        "createdAt": user.get("createdAt"),
        "hasPassword": bool(user.get("hasPassword")),
    }


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email))


def _enforce_auth_rate_limits(request: Request, *, email: str | None = None, action: str) -> None:
    ip = get_request_ip(request)
    rules = [
        RateLimitRule(f"{action}:ip:minute", ip, 20, 60, "请求过于频繁，请稍后重试"),
        RateLimitRule(f"{action}:ip:hour", ip, 120, 3600, "请求过于频繁，请稍后重试"),
    ]
    if email:
        rules.append(RateLimitRule(f"{action}:email", email.lower(), 8, 3600, "该邮箱操作过于频繁，请稍后再试"))
    enforce_rate_limits(rules)



async def _read_uploaded_contract_file(upload: UploadFile) -> UploadedContractFile:
    file_bytes = await upload.read()
    return UploadedContractFile(
        filename=upload.filename or "contract.bin",
        content=file_bytes,
        content_type=upload.content_type,
    )


async def _verify_captcha_token(captcha_token: str, request: Request) -> bool:
    runtime_settings = get_settings()
    secret = (runtime_settings.captcha_secret_key or '').strip()
    verify_url = (runtime_settings.captcha_verify_url or '').strip()
    if not secret or not verify_url:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                verify_url,
                data={
                    'secret': secret,
                    'response': captcha_token.strip(),
                    'remoteip': get_request_ip(request),
                },
            )
        payload = response.json() if response.content else {}
        return bool(payload.get('success'))
    except Exception as exc:
        _log_internal_exception('auth-captcha-verify', exc)
        return False


async def _enforce_auth_bot_guard(
    request: Request,
    *,
    honeypot: str | None = None,
    client_elapsed_ms: int | None = None,
    captcha_token: str | None = None,
    min_elapsed_ms: int = 0,
) -> JSONResponse | None:
    if honeypot and honeypot.strip():
        return _api_error_response(400, AUTH_BOT_GUARD_MESSAGE, 'AUTH_BOT_GUARD')

    if min_elapsed_ms > 0 and client_elapsed_ms is not None and client_elapsed_ms >= 0 and client_elapsed_ms < min_elapsed_ms:
        return _api_error_response(429, '操作过于频繁，请稍后重试', 'AUTH_BOT_TOO_FAST')

    runtime_settings = get_settings()
    if runtime_settings.captcha_enabled:
        token = (captcha_token or '').strip()
        if not token:
            return _api_error_response(400, '请完成 captcha 安全校验后再试', 'AUTH_CAPTCHA_REQUIRED')
        if not await _verify_captcha_token(token, request):
            return _api_error_response(400, 'captcha 安全校验未通过，请刷新后重试', 'AUTH_CAPTCHA_INVALID')

    return None


@app.post("/api/auth/send-code")
async def send_code(body: SendCodeRequest, request: Request):
    email = body.email.strip().lower()
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    bot_guard = await _enforce_auth_bot_guard(
        request,
        honeypot=body.website,
        client_elapsed_ms=body.client_elapsed_ms,
        captcha_token=body.captcha_token,
        min_elapsed_ms=AUTH_SEND_CODE_MIN_ELAPSED_MS,
    )
    if bot_guard is not None:
        return bot_guard

    _enforce_auth_rate_limits(request, email=email, action="auth-email-code")
    result = auth.send_verification_code(email)
    if not result.get("success"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "注册失败")})
    return {"success": True, **({"dev_code": result["dev_code"]} if "dev_code" in result else {})}


@app.post("/api/auth/password/send-reset-code")
async def send_public_password_reset_code(body: PasswordResetCodeRequest, request: Request):
    email = body.email.strip().lower()
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    _enforce_auth_rate_limits(request, email=email, action="auth-public-password-reset-code")
    result = auth.send_password_reset_code_for_email(email)
    if not result.get("success"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "发送失败")})
    return {
        "success": True,
        "message": "如果该邮箱已注册，我们已发送验证码，请查收邮箱",
        **({"dev_code": result["dev_code"]} if "dev_code" in result else {}),
    }


@app.post("/api/auth/register")
async def register(body: RegisterRequest, request: Request):
    email = body.email.strip().lower()
    code = body.code.strip()
    password = body.password.strip()

    if not email or not code or not password:
        return JSONResponse(status_code=400, content={"error": "邮箱、验证码和密码不能为空"})
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    bot_guard = await _enforce_auth_bot_guard(
        request,
        honeypot=body.website,
        client_elapsed_ms=body.client_elapsed_ms,
        captcha_token=body.captcha_token,
        min_elapsed_ms=AUTH_REGISTER_MIN_ELAPSED_MS,
    )
    if bot_guard is not None:
        return bot_guard

    _enforce_auth_rate_limits(request, email=email, action="auth-register")
    result = auth.register_user(email, code, password)
    if not result.get("success"):
        return JSONResponse(status_code=400, content={"error": result.get("error", "注册失败")})
    return {"success": True, "message": "注册成功，请登录", "user": result.get("user")}


@app.post("/api/auth/login")
async def login(body: LoginRequest, request: Request):
    email = body.email.strip().lower()
    password = body.password.strip()

    if not email or not password:
        return JSONResponse(status_code=400, content={"error": "邮箱和密码不能为空"})
    _enforce_auth_rate_limits(request, email=email, action="auth-email-login")

    token = auth.login_with_password(email, password)
    if not token:
        return JSONResponse(status_code=401, content={"error": "邮箱或密码错误"})

    user = auth.get_user_from_token(token)
    return {"success": True, "token": token, "user": _build_user_payload(user or {})}


@app.post("/api/auth/security/send-password-code")
async def send_password_reset_code(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_current_user(authorization)
    email = str(user.get("email") or "").strip().lower()
    if not email:
        return JSONResponse(status_code=400, content={"error": "当前账号未绑定邮箱，暂不支持邮箱改密"})

    _enforce_auth_rate_limits(request, email=email, action="auth-password-reset-code")
    result = auth.send_password_reset_code_for_user(user["id"])
    if not result.get("success"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "发送失败")})
    return {"success": True, **({"dev_code": result["dev_code"]} if "dev_code" in result else {})}


@app.post("/api/auth/password/reset")
async def reset_password_public(body: PublicPasswordResetRequest, request: Request):
    email = body.email.strip().lower()
    code = body.code.strip()
    if not email or not code or not body.new_password.strip():
        return JSONResponse(status_code=400, content={"error": "邮箱、验证码和新密码不能为空"})
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    _enforce_auth_rate_limits(request, email=email, action="auth-public-password-reset")
    result = auth.reset_password_by_email_code(email, code, body.new_password)
    if not result.get("success"):
        return JSONResponse(status_code=400, content={"error": result.get("error", "密码重置失败")})
    return {"success": True, "message": "密码重置成功，请返回登录"}


@app.post("/api/auth/security/reset-password")
async def reset_password(
    body: SecurityResetPasswordRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_current_user(authorization)
    email = str(user.get("email") or "").strip().lower()
    if not email:
        return JSONResponse(status_code=400, content={"error": "当前账号未绑定邮箱，暂不支持邮箱改密"})

    _enforce_auth_rate_limits(request, email=email, action="auth-password-reset")
    result = auth.reset_password_with_email_code(user["id"], body.code.strip(), body.new_password)
    if not result.get("success"):
        return JSONResponse(status_code=400, content={"error": result.get("error", "密码修改失败")})
    return {"success": True, "message": "密码修改成功"}


@app.get("/api/auth/github")
async def github_oauth_redirect():
    settings = get_settings()
    client_id = (settings.github_client_id or "").strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth 未配置")
    redirect_uri = (settings.github_oauth_redirect_uri or "").strip()
    params = f"client_id={client_id}&scope=user:email"
    if redirect_uri:
        params += f"&redirect_uri={quote(redirect_uri)}"
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@app.get("/api/auth/github/callback")
async def github_oauth_callback(code: str):
    result = auth.login_with_github(code)
    if not result.get("success"):
        error_msg = quote(result.get("error", "GitHub 登录失败"))
        return RedirectResponse(f"/?auth_error={error_msg}")
    token = result.get("token", "")
    return RedirectResponse(f"/?token={quote(token)}")


@app.get("/api/auth/me")
async def get_me(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"error": "未登录"})
    return {"user": _build_user_payload(user)}


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/api/models")
async def list_models():
    return {"models": available_models(), "default_model": DEFAULT_MODEL_KEY}


@app.post("/api/chat")
async def chat(body: ChatRequest, authorization: Optional[str] = Header(None)):
    user = require_current_user(authorization)

    message = body.message.strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "消息不能为空"})

    context_sections: list[str] = []
    if body.contract_text:
        context_sections.append(f"合同原文（节选）：\n{body.contract_text[:2200]}")
    if body.risk_summary:
        context_sections.append(f"已识别风险条款：\n{body.risk_summary[:1200]}")

    system_prompt = (
        "你是一个专业的合同审查助手。请基于合同原文和已识别风险回答用户问题，"
        "结论要简洁直接，优先指出风险、影响和可执行建议。"
        "格式要求：用 **关键词** 标注重要的金额、条款名称、风险结论等关键内容（两个星号包裹）；"
        "多条建议用「- 」开头分行列出；章节标题后加冒号另起一行。"
        "不要输出 HTML 标签。"
    )
    if context_sections:
        system_prompt = f"{system_prompt}\n\n" + "\n\n".join(context_sections)

    try:
        response = create_chat_completion(
            lane=CHAT_MODEL_KEY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=settings.chat_temperature,
            max_tokens=settings.interactive_chat_max_tokens,
            timeout=settings.interactive_chat_timeout_seconds,
            allow_fallback=False,
        )
        reply = extract_chat_reply(response)
        if reply == EMPTY_CHAT_REPLY_TEXT:
            reply = build_empty_chat_fallback_reply(body.risk_summary)
        return {
            "reply": reply,
            "model": getattr(response, "model", settings.primary_chat_model) or settings.primary_chat_model,
        }
    except Exception as exc:
        print(f"[Chat] Model call failed: {exc}", flush=True)
        fallback_reply = build_empty_chat_fallback_reply(body.risk_summary)
        if fallback_reply == EMPTY_CHAT_REPLY_TEXT:
            fallback_reply = "模型暂时繁忙，你可以先优先核对押金、违约金、解约条件和退款机制，等稍后再继续提问。"
        return {
            "reply": fallback_reply,
            "model": None,
            "degraded": True,
        }

@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, authorization: Optional[str] = Header(None)):
    require_current_user(authorization)

    message = body.message.strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "消息不能为空"})

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            yield format_sse("chat_retrieval_started", {"message": "正在检索合同依据与法律资料..."})

            queries = build_chat_search_queries(
                question=message,
                contract_text=body.contract_text,
                risk_summary=body.risk_summary,
                rewrite_count=settings.chat_query_rewrite_count,
            )

            yield format_sse("chat_retrieval_stage", {"stage": "pgvector", "message": "正在检索本地法规知识库..."})
            pgvector_items = await to_thread(
                retrieve_pgvector_evidence,
                queries,
                top_k=settings.chat_pgvector_top_k,
                min_similarity=settings.chat_pgvector_min_similarity,
            )

            targeted_items: list[dict[str, object]] = []
            if settings.chat_enable_targeted_search and should_search_targeted_legal(
                question=message,
                pgvector_items=pgvector_items,
                minimum_hits=settings.chat_pgvector_min_hits_for_skip_search,
                minimum_top_score=settings.chat_pgvector_min_top_score_for_skip_search,
            ):
                yield format_sse("chat_retrieval_stage", {"stage": "legal_search", "message": "正在检索法律站点与法规库..."})
                targeted_items = await to_thread(
                    retrieve_targeted_legal_evidence,
                    queries,
                    max_results=settings.chat_targeted_search_top_k,
                )

            web_items: list[dict[str, object]] = []
            if settings.chat_enable_web_search and should_search_general_web(
                question=message,
                targeted_items=targeted_items,
                minimum_hits=settings.chat_targeted_search_min_hits_for_skip_web,
            ):
                yield format_sse("chat_retrieval_stage", {"stage": "web_search", "message": "正在补充联网搜索结果..."})
                web_items = await to_thread(
                    retrieve_general_web_evidence,
                    queries,
                    max_results=settings.chat_web_search_top_k,
                )

            evidence_items = rerank_evidence_items(
                [*pgvector_items, *targeted_items, *web_items],
                max_items=settings.chat_max_evidence_items,
            )
            evidence_context = build_answer_evidence_context(evidence_items)

            yield format_sse(
                "chat_retrieval_complete",
                {
                    "message": "依据检索完成，开始生成回答...",
                    "source_counts": {
                        "pgvector": len(pgvector_items),
                        "legal_search": len(targeted_items),
                        "web_search": len(web_items),
                    },
                },
            )

            system_prompt = build_chat_system_prompt(
                contract_text=body.contract_text,
                risk_summary=body.risk_summary,
                evidence_context=evidence_context,
            )

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

            def run_model_stream() -> None:
                try:
                    stream, model_id = stream_chat_completion(
                        lane=CHAT_MODEL_KEY,
                        model=settings.chat_stream_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message},
                        ],
                        temperature=settings.chat_temperature,
                        max_tokens=settings.interactive_chat_max_tokens,
                        timeout=settings.interactive_chat_timeout_seconds,
                        allow_fallback=False,
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, ("model", model_id))
                    for chunk in stream:
                        text = extract_stream_delta_text(chunk)
                        if text:
                            loop.call_soon_threadsafe(queue.put_nowait, ("token", text))
                except Exception as exc:  # pragma: no cover - runtime failure path
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

            Thread(target=run_model_stream, daemon=True).start()

            model_name = settings.chat_stream_model
            saw_token = False
            while True:
                event_type, payload = await queue.get()
                if event_type == "model":
                    model_name = str(payload)
                    continue
                if event_type == "token":
                    saw_token = True
                    yield format_sse("chat_token", {"text": str(payload)})
                    continue
                if event_type == "error":
                    print(f"[ChatStream] Model stream failed: {payload}", flush=True)
                    if not saw_token:
                        fallback_reply = build_empty_chat_fallback_reply(body.risk_summary)
                        yield format_sse("chat_token", {"text": fallback_reply})
                        yield format_sse("chat_complete", {"model": None, "degraded": True})
                    else:
                        yield format_sse("error", {"message": "回答中断，请重试。", "partial": True})
                        yield format_sse("chat_complete", {"model": model_name, "partial": True, "degraded": True})
                    return
                if event_type == "done":
                    yield format_sse("chat_complete", {"model": model_name, "degraded": False})
                    return
        except Exception as exc:
            print(f"[ChatStream] Retrieval failed: {exc}", flush=True)
            fallback_reply = build_empty_chat_fallback_reply(body.risk_summary)
            yield format_sse("chat_token", {"text": fallback_reply})
            yield format_sse("chat_complete", {"model": None, "degraded": True})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/ocr/ingest")
async def ingest_contract_materials(
    files: list[UploadFile] = File(...),
    authorization: Optional[str] = Header(None),
):
    require_current_user(authorization)

    if not files:
        return JSONResponse(status_code=400, content={"error": "请选择要导入的合同材料"})

    try:
        uploaded_files = [await _read_uploaded_contract_file(file) for file in files]
        result = await to_thread(ingest_contract_files, uploaded_files)
    except ValueError as exc:
        return _api_error_response(400, str(exc), "INGEST_VALIDATION_ERROR")
    except Exception as exc:
        _log_internal_exception("ocr-ingest", exc)
        return _api_error_response(500, "\u5408\u540c\u6750\u6599\u5904\u7406\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002", "INGEST_PROCESSING_FAILED")

    return result.to_dict()


@app.post("/api/ocr")
@app.post("/api/ocr/extract")
async def ocr_image(file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    return await ingest_contract_materials(files=[file], authorization=authorization)


@app.post("/api/ocr/queue")
async def queue_ocr_ingest(
    files: list[UploadFile] = File(...),
    authorization: Optional[str] = Header(None),
):
    user = require_current_user(authorization)
    if not files:
        return _api_error_response(400, "请选择要导入的合同材料。", "INGEST_VALIDATION_ERROR")

    try:
        uploaded_files = [await _read_uploaded_contract_file(file) for file in files]
        await to_thread(validate_contract_uploads, uploaded_files)
    except ValueError as exc:
        return _api_error_response(400, str(exc), "INGEST_VALIDATION_ERROR")
    except Exception as exc:
        _log_internal_exception("ocr-queue-read", exc)
        return _api_error_response(500, "合同材料处理失败，请稍后重试。", "INGEST_PROCESSING_FAILED")

    pending = await to_thread(queue_service.get_pending_count, task_type="ocr")
    task_id = await to_thread(queue_service.create_task,
        user_id=user["id"],
        filename=uploaded_files[0].filename if uploaded_files else "",
        task_type="ocr",
        max_retries=settings.ocr_queue_max_retries,
        metadata={
            "file_count": len(uploaded_files),
            "progress_message": "上传已接收，正在排队识别…",
        },
    )

    try:
        await to_thread(stage_ocr_task_files, task_id, uploaded_files)
    except Exception as exc:
        _log_internal_exception("ocr-queue-stage", exc)
        queue_service.update_task_status(
            task_id,
            "failed",
            task_type="ocr",
            last_error="合同材料暂存失败，请稍后重试。",
            error_code="OCR_TASK_STAGE_FAILED",
            progress_message="暂存失败。",
        )
        return _api_error_response(500, "合同材料暂存失败，请稍后重试。", "OCR_TASK_STAGE_FAILED")

    asyncio.create_task(
        ocr_worker.run_queued_ocr(
            task_id=task_id,
            max_retries=settings.ocr_queue_max_retries,
            retry_backoff_seconds=settings.queue_retry_backoff_seconds,
        )
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "queue_position": pending + 1,
        "estimated_wait": f"约 {max(1, pending + 1)} 分钟" if pending > 0 else "即将开始",
    }


@app.get("/api/ocr/queue/{task_id}")
async def get_ocr_task_status(task_id: str, authorization: Optional[str] = Header(None)):
    task = _require_task_owner(task_id, authorization, task_type="ocr")
    return task


@app.post("/api/autofix")
async def autofix_clause(body: dict, authorization: Optional[str] = Header(None)):
    from .agents.logic_review import generate_clause_fix

    require_current_user(authorization)
    fix = generate_clause_fix(
        body.get("clause", ""),
        body.get("issue", ""),
        body.get("suggestion", ""),
        body.get("legal_ref", ""),
    )
    return {"suggestion": fix}


@app.post("/api/review/export-docx")
async def export_review_report_docx(
    body: ExportReportRequest,
    authorization: Optional[str] = Header(None),
):
    require_current_user(authorization)

    paragraphs = [paragraph for paragraph in body.report_paragraphs if paragraph and paragraph.strip()]
    if not paragraphs:
        raise HTTPException(status_code=400, detail="报告内容不能为空")

    docx_bytes = await to_thread(build_report_docx, paragraphs, body.filename)
    download_name = await to_thread(build_report_download_name, body.filename)
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}"},
    )


@app.post("/api/review")
async def create_review(
    body: ContractReviewRequest,
    authorization: Optional[str] = Header(None),
):
    user = require_current_user(authorization)

    session_id = body.session_id or f"session-{uuid.uuid4().hex}"

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in run_review_stream(
                contract_text=body.contract_text,
                session_id=session_id,
                model_key=DEFAULT_MODEL_KEY,
                review_mode=body.review_mode,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)

                if event_type == "breakpoint":
                    breakpoint_payload = event_data or {}
                    await to_thread(
                        store_paused_session,
                        session_id,
                        {
                            "owner": user["id"],
                            "contract_text": body.contract_text,
                            "issues": breakpoint_payload.get("issues", []),
                            "filename": body.filename or "",
                        },
                    )
                yield format_sse(event_type, event_data)

                if event_type == "breakpoint":
                    return
        except Exception as exc:
            _log_internal_exception("review-stream", exc)
            yield format_sse(
                "error",
                _build_sse_error_payload("\u5ba1\u67e5\u4efb\u52a1\u5904\u7406\u4e2d\u65ad\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002", "REVIEW_STREAM_FAILED"),
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/review/confirm/{session_id}")
async def confirm_breakpoint(
    session_id: str,
    body: ConfirmRequest,
    authorization: Optional[str] = Header(None),
):
    user = require_current_user(authorization)

    session_data = load_paused_session(session_id)
    if session_data is None and body.confirmed and body.contract_text.strip():
        session_data = {
            "owner": user["id"],
            "contract_text": body.contract_text,
            "issues": body.issues,
            "filename": body.filename or "",
        }
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    if session_data.get("owner") != user.get("id"):
        raise HTTPException(status_code=403, detail="无权访问该审查会话")

    if not body.confirmed:
        delete_paused_session(session_id)
        return {"status": "cancelled"}

    resumed_session_data = pop_paused_session(session_id)
    if resumed_session_data is not None:
        session_data = resumed_session_data

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in run_aggregation_stream(
                contract_text=session_data["contract_text"],
                session_id=session_id,
                issues=session_data["issues"],
                model_key=DEFAULT_MODEL_KEY,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)
                yield format_sse(event_type, event_data)
        except Exception as exc:
            _log_internal_exception("aggregation-stream", exc)
            yield format_sse(
                "error",
                _build_sse_error_payload("\u62a5\u544a\u751f\u6210\u4e2d\u65ad\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002", "AGGREGATION_STREAM_FAILED"),
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/review/deepen")
async def deepen_review(
    body: DeepReviewRequest,
    authorization: Optional[str] = Header(None),
):
    require_current_user(authorization)

    session_id = body.session_id or f"session-{uuid.uuid4().hex}"

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in run_deep_review_stream(
                contract_text=body.contract_text,
                session_id=session_id,
                issues=body.issues,
                model_key=DEFAULT_MODEL_KEY,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)
                yield format_sse(event_type, event_data)
        except Exception as exc:
            _log_internal_exception("deep-review-stream", exc)
            yield format_sse(
                "error",
                _build_sse_error_payload("\u6df1\u5ea6\u626b\u63cf\u5904\u7406\u4e2d\u65ad\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002", "DEEP_REVIEW_STREAM_FAILED"),
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/review/queue")
async def queue_review(
    body: ContractReviewRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Submit a contract review to the background queue.

    Returns immediately with a ``task_id`` that the client can use to
    stream progress via ``GET /api/review/queue/{task_id}/stream``.
    Useful when the server is under load and cannot start a review inline.
    """
    user = require_current_user(authorization)
    session_id = body.session_id or f"session-{uuid.uuid4().hex}"

    pending = await to_thread(queue_service.get_pending_count, task_type="review")
    task_id = await to_thread(queue_service.create_task,
        user_id=user["id"],
        contract_text=body.contract_text,
        session_id=session_id,
        filename=body.filename or "",
        review_mode=body.review_mode,
        task_type="review",
        max_retries=settings.review_queue_max_retries,
    )

    def _on_breakpoint(sid: str, session_data: dict) -> None:
        store_paused_session(sid, session_data)

    asyncio.create_task(
        review_worker.run_queued_review(
            task_id=task_id,
            contract_text=body.contract_text,
            session_id=session_id,
            user_id=user["id"],
            review_mode=body.review_mode,
            on_breakpoint=_on_breakpoint,
            max_retries=settings.review_queue_max_retries,
            retry_backoff_seconds=settings.queue_retry_backoff_seconds,
        )
    )

    return {
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "queue_position": pending + 1,
        "estimated_wait": f"约 {max(1, pending) * 2} 分钟" if pending > 0 else "即将开始",
    }


@app.get("/api/review/queue/{task_id}")
async def get_queue_task_status(
    task_id: str,
    authorization: Optional[str] = Header(None),
):
    """Return the current status of a queued review task."""
    return _require_task_owner(task_id, authorization, task_type="review")


@app.get("/api/review/queue/{task_id}/stream")
async def stream_queue_task(
    task_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    SSE stream for a queued review task.

    The endpoint polls the Redis event list and relays events to the client
    as they are produced by the background worker.  The stream closes when
    the worker pushes the internal ``_done`` sentinel or the task reaches a
    terminal status (completed / failed / paused).
    """
    _require_task_owner(task_id, authorization, task_type="review")

    async def event_generator() -> AsyncGenerator[bytes, None]:
        offset = 0
        poll_interval = 0.5      # seconds between Redis polls
        idle_polls = 0
        max_idle_polls = 120     # 60 s of silence → timeout

        while True:
            events = await to_thread(queue_service.get_events, task_id, offset, task_type="review")

            if events:
                idle_polls = 0
                for ev in events:
                    event_type = ev.get("event", "message")
                    # Internal sentinel — close the stream
                    if event_type == queue_service.DONE_SENTINEL:
                        return
                    yield format_sse(event_type, ev.get("data", {}))
                offset += len(events)
            else:
                idle_polls += 1
                # Also exit if the worker already marked the task terminal
                current_task = await to_thread(queue_service.get_task, task_id, task_type="review")
                if current_task and current_task.get("status") in (
                    "completed", "failed", "paused", "dead_letter", "cancelled"
                ):
                    return
                if idle_polls >= max_idle_polls:
                    yield format_sse("error", {"message": "任务等待超时，请刷新页面重试"})
                    return

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

