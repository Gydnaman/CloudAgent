import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from alembic import command
from app.agent.graph import AgentRuntime
from app.agent.service import TERMINAL, DemoService
from app.api.schemas import (
    ApiErrorDTO,
    CatalogDTO,
    ClosedSessionDTO,
    CreatedSessionDTO,
    HealthDTO,
    ProviderStatusDTO,
    RunDTO,
    RunEventDTO,
    SessionDTO,
    SubjectDTO,
)
from app.core.config import settings
from app.core.errors import ApiError
from app.fixtures.data import KNOWLEDGE, SUBJECTS
from app.persistence.db import Session, engine


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: str = Field(description="合成演示身份 ID，可从 /api/v1/demo/subjects 获取")


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(description="用户消息；NFC 规范化并裁剪后须为 1 至 4,000 个码点")


def json_body(model: type[BaseModel], example: dict) -> dict:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": model.model_json_schema(), "example": example}},
        }
    }


def required_header(name: str, description: str) -> dict:
    return {
        "name": name,
        "in": "header",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def api_error_responses(*status_codes: int) -> dict[int, dict]:
    return {code: {"model": ApiErrorDTO, "description": "CloudAgent API 错误"} for code in status_codes}


async def parse_json_limited(request: Request) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise ApiError(413, "request_too_large", "请求体不得超过 64 KiB")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "invalid_json", "请求体必须是 JSON") from None
    if not isinstance(value, dict):
        raise ApiError(422, "invalid_body", "请求体必须是对象")
    return value


def require_token(token: str | None) -> str:
    if not token:
        raise ApiError(401, "missing_session_token", "缺少会话凭据")
    return token


def parse_id(raw: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ApiError(422, "invalid_uuid", f"{name} 须为 UUID") from None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    for attempt in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            break
        except Exception:
            if attempt == 29:
                raise
            await asyncio.sleep(1)
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    await asyncio.to_thread(command.upgrade, alembic_config, "head")
    conninfo = settings.database_url.replace("postgresql+psycopg_async://", "postgresql://")
    pool = AsyncConnectionPool(conninfo=conninfo, min_size=1, max_size=5,
                               kwargs={"autocommit": True, "prepare_threshold": 0}, open=False)
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        app.state.service = DemoService(AgentRuntime(saver))
        await app.state.service.reconcile_all()
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        for control in list(app.state.service.active.values()) if hasattr(app.state, "service") else []:
            if control.task:
                control.task.cancel()
        await pool.close()
        await engine.dispose()


app = FastAPI(title="CloudAgent Stage A", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Session-Token", "Idempotency-Key"],
    expose_headers=["X-Run-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; "
        "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 http://127.0.0.1:5173 http://localhost:5173"
    )
    return response


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, error: ApiError):
    return JSONResponse(status_code=error.status_code, content=error.detail)


@app.get("/api/v1/health/live", response_model=HealthDTO)
async def health_live():
    return {"status": "live"}


@app.get("/api/v1/health/ready", response_model=HealthDTO, responses=api_error_responses(503))
async def health_ready(request: Request):
    if not getattr(request.app.state, "ready", False):
        raise ApiError(503, "not_ready", "数据库或运行时尚未就绪")
    async with Session() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/api/v1/demo/subjects", response_model=list[SubjectDTO], responses=api_error_responses(404))
async def subjects():
    if settings.app_env != "local" or not settings.demo_auth_enabled:
        raise ApiError(404, "demo_disabled", "本地演示身份未启用")
    return [{"id": subject.id, "label": subject.label, "role": subject.role}
            for subject in SUBJECTS.values()]


@app.post(
    "/api/v1/sessions",
    response_model=CreatedSessionDTO,
    responses=api_error_responses(400, 404, 409, 413, 422),
    openapi_extra=json_body(SessionInput, {"subject_id": "demo-alice"}),
)
async def create_session(request: Request):
    try:
        data = SessionInput.model_validate(await parse_json_limited(request))
    except ValidationError:
        raise ApiError(422, "invalid_session_request", "请求必须包含有效的 subject_id") from None
    return await request.app.state.service.create_session(data.subject_id)


@app.get(
    "/api/v1/sessions/{session_id}",
    response_model=SessionDTO,
    responses=api_error_responses(401, 403, 404, 422),
    openapi_extra={"parameters": [required_header("x-demo-session-token", "会话凭据") ]},
)
async def get_session(session_id: str, request: Request):
    token = require_token(request.headers.get("x-demo-session-token"))
    return await request.app.state.service.get_session(parse_id(session_id, "session_id"), token)


@app.post(
    "/api/v1/sessions/{session_id}/close",
    response_model=ClosedSessionDTO,
    responses=api_error_responses(401, 403, 404, 409, 422),
    openapi_extra={"parameters": [required_header("x-demo-session-token", "会话凭据")]},
)
async def close_session(session_id: str, request: Request):
    token = require_token(request.headers.get("x-demo-session-token"))
    return await request.app.state.service.close_session(parse_id(session_id, "session_id"), token)


def frame(event: dict) -> bytes:
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['event_id']}\nevent: {event['type']}\ndata: {data}\n\n".encode()


@app.post(
    "/api/v1/sessions/{session_id}/runs/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string", "description": "RunEventDTO SSE frames"}}}},
        **api_error_responses(400, 401, 403, 404, 409, 413, 422, 429),
    },
    openapi_extra={
        **json_body(RunInput, {"message": "产品支持哪些部署版本？"}),
        "parameters": [
            required_header("x-demo-session-token", "会话凭据"),
            required_header("idempotency-key", "每次新消息使用的 UUID 幂等键"),
        ],
    },
)
async def stream_run(session_id: str, request: Request):
    session_uuid = parse_id(session_id, "session_id")
    token = require_token(request.headers.get("x-demo-session-token"))
    idempotency_key = request.headers.get("idempotency-key")
    if not idempotency_key:
        raise ApiError(422, "missing_idempotency_key", "缺少 Idempotency-Key")
    key = parse_id(idempotency_key, "Idempotency-Key")
    try:
        data = RunInput.model_validate(await parse_json_limited(request))
    except ValidationError:
        raise ApiError(422, "invalid_message", "message 须为字符串") from None
    control, _ = await request.app.state.service.start_run(session_uuid, token, key, data.message)

    async def send():
        terminal_seen = False
        expected = 1
        pending: dict[int, dict] = {}
        try:
            while True:
                try:
                    event = await asyncio.wait_for(control.queue.get(), timeout=15)
                except TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                if event is None:
                    break
                pending[event["sequence"]] = event
                while expected in pending:
                    ordered = pending.pop(expected)
                    yield frame(ordered)
                    expected += 1
                    if ordered["type"] in TERMINAL:
                        terminal_seen = True
                        break
                if terminal_seen:
                    break
        finally:
            if not terminal_seen:
                await request.app.state.service.cancel(control.run_id, "client_disconnected")

    return StreamingResponse(send(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Run-ID": str(control.run_id)})


@app.get(
    "/api/v1/runs/{run_id}",
    response_model=RunDTO,
    responses=api_error_responses(401, 403, 404, 422),
    openapi_extra={"parameters": [required_header("x-demo-session-token", "会话凭据")]},
)
async def get_run(run_id: str, request: Request):
    token = require_token(request.headers.get("x-demo-session-token"))
    return await request.app.state.service.get_run(parse_id(run_id, "run_id"), token)


@app.get(
    "/api/v1/runs/{run_id}/events",
    response_model=list[RunEventDTO],
    responses=api_error_responses(401, 403, 404, 422),
    openapi_extra={"parameters": [required_header("x-demo-session-token", "会话凭据")]},
)
async def get_events(run_id: str, request: Request):
    token = require_token(request.headers.get("x-demo-session-token"))
    return await request.app.state.service.get_events(parse_id(run_id, "run_id"), token)


@app.get("/api/v1/providers/status", response_model=ProviderStatusDTO)
async def provider_status():
    return {"providers": [{"name": "Mock", "status": "available", "mode": "mock"},
                          {"name": "Live", "status": "not_connected", "mode": "live"}]}


@app.get("/api/v1/catalog", response_model=CatalogDTO)
async def catalog():
    return {"knowledge": [{"id": key, "name": item["title"], "type": "mock_fixture", "status": "available"}
                          for key, item in KNOWLEDGE.items()],
            "tools": [{"name": "read_account_usage", "type": "mock_read_only", "status": "available"}]}


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
