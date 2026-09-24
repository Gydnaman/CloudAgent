from dataclasses import dataclass

from app.fixtures.data import DemoSubject


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


class AuthorizationPolicy:
    def check(self, subject: DemoSubject, action: str, resource: str) -> Decision:
        if action != "read_account_usage":
            return Decision(False, "tool_not_allowed")
        if resource != subject.account_id:
            return Decision(False, "resource_not_owned")
        return Decision(True, "owner")
