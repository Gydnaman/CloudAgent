from dataclasses import dataclass
from typing import Protocol

from app.fixtures.data import KNOWLEDGE, DemoSubject


@dataclass(frozen=True)
class Evidence:
    source_id: str
    title: str
    summary: str


class KnowledgeProvider(Protocol):
    async def search(self, query: str, filters: dict, subject: DemoSubject) -> list[Evidence]: ...


class MockKnowledgeProvider:
    async def search(self, query: str, filters: dict, subject: DemoSubject) -> list[Evidence]:
        del filters, subject
        if any(term in query for term in ("部署", "版本", "兼容")):
            doc = KNOWLEDGE["product-compatibility"]
            return [Evidence("product-compatibility", doc["title"], doc["body"])]
        return []
