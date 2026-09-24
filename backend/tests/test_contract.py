import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from starlette.requests import Request

from app.agent.graph import AgentRuntime, route_question
from app.agent.service import (
    DemoService,
    RunControl,
    normalize_message,
    request_digest,
    token_valid,
)
from app.auth.context import DemoRunContext
from app.core.errors import ApiError
from app.fixtures.data import SUBJECTS
from app.main import app, stream_run
from app.persistence.models import Conversation
from app.tools.mock import MockToolProvider


def test_fixed_routes_and_nfc_hash() -> None:
    assert route_question("产品支持哪些部署版本？") == "product"
    assert route_question("查询我的账户用量") == "billing"
    assert route_question("今天下雨吗？") == "unsupported"
    assert normalize_message("  e\u0301  ") == "é"
    assert request_digest("  e\u0301  ") == request_digest("é")
    assert request_digest("é") == hashlib.sha256("é".encode()).hexdigest()
    assert len(normalize_message("x" * 4000)) == 4000
    with pytest.raises(ApiError):
        normalize_message("x" * 4001)
    with pytest.raises(ApiError) as raised:
        normalize_message("  ")
    assert raised.value.detail["code"] == "invalid_message"


def test_openapi_describes_manual_json_and_required_headers() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    create_session = paths["/api/v1/sessions"]["post"]
    session_schema = create_session["requestBody"]["content"]["application/json"]["schema"]
    assert session_schema["required"] == ["subject_id"]
    assert session_schema["additionalProperties"] is False

    stream = paths["/api/v1/sessions/{session_id}/runs/stream"]["post"]
    run_schema = stream["requestBody"]["content"]["application/json"]["schema"]
    assert run_schema["required"] == ["message"]
    assert run_schema["additionalProperties"] is False
    headers = {item["name"].lower(): item for item in stream["parameters"]}
    assert headers["x-demo-session-token"]["required"] is True
    assert headers["idempotency-key"]["required"] is True
    assert "401" in stream["responses"]
    assert "409" in stream["responses"]

    get_session = paths["/api/v1/sessions/{session_id}"]["get"]
    token_header = next(p for p in get_session["parameters"] if p["name"].lower() == "x-demo-session-token")
    assert token_header["required"] is True


@pytest.mark.parametrize("question", ["账单什么时候到？", "计费规则是什么？", "账户怎么开通？"])
def test_billing_route_requires_explicit_usage_query(question: str) -> None:
    assert route_question(question) == "unsupported"


@pytest.mark.asyncio
async def test_graph_uses_completed_history_for_a_product_follow_up() -> None:
    runtime = AgentRuntime(InMemorySaver())
    events: list[str] = []

    async def emit(kind: str, _payload: dict) -> None:
        events.append(kind)

    result = await runtime.invoke(
        "还支持别的吗？", ["产品支持哪些部署版本？"],
        DemoRunContext(SUBJECTS["demo-alice"], emit), str(uuid.uuid4())
    )
    assert result["intent"] == "product"
    assert result["source_ids"] == ["product-compatibility"]
    assert "knowledge.search.completed" in events


@pytest.mark.asyncio
async def test_graph_checkpoint_does_not_store_prompt_or_history() -> None:
    checkpointer = InMemorySaver()
    runtime = AgentRuntime(checkpointer)
    run_id = str(uuid.uuid4())
    question = "PRIVATE_CURRENT_PROMPT_9c7a"
    history = ["PRIVATE_PREVIOUS_PROMPT_42bd"]

    await runtime.invoke(
        question, history,
        DemoRunContext(SUBJECTS["demo-alice"], AsyncMock()),
        run_id,
    )

    snapshot = await runtime.graph.aget_state({"configurable": {"thread_id": run_id}})
    assert "question" not in snapshot.values
    assert "history" not in snapshot.values
    assert question not in repr(snapshot.values)
    assert history[0] not in repr(snapshot.values)


@pytest.mark.asyncio
async def test_read_only_tool_denial_never_calls_adapter(monkeypatch) -> None:
    tool = MockToolProvider()
    read = AsyncMock(return_value={"units": 42})
    monkeypatch.setattr(tool, "read_usage", read)
    alice = SUBJECTS["demo-alice"]
    denied = await tool.invoke("read_account_usage", {"account_id": "acct-bob"}, alice)
    malformed = await tool.invoke("read_account_usage", {"account_id": "acct-alice", "extra": 1}, alice)
    unknown = await tool.invoke("write_account_usage", {"account_id": "acct-alice"}, alice)
    assert [denied["reason"], malformed["reason"], unknown["reason"]] == ["resource_not_owned", "invalid_args", "tool_not_allowed"]
    read.assert_not_awaited()
    allowed = await tool.invoke("read_account_usage", {"account_id": "acct-alice"}, alice)
    assert allowed["allowed"] is True
    read.assert_awaited_once_with("acct-alice")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "expected_intent", "expected_marker", "forbidden_marker"),
    [
        ("产品支持哪些部署版本？", "product", "knowledge.search.completed", "tool.completed"),
        ("产品的 SLA 是多少？", "product", "knowledge.empty", "tool.completed"),
        ("查询我的账户用量", "billing", "tool.completed", "tool.skipped"),
        ("查询其他账户用量", "billing", "tool.skipped", "tool.completed"),
        ("今天天气如何？", "unsupported", "route.unsupported", "agent.started"),
    ],
)
async def test_graph_fixed_scenarios(question, expected_intent, expected_marker, forbidden_marker) -> None:
    runtime = AgentRuntime(InMemorySaver())
    kinds: list[str] = []

    async def emit(kind: str, _payload: dict) -> None:
        kinds.append(kind)

    result = await runtime.invoke(question, [], DemoRunContext(SUBJECTS["demo-alice"], emit), str(uuid.uuid4()))
    assert result["intent"] == expected_intent
    assert expected_marker in kinds
    assert forbidden_marker not in kinds
    if expected_marker == "tool.skipped":
        assert "未执行" in result["answer"]
    if expected_marker == "knowledge.empty":
        assert "没有匹配" in result["answer"]


def make_conversation(token: str, *, expired: bool = False, closed: bool = False) -> Conversation:
    timestamp = datetime.now(UTC)
    return Conversation(
        id=uuid.uuid4(), subject_id="demo-alice", token_digest=hashlib.sha256(token.encode()).hexdigest(),
        token_expires_at=timestamp + (timedelta(seconds=-1) if expired else timedelta(hours=8)),
        created_at=timestamp, updated_at=timestamp,
        closed_at=timestamp if closed else None, close_run_id=uuid.uuid4() if closed else None,
    )


def test_token_digest_and_expiry() -> None:
    row = make_conversation("synthetic-token")
    assert token_valid(row, "synthetic-token")
    assert not token_valid(row, "wrong")
    assert not token_valid(make_conversation("synthetic-token", expired=True), "synthetic-token")


@pytest.mark.asyncio
async def test_closed_session_replays_same_result_and_expired_token_rejects(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token", closed=True)
    terminal = {"event_id": str(uuid.uuid4()), "run_id": str(row.close_run_id),
                "sequence": 7, "type": "run.cancelled", "payload": {"reason": "session_closed"}}

    class FakeDb:
        async def scalar(self, _query):
            return row

    class FakeSession:
        @staticmethod
        @asynccontextmanager
        async def begin():
            yield FakeDb()

    monkeypatch.setattr(service_module, "Session", FakeSession)
    service = DemoService(runtime=object())
    service._terminal_in_db = AsyncMock(return_value=terminal)
    first = await service.close_session(row.id, "synthetic-token")
    second = await service.close_session(row.id, "synthetic-token")
    assert first == second
    assert first["terminal_event"] == terminal
    assert first["close_run_id"] == str(row.close_run_id)
    with pytest.raises(ApiError) as raised:
        await service.close_session(row.id, "wrong")
    assert raised.value.detail["code"] == "invalid_session_token"
    row.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ApiError) as expired:
        await service.close_session(row.id, "synthetic-token")
    assert expired.value.detail["code"] == "invalid_session_token"


@pytest.mark.asyncio
async def test_duplicate_key_wins_over_saturated_active_cap(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token")
    key = uuid.uuid4()
    previous = SimpleNamespace(id=uuid.uuid4(), request_hash=request_digest("same message"))

    class FakeDb:
        async def scalar(self, _query):
            return previous

    class FakeSession:
        @staticmethod
        @asynccontextmanager
        async def begin():
            yield FakeDb()

    monkeypatch.setattr(service_module, "Session", FakeSession)
    service = DemoService(runtime=object())
    service.locked_session = AsyncMock(return_value=row)
    for _ in range(4):
        active = uuid.uuid4()
        service.active[active] = RunControl(active, uuid.uuid4())
    with pytest.raises(ApiError) as raised:
        await service.start_run(row.id, "synthetic-token", key, "same message")
    assert raised.value.status_code == 409
    assert raised.value.detail == {"code": "duplicate_request", "message": "该幂等键已用于此会话", "run_id": str(previous.id)}
    with pytest.raises(ApiError) as conflict:
        await service.start_run(row.id, "synthetic-token", key, "different message")
    assert conflict.value.detail == {"code": "idempotency_conflict", "message": "该幂等键已用于此会话", "run_id": str(previous.id)}
    assert len(service.active) == 4


@pytest.mark.asyncio
async def test_close_returns_completed_terminal_after_registry_removal(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token")
    run_id = uuid.uuid4()
    control = RunControl(run_id, row.id)
    terminal = {"event_id": str(uuid.uuid4()), "run_id": str(run_id),
                "sequence": 5, "type": "run.completed", "payload": {"answer": "DEMO / MOCK"}}
    service = DemoService(runtime=object())
    service.active[run_id] = control

    class FakeDb:
        async def scalar(self, _query):
            return row

        async def get(self, _model, _run_id):
            service.active.pop(run_id)  # completion commits while close waits for its row lock
            return SimpleNamespace(id=run_id, status="completed")

        async def refresh(self, _row):
            return None

        def add(self, _row):
            return None

    class FakeSession:
        @staticmethod
        @asynccontextmanager
        async def begin():
            yield FakeDb()

    monkeypatch.setattr(service_module, "Session", FakeSession)
    service._terminal_in_db = AsyncMock(return_value=terminal)
    result = await service.close_session(row.id, "synthetic-token")
    assert result["close_run_id"] == str(run_id)
    assert result["terminal_event"] == terminal
    assert row.closed_at is not None


@pytest.mark.asyncio
async def test_close_finds_run_registered_while_waiting_for_session_row(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token")
    run_id = uuid.uuid4()
    control = RunControl(run_id, row.id)
    active_run = SimpleNamespace(id=run_id, status="running", finished_at=None)
    service = DemoService(runtime=object())
    service.locked_session = AsyncMock(return_value=row)

    class FakeDb:
        async def get(self, _model, _run_id):
            return active_run

        async def scalar(self, _query):
            return 0

        async def refresh(self, _row):
            return None

        def add(self, _row):
            return None

    class FakeSession:
        @staticmethod
        @asynccontextmanager
        async def begin():
            # Simulate start_run committing after close took its early registry snapshot.
            service.active[run_id] = control
            yield FakeDb()

    monkeypatch.setattr(service_module, "Session", FakeSession)
    result = await service.close_session(row.id, "synthetic-token")
    assert active_run.status == "cancelled"
    assert result["close_run_id"] == str(run_id)
    assert result["terminal_event"]["type"] == "run.cancelled"
    assert control.run_id not in service.active


@pytest.mark.asyncio
async def test_stream_disconnect_cancellation_persists_one_terminal_event(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token")
    run_id = uuid.uuid4()
    active_run = SimpleNamespace(id=run_id, session_id=row.id, status="running", finished_at=None,
                                 error_code=None, intent=None, agent_path=None)
    stored_events = []
    task = asyncio.create_task(asyncio.sleep(30))
    control = RunControl(run_id, row.id, task=task)
    service = DemoService(runtime=object())
    service.active[run_id] = control

    class FakeDb:
        def __init__(self):
            self.scalar_call = 0

        async def get(self, _model, _run_id):
            return active_run

        async def scalar(self, _query):
            self.scalar_call += 1
            return row if self.scalar_call == 1 else active_run if self.scalar_call == 2 else 1

        def add(self, event):
            stored_events.append(event)

    db = FakeDb()

    class FakeSession:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

        @staticmethod
        @asynccontextmanager
        async def begin():
            yield db

    monkeypatch.setattr(service_module, "Session", FakeSession)
    receipt = await service.cancel(run_id, "client_disconnected")
    await asyncio.gather(task, return_exceptions=True)
    assert receipt["type"] == "run.cancelled"
    assert receipt["payload"] == {"reason": "client_disconnected"}
    assert active_run.status == "cancelled"
    assert len(stored_events) == 1 and stored_events[0].type == "run.cancelled"
    assert task.cancelled()


@pytest.mark.asyncio
async def test_http_sse_generator_disconnect_calls_cancel(monkeypatch) -> None:
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    control = RunControl(run_id, session_id)
    control.queue.put_nowait({
        "event_id": str(uuid.uuid4()), "run_id": str(run_id), "sequence": 1,
        "type": "agent.started", "payload": {},
    })
    service = SimpleNamespace(
        start_run=AsyncMock(return_value=(control, False)),
        cancel=AsyncMock(return_value=None),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(service=service))
    async def receive():
        return {"type": "http.request", "body": b'{"message":"test"}', "more_body": False}

    request = Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/v1/sessions/runs/stream",
        "raw_path": b"/api/v1/sessions/runs/stream", "query_string": b"",
        "headers": [
            (b"x-demo-session-token", b"synthetic-token"),
            (b"idempotency-key", str(uuid.uuid4()).encode()),
        ],
        "client": ("test", 1234), "server": ("test", 80), "app": fake_app,
    }, receive=receive)

    response = await stream_run(str(session_id), request)
    first_frame = await response.body_iterator.__anext__()
    assert first_frame.startswith(b"id:")
    await response.body_iterator.aclose()
    service.cancel.assert_awaited_once_with(run_id, "client_disconnected")


@pytest.mark.asyncio
async def test_reconcile_marks_persisted_orphan_run_failed(monkeypatch) -> None:
    import app.agent.service as service_module

    row = make_conversation("synthetic-token")
    run_id = uuid.uuid4()
    orphan = SimpleNamespace(
        id=run_id, session_id=row.id, status="running", error_code=None,
        finished_at=None,
    )
    stored_events = []

    class FakeDb:
        def __init__(self):
            self.scalar_call = 0

        async def get(self, _model, _run_id):
            return orphan

        async def scalar(self, _query):
            self.scalar_call += 1
            return row if self.scalar_call == 1 else orphan if self.scalar_call == 2 else 1

        def add(self, event):
            stored_events.append(event)

    db = FakeDb()

    class FakeSession:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

        @staticmethod
        @asynccontextmanager
        async def begin():
            yield db

    monkeypatch.setattr(service_module, "Session", FakeSession)
    await DemoService(runtime=object()).reconcile_one(run_id)

    assert orphan.status == "failed"
    assert orphan.error_code == "runtime_interrupted"
    assert orphan.finished_at is not None
    assert len(stored_events) == 1
    assert stored_events[0].type == "run.failed"
    assert stored_events[0].payload == {"error_code": "runtime_interrupted"}
