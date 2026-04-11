"""
Contract Review Copilot FastAPI backend.
"""
from __future__ import annotations

import json
import re
import uuid
from asyncio import to_thread
from contextlib import asynccontextmanager
from io import BytesIO
from threading import Lock
from typing import AsyncGenerator, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import auth
from .cache import build_cache_key, close_redis_client, delete_json, get_json, get_ttl_seconds, set_json
from .config import get_settings
from .graph.review_graph import run_aggregation_stream, run_review_stream
from .llm_client import DEFAULT_MODEL_KEY, available_models, create_chat_completion
from .ocr import UploadedContractFile, ingest_contract_files
from .rate_limit import RateLimitRule, enforce_rate_limits, get_request_ip
from .report_export import build_report_docx, build_report_download_name
from .schemas import (
    ChatRequest,
    ConfirmRequest,
    ContractReviewRequest,
    ExportReportRequest,
    HealthResponse,
    LoginRequest,
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
        getattr(message, "reasoning_content", ""),
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
    return UploadedContractFile(
        filename=upload.filename or "contract.bin",
        content=await upload.read(),
        content_type=upload.content_type,
    )


@app.post("/api/auth/send-code")
async def send_code(body: SendCodeRequest, request: Request):
    email = body.email.strip().lower()
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    _enforce_auth_rate_limits(request, email=email, action="auth-email-code")
    result = auth.send_verification_code(email)
    if not result.get("success"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "发送失败")})
    return {"success": True, **({"dev_code": result["dev_code"]} if "dev_code" in result else {})}


@app.post("/api/auth/register")
async def register(body: RegisterRequest, request: Request):
    email = body.email.strip().lower()
    code = body.code.strip()
    password = body.password.strip()

    if not email or not code or not password:
        return JSONResponse(status_code=400, content={"error": "邮箱、验证码和密码不能为空"})
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})
    if len(password) < 6:
        return JSONResponse(status_code=400, content={"error": "密码不能少于 6 位"})

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
        context_sections.append(f"合同原文（节选）：\n{body.contract_text[:3000]}")
    if body.risk_summary:
        context_sections.append(f"已识别风险条款：\n{body.risk_summary[:2000]}")

    system_prompt = (
        "你是一个专业的合同审查助手。请基于合同原文和已识别风险回答用户问题，"
        "结论要简洁直接，优先指出风险、影响和可执行建议。"
    )
    if context_sections:
        system_prompt = f"{system_prompt}\n\n" + "\n\n".join(context_sections)

    try:
        response = create_chat_completion(
            model=DEFAULT_MODEL_KEY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
            max_tokens=1024,
            timeout=90.0,
        )
        reply = extract_chat_reply(response)
        if reply == EMPTY_CHAT_REPLY_TEXT:
            reply = build_empty_chat_fallback_reply(body.risk_summary)
        return {
            "reply": reply,
            "model": getattr(response, "model", settings.review_model) or settings.review_model,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


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
        result = ingest_contract_files(uploaded_files)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return result.to_dict()


@app.post("/api/ocr")
@app.post("/api/ocr/extract")
async def ocr_image(file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    return await ingest_contract_materials(files=[file], authorization=authorization)


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

    docx_bytes = build_report_docx(paragraphs, body.filename)
    download_name = build_report_download_name(body.filename)
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
            yield format_sse("error", {"message": str(exc)})

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
            yield format_sse("error", {"message": str(exc)})

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

