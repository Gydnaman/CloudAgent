from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class HealthDTO(BaseModel):
    status: str


class ApiErrorDTO(BaseModel):
    code: str
    message: str
    run_id: str | None = None


class SubjectDTO(BaseModel):
    id: str
    label: str
    role: str


class CreatedSessionDTO(BaseModel):
    session_id: UUID
    subject_id: str
    subject_label: str
    demo_session_token: str
    token_expires_at: datetime
    source: str


class MessageDTO(BaseModel):
    role: str
    content: str
    source: str
    run_id: UUID


class SessionDTO(BaseModel):
    session_id: UUID
    subject_id: str
    token_expires_at: datetime
    closed_at: datetime | None
    messages: list[MessageDTO]


class RunEventDTO(BaseModel):
    event_id: UUID
    run_id: UUID
    sequence: int
    created_at: datetime
    type: str
    payload: dict[str, Any]


class ClosedSessionDTO(BaseModel):
    session_id: UUID
    closed_at: datetime
    close_run_id: UUID | None
    terminal_event: RunEventDTO | None


class RunDTO(BaseModel):
    run_id: UUID
    session_id: UUID
    status: str
    intent: str | None
    agent_path: str | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None


class ProviderDTO(BaseModel):
    name: str
    status: str
    mode: str


class ProviderStatusDTO(BaseModel):
    providers: list[ProviderDTO]


class KnowledgeSourceDTO(BaseModel):
    id: str
    name: str
    type: str
    status: str


class ToolDTO(BaseModel):
    name: str
    type: str
    status: str


class CatalogDTO(BaseModel):
    knowledge: list[KnowledgeSourceDTO]
    tools: list[ToolDTO]
