from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from app.fixtures.data import USAGE, DemoSubject
from app.policy.authorization import AuthorizationPolicy


class ReadUsageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str


class ToolProvider(Protocol):
    async def invoke(self, tool_name: str, args: dict, subject: DemoSubject) -> dict: ...


class MockToolProvider:
    def __init__(self) -> None:
        self.policy = AuthorizationPolicy()

    async def read_usage(self, account_id: str) -> dict:
        return USAGE[account_id]

    async def invoke(self, tool_name: str, args: dict, subject: DemoSubject) -> dict:
        if tool_name != "read_account_usage":
            return {"allowed": False, "reason": "tool_not_allowed"}
        try:
            validated = ReadUsageArgs.model_validate(args)
        except ValidationError:
            return {"allowed": False, "reason": "invalid_args"}
        decision = self.policy.check(subject, tool_name, validated.account_id)
        if not decision.allowed:
            return {"allowed": False, "reason": decision.reason}
        # The adapter repeats the ownership check even after policy approval.
        if validated.account_id != subject.account_id:
            return {"allowed": False, "reason": "resource_not_owned"}
        return {"allowed": True, "summary": await self.read_usage(validated.account_id)}
