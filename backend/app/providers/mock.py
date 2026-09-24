from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMRequest:
    answer: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    source: str = "mock"


@dataclass(frozen=True)
class LLMChunk:
    text: str


class LLMProvider(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...
    async def health(self) -> dict: ...


class MockLLMProvider:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(request.answer)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        for i in range(0, len(request.answer), 12):
            yield LLMChunk(request.answer[i:i + 12])

    async def health(self) -> dict:
        return {"name": "Mock", "status": "available", "mode": "mock"}
