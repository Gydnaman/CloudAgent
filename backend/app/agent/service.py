import asyncio
import hashlib
import hmac
import logging
import secrets
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agent.graph import AgentRuntime
from app.auth.context import AuthContextProvider, DemoRunContext
from app.core.config import settings
from app.core.errors import ApiError
from app.persistence.db import Session
from app.persistence.models import AgentRun, Conversation, Message, RunEvent

TERMINAL = {"run.completed", "run.failed", "run.cancelled"}
logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(UTC)


def normalize_message(message: str) -> str:
    normalized = unicodedata.normalize("NFC", message).strip()
    if not 1 <= len(normalized) <= 4000:
        raise ApiError(422, "invalid_message", "消息长度须为 1 至 4,000 个字符")
    return normalized


def request_digest(message: str) -> str:
    return hashlib.sha256(normalize_message(message).encode()).hexdigest()


def token_valid(row: Conversation, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(digest, row.token_digest) and row.token_expires_at > now()


def event_dict(event: RunEvent) -> dict:
    return {"event_id": str(event.id), "run_id": str(event.run_id), "sequence": event.sequence,
            "created_at": event.created_at.isoformat(), "type": event.type, "payload": event.payload}


def run_dict(run: AgentRun) -> dict:
    return {"run_id": str(run.id), "session_id": str(run.session_id), "status": run.status,
            "intent": run.intent, "agent_path": run.agent_path, "error_code": run.error_code,
            "started_at": run.started_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None}


@dataclass
class RunControl:
    run_id: uuid.UUID
    session_id: uuid.UUID
    gate: asyncio.Lock = field(default_factory=asyncio.Lock)
    writer: asyncio.Lock = field(default_factory=asyncio.Lock)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


class DemoService:
    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self.auth = AuthContextProvider()
        self.capacity = asyncio.Lock()
        self.active: dict[uuid.UUID, RunControl] = {}

    async def locked_session(self, db, session_id: uuid.UUID, token: str, allow_closed: bool = False) -> Conversation:
        row = await db.scalar(select(Conversation).where(Conversation.id == session_id).with_for_update())
        if row is None:
            raise ApiError(404, "session_not_found", "会话不存在")
        if not token_valid(row, token):
            raise ApiError(401, "invalid_session_token", "会话凭据无效或已过期")
        if row.closed_at is not None and not allow_closed:
            raise ApiError(403, "session_closed", "会话已关闭")
        return row

    async def create_session(self, subject_id: str) -> dict:
        subject = self.auth.resolve(subject_id)
        async with self.capacity, Session.begin() as db:
            count = await db.scalar(select(func.count()).select_from(Conversation))
            if count >= settings.max_sessions:
                raise ApiError(409, "demo_capacity_reached", "演示会话已达上限，请重置本地数据")
            token = secrets.token_urlsafe(32)
            timestamp = now()
            row = Conversation(id=uuid.uuid4(), subject_id=subject.id,
                               token_digest=hashlib.sha256(token.encode()).hexdigest(),
                               token_expires_at=timestamp + timedelta(hours=8),
                               created_at=timestamp, updated_at=timestamp)
            db.add(row)
        return {"session_id": str(row.id), "subject_id": subject.id, "subject_label": subject.label,
                "demo_session_token": token, "token_expires_at": row.token_expires_at.isoformat(), "source": "mock"}

    async def get_session(self, session_id: uuid.UUID, token: str) -> dict:
        async with Session.begin() as db:
            row = await self.locked_session(db, session_id, token)
            messages = (await db.scalars(select(Message).where(Message.session_id == session_id)
                                         .order_by(Message.created_at))).all()
            return {"session_id": str(row.id), "subject_id": row.subject_id,
                    "token_expires_at": row.token_expires_at.isoformat(), "closed_at": None,
                    "messages": [{"role": msg.role, "content": msg.content, "source": msg.source,
                                  "run_id": str(msg.run_id)} for msg in messages]}

    async def _duplicate_error(self, session_id: uuid.UUID, key: uuid.UUID, request_hash: str) -> ApiError:
        async with Session() as db:
            prior = await db.scalar(select(AgentRun).where(AgentRun.session_id == session_id, AgentRun.idempotency_key == key))
            if prior:
                code = "duplicate_request" if prior.request_hash == request_hash else "idempotency_conflict"
                return ApiError(409, code, "该幂等键已用于此会话", str(prior.id))
            running = await db.scalar(select(AgentRun).where(AgentRun.session_id == session_id, AgentRun.status == "running"))
            if running:
                return ApiError(409, "run_in_progress", "该会话已有运行", str(running.id))
        return ApiError(409, "run_in_progress", "并发请求冲突，请重试")

    async def start_run(self, session_id: uuid.UUID, token: str, key: uuid.UUID, message: str) -> tuple[RunControl, dict]:
        message = normalize_message(message)
        request_hash = request_digest(message)
        run_id = uuid.uuid4()
        control = RunControl(run_id, session_id)
        async with self.capacity:
            try:
                async with Session.begin() as db:
                    row = await self.locked_session(db, session_id, token)
                    prior = await db.scalar(select(AgentRun).where(AgentRun.session_id == session_id, AgentRun.idempotency_key == key))
                    if prior:
                        code = "duplicate_request" if prior.request_hash == request_hash else "idempotency_conflict"
                        raise ApiError(409, code, "该幂等键已用于此会话", str(prior.id))
                    running = await db.scalar(select(AgentRun).where(AgentRun.session_id == session_id, AgentRun.status == "running"))
                    if running:
                        raise ApiError(409, "run_in_progress", "该会话已有运行", str(running.id))
                    count = await db.scalar(select(func.count()).select_from(AgentRun))
                    if count >= settings.max_runs:
                        raise ApiError(409, "demo_capacity_reached", "演示运行已达上限，请重置本地数据")
                    if len(self.active) >= settings.max_active_runs:
                        raise ApiError(429, "global_run_limit", "同时运行数量已达上限")
                    self.active[run_id] = control  # reserve before the database transaction commits
                    timestamp = now()
                    db.add(AgentRun(id=run_id, session_id=session_id, idempotency_key=key,
                                    request_hash=request_hash, status="running", started_at=timestamp))
                    db.add(Message(id=uuid.uuid4(), session_id=session_id, run_id=run_id,
                                   role="user", content=message, source="mock", created_at=timestamp))
                    started = RunEvent(id=uuid.uuid4(), run_id=run_id, sequence=1, type="run.started",
                                       payload={"source": "mock"}, created_at=timestamp)
                    db.add(started)
                    subject_id = row.subject_id
                first = event_dict(started)
                await control.queue.put(first)
                await self._launch(control, session_id, subject_id, message)
                return control, first
            except IntegrityError:
                self.active.pop(run_id, None)
                raise await self._duplicate_error(session_id, key, request_hash) from None
            except BaseException:
                self.active.pop(run_id, None)
                raise

    async def _launch(self, control: RunControl, session_id: uuid.UUID, subject_id: str, message: str) -> None:
        async with Session.begin() as db:
            await db.scalar(select(Conversation).where(Conversation.id == session_id).with_for_update())
            async with control.gate:
                run = await db.get(AgentRun, control.run_id)
                if run.status == "running":
                    control.task = asyncio.create_task(self._execute(control, session_id, subject_id, message))

    async def _execute(self, control: RunControl, session_id: uuid.UUID, subject_id: str, message: str) -> None:
        async def emit(kind: str, payload: dict) -> None:
            await self.emit(control, session_id, kind, payload)

        try:
            subject = self.auth.resolve(subject_id)
            async with Session() as db:
                history_rows = (await db.scalars(select(Message).join(AgentRun, AgentRun.id == Message.run_id)
                                                 .where(Message.session_id == session_id, Message.role == "user",
                                                        AgentRun.status == "completed")
                                                 .order_by(Message.created_at))).all()
            context = DemoRunContext(subject=subject, emit=emit)
            state = await asyncio.wait_for(self.runtime.invoke(message, [m.content for m in history_rows], context, str(control.run_id)), 120)
            await self.emit(control, session_id, "run.completed", {"answer": state["answer"], "source": "mock", "source_ids": state.get("source_ids", [])})
        except TimeoutError:
            await self.emit(control, session_id, "run.failed", {"error_code": "run_timeout"})
        except asyncio.CancelledError:
            try:
                await self.emit(control, session_id, "run.cancelled", {"reason": "client_disconnected"})
            except Exception as error:  # noqa: BLE001 - database failure is reconciled later
                logger.error("terminal persistence failed run_id=%s category=%s", control.run_id, type(error).__name__)
            raise
        except Exception as error:  # noqa: BLE001 - graph/provider failure maps to a stable terminal code
            logger.error("runtime failed run_id=%s category=%s", control.run_id, type(error).__name__)
            try:
                await self.emit(control, session_id, "run.failed", {"error_code": "runtime_error"})
            except Exception as persistence_error:  # noqa: BLE001 - reconciliation handles storage outages
                logger.error("terminal persistence failed run_id=%s category=%s", control.run_id, type(persistence_error).__name__)

    async def emit(self, control: RunControl, session_id: uuid.UUID, kind: str, payload: dict) -> dict | None:
        # Lock order: session row -> per-run gate -> event writer.
        for delay in (0, 0.1, 0.3, 0.9):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with Session.begin() as db:
                    await db.scalar(select(Conversation).where(Conversation.id == session_id).with_for_update())
                    async with control.gate, control.writer:
                            run = await db.scalar(select(AgentRun).where(AgentRun.id == control.run_id).with_for_update())
                            if run.status != "running":
                                return None
                            seq = (await db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run.id))) + 1
                            timestamp = now()
                            event = RunEvent(id=uuid.uuid4(), run_id=run.id, sequence=seq,
                                             type=kind, payload=payload, created_at=timestamp)
                            db.add(event)
                            if kind == "route.selected" or kind == "route.unsupported":
                                run.intent = payload["intent"]
                                run.agent_path = payload["intent"]
                            if kind in TERMINAL:
                                run.status = kind.split(".")[1]
                                run.finished_at = timestamp
                                run.error_code = payload.get("error_code")
                                if kind == "run.completed":
                                    db.add(Message(id=uuid.uuid4(), session_id=session_id, run_id=run.id,
                                                   role="assistant", content=payload["answer"],
                                                   source="mock", created_at=timestamp))
                result = event_dict(event)
                await control.queue.put(result)
                if kind in TERMINAL:
                    self.active.pop(control.run_id, None)
                return result
            except Exception:
                if delay == 0.9:
                    self.active.pop(control.run_id, None)
                    await control.queue.put(None)
                    task = control.task
                    if task and task is not asyncio.current_task():
                        task.cancel()
                    raise
        return None

    async def cancel(self, run_id: uuid.UUID, reason: str) -> dict | None:
        control = self.active.get(run_id)
        if not control:
            return None
        async with Session() as db:
            run = await db.get(AgentRun, run_id)
        event = await self.emit(control, run.session_id, "run.cancelled", {"reason": reason})
        if control.task and not control.task.done():
            control.task.cancel()
        return event

    async def close_session(self, session_id: uuid.UUID, token: str) -> dict:
        async with Session.begin() as db:
            row = await self.locked_session(db, session_id, token, allow_closed=True)
            if row.closed_at:
                terminal = await self._terminal_in_db(db, row.close_run_id)
                return {"session_id": str(session_id), "closed_at": row.closed_at.isoformat(),
                        "close_run_id": str(row.close_run_id) if row.close_run_id else None, "terminal_event": terminal}
            # Resolve the in-process control only after owning the session row lock.
            # A start_run that held the row lock before this request is now visible here.
            control = next((item for item in self.active.values() if item.session_id == session_id), None)
            active_run = await db.get(AgentRun, control.run_id) if control else None
            terminal = None
            if control:
                async with control.gate, control.writer:
                        await db.refresh(active_run)
                        if active_run.status == "running":
                            active_run.status = "cancelled"
                            active_run.finished_at = now()
                            seq = (await db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == active_run.id))) + 1
                            event = RunEvent(id=uuid.uuid4(), run_id=active_run.id, sequence=seq,
                                             type="run.cancelled", payload={"reason": "session_closed"}, created_at=now())
                            db.add(event)
                            terminal = event_dict(event)
                        else:
                            terminal = await self._terminal_in_db(db, active_run.id)
                        row.close_run_id = active_run.id
            row.closed_at = now()
            row.updated_at = row.closed_at
            result = {"session_id": str(session_id), "closed_at": row.closed_at.isoformat(),
                      "close_run_id": str(row.close_run_id) if row.close_run_id else None,
                      "terminal_event": terminal}
        if control:
            if terminal and terminal["type"] == "run.cancelled":
                await control.queue.put(terminal)
            if control.task and not control.task.done():
                control.task.cancel()
            self.active.pop(control.run_id, None)
        return result

    async def _terminal_in_db(self, db, run_id: uuid.UUID | None) -> dict | None:
        if run_id is None:
            return None
        event = await db.scalar(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.type.in_(TERMINAL)))
        return event_dict(event) if event else None

    async def get_run(self, run_id: uuid.UUID, token: str) -> dict:
        async with Session.begin() as db:
            run = await db.get(AgentRun, run_id)
            if not run:
                raise ApiError(404, "run_not_found", "运行不存在")
            await self.locked_session(db, run.session_id, token)
        await self.reconcile_one(run_id)
        async with Session.begin() as db:
            run = await db.get(AgentRun, run_id)
            await self.locked_session(db, run.session_id, token)
            return run_dict(run)

    async def get_events(self, run_id: uuid.UUID, token: str) -> list[dict]:
        async with Session.begin() as db:
            run = await db.get(AgentRun, run_id)
            if not run:
                raise ApiError(404, "run_not_found", "运行不存在")
            await self.locked_session(db, run.session_id, token)
        await self.reconcile_one(run_id)
        async with Session.begin() as db:
            run = await db.get(AgentRun, run_id)
            await self.locked_session(db, run.session_id, token)
            events = (await db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence))).all()
            return [event_dict(event) for event in events]

    async def reconcile_one(self, run_id: uuid.UUID) -> None:
        if run_id in self.active:
            return
        async with Session() as db:
            existing = await db.get(AgentRun, run_id)
            if existing is None:
                return
            session_id = existing.session_id
        async with Session.begin() as db:
            await db.scalar(select(Conversation).where(Conversation.id == session_id).with_for_update())
            run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None or run.status != "running":
                return
            run.status = "failed"
            run.error_code = "runtime_interrupted"
            run.finished_at = now()
            seq = (await db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run.id))) + 1
            db.add(RunEvent(id=uuid.uuid4(), run_id=run.id, sequence=seq, type="run.failed",
                            payload={"error_code": "runtime_interrupted"}, created_at=now()))

    async def reconcile_all(self) -> None:
        async with Session() as db:
            ids = (await db.scalars(select(AgentRun.id).where(AgentRun.status == "running"))).all()
        for run_id in ids:
            await self.reconcile_one(run_id)
