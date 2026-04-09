"""
Contract Review Copilot — FastAPI Backend
SSE streaming endpoint + LangGraph StateGraph orchestration
"""
import asyncio
import json
import re
import uuid
from contextlib import asynccontextmanager
from io import BytesIO
from typing import AsyncGenerator, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from .cache import build_cache_key, close_redis_client, delete_json, get_json, get_ttl_seconds, set_json
from .config import get_settings
from .llm_client import DEFAULT_MODEL_KEY, available_models, create_chat_completion, is_supported_model_key, resolve_model
from .report_export import build_report_docx, build_report_download_name
from .schemas import (
    ConfirmRequest,
    ContractReviewRequest,
    ExportReportRequest,
    HealthResponse,
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
)
from .graph.review_graph import run_review_stream, run_aggregation_stream
from . import auth


# In-memory store for paused sessions: session_id -> {contract_text, issues}
paused_sessions: dict[str, dict] = {}


def _session_cache_key(session_id: str) -> str:
    return build_cache_key("session", {"session_id": session_id})


def store_paused_session(session_id: str, session_data: dict) -> None:
    paused_sessions[session_id] = session_data
    set_json(_session_cache_key(session_id), session_data, get_ttl_seconds("session"))


def load_paused_session(session_id: str) -> dict | None:
    cached_session = get_json(_session_cache_key(session_id))
    if isinstance(cached_session, dict):
        paused_sessions[session_id] = cached_session
        return cached_session
    return paused_sessions.get(session_id)


def delete_paused_session(session_id: str) -> None:
    paused_sessions.pop(session_id, None)
    delete_json(_session_cache_key(session_id))


def pop_paused_session(session_id: str) -> dict | None:
    session_data = load_paused_session(session_id)
    if session_data is not None:
        delete_paused_session(session_id)
    return session_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Contract Review Copilot API started")
    yield
    paused_sessions.clear()
    close_redis_client()
    print("👋 Contract Review Copilot API stopped")


app = FastAPI(
    title="Contract Review Copilot API",
    description="AI-powered contract review with LangGraph agent orchestration",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
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
    """Extract and validate user from Authorization: Bearer <token> header."""
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return auth.get_user_from_token(token)


def require_current_user(authorization: Optional[str]) -> dict:
    """Require a valid user token for protected endpoints."""
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


# ── Auth Endpoints ────────────────────────────────────────────────

@app.post("/api/auth/send-code")
async def send_code(body: SendCodeRequest):
    """Send a verification code to the given email."""
    email = body.email.strip().lower()

    # Validate email format
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})

    result = auth.send_verification_code(email)
    if not result.get("success"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "发送失败")})

    # In dev mode, return the code directly
    if "dev_code" in result:
        return {"success": True, "dev_code": result["dev_code"]}
    return {"success": True}


@app.post("/api/auth/register")
async def register(body: RegisterRequest):
    """Register a new user with email verification code + password."""
    email = body.email.strip().lower()
    code = body.code.strip()
    password = body.password.strip()

    if not email or not code or not password:
        return JSONResponse(status_code=400, content={"error": "邮箱、验证码和密码不能为空"})
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
        return JSONResponse(status_code=400, content={"error": "无效的邮箱格式"})
    if len(password) < 6:
        return JSONResponse(status_code=400, content={"error": "密码不能少于6位"})

    result = auth.register_user(email, code, password)
    if not result.get("success"):
        return JSONResponse(status_code=400, content={"error": result.get("error", "注册失败")})

    return {"success": True, "message": "注册成功，请登录"}


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    """Login with email + password, return JWT token."""
    email = body.email.strip().lower()
    password = body.password.strip()

    if not email or not password:
        return JSONResponse(status_code=400, content={"error": "邮箱和密码不能为空"})

    token = auth.login_with_password(email, password)
    if not token:
        return JSONResponse(status_code=401, content={"error": "邮箱或密码错误"})

    user = auth.get_user_from_token(token)
    return {
        "success": True,
        "token": token,
        "user": {
            "email": user.get("email") if user else email,
            "id": user.get("email", "").split("@")[0] if user else email.split("@")[0],
        },
    }


@app.get("/api/auth/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current user info from JWT token."""
    user = get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"error": "未登录"})
    return {"user": user}


# ── Protected Review Endpoints ────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/api/models")
async def list_models():
    """Return the chat models available to the frontend."""
    return {
        "models": available_models(),
        "default_model": DEFAULT_MODEL_KEY,
    }


@app.post("/api/chat")
async def chat(body: dict, authorization: Optional[str] = Header(None)):
    """Answer user questions about the current review using the selected model."""
    require_current_user(authorization)

    message = body.get("message", "").strip()
    model_key = (body.get("model") or DEFAULT_MODEL_KEY).strip()
    contract_text = body.get("contract_text", "")
    risk_summary = body.get("risk_summary", "")

    if not message:
        return JSONResponse(status_code=400, content={"error": "消息不能为空"})
    if not is_supported_model_key(model_key):
        return JSONResponse(status_code=400, content={"error": "不支持的模型"})

    context_sections = []
    if contract_text:
        context_sections.append(f"合同原文（节选）：\n{contract_text[:3000]}")
    if risk_summary:
        context_sections.append(f"已识别风险条款：\n{risk_summary[:2000]}")

    system_prompt = (
        "你是一个专业的合同审查助手。请基于合同原文和已识别风险回答用户问题，"
        "结论要简洁直接，优先指出风险、影响和可执行建议。"
    )
    if context_sections:
        system_prompt = f"{system_prompt}\n\n" + "\n\n".join(context_sections)

    try:
        resolved = resolve_model(model_key)
        response = create_chat_completion(
            model=model_key,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
            max_tokens=1024,
            timeout=30.0,
        )
        reply = (response.choices[0].message.content or "").strip()
        return {
            "reply": reply,
            "model": getattr(response, "model", resolved.model_id) or resolved.model_id,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/autofix")
async def autofix_clause(body: dict, authorization: Optional[str] = Header(None)):
    """Generate a suggested clause revision for a problematic clause."""
    from .agents.logic_review import generate_clause_fix
    require_current_user(authorization)

    clause = body.get("clause", "")
    issue = body.get("issue", "")
    suggestion = body.get("suggestion", "")
    legal_ref = body.get("legal_ref", "")

    fix = generate_clause_fix(clause, issue, suggestion, legal_ref)
    return {"suggestion": fix}


@app.post("/api/review/export-docx")
async def export_review_report_docx(
    body: ExportReportRequest,
    authorization: Optional[str] = Header(None),
):
    """Export the generated report as a Word document."""
    require_current_user(authorization)

    paragraphs = [paragraph for paragraph in body.report_paragraphs if paragraph and paragraph.strip()]
    if not paragraphs:
        raise HTTPException(status_code=400, detail="报告内容不能为空")

    docx_bytes = build_report_docx(paragraphs, body.filename)
    download_name = build_report_download_name(body.filename)

    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}",
        },
    )


@app.post("/api/review")
async def create_review(
    body: ContractReviewRequest,
    authorization: Optional[str] = Header(None),
):
    """Start a new contract review session. Returns SSE stream."""
    user = require_current_user(authorization)

    session_id = body.session_id or f"session-{uuid.uuid4().hex}"
    model_key = (body.model or DEFAULT_MODEL_KEY).strip() or DEFAULT_MODEL_KEY
    if not is_supported_model_key(model_key):
        return JSONResponse(status_code=400, content={"error": "不支持的模型"})

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in run_review_stream(
                contract_text=body.contract_text,
                session_id=session_id,
                model_key=model_key,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)
                yield format_sse(event_type, event_data)

                if event_type == "breakpoint":
                    breakpoint_payload = event_data or {}
                    store_paused_session(session_id, {
                        "owner": user.get("email") or user.get("id"),
                        "contract_text": body.contract_text,
                        "issues": breakpoint_payload.get("issues", []),
                        "model_key": model_key,
                    })
                    return

        except Exception as e:
            yield format_sse("error", {"message": str(e)})

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
    """Resume a paused review session and continue with aggregation."""
    user = require_current_user(authorization)

    session_data = load_paused_session(session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")
    session_owner = session_data.get("owner")
    if session_owner and session_owner != (user.get("email") or user.get("id")):
        raise HTTPException(status_code=403, detail="无权访问该审查会话")

    if not body.confirmed:
        delete_paused_session(session_id)
        return {"status": "cancelled"}

    session_data = pop_paused_session(session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in run_aggregation_stream(
                contract_text=session_data["contract_text"],
                session_id=session_id,
                issues=session_data["issues"],
                model_key=session_data.get("model_key"),
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", event)
                yield format_sse(event_type, event_data)
        except Exception as e:
            yield format_sse("error", {"message": str(e)})

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
