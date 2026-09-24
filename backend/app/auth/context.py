from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import ApiError
from app.fixtures.data import SUBJECTS, DemoSubject


@dataclass(frozen=True)
class DemoRunContext:
    subject: DemoSubject
    emit: object
    question: str = ""
    history: tuple[str, ...] = ()


class AuthContextProvider:
    def resolve(self, subject_id: str) -> DemoSubject:
        if settings.app_env != "local" or not settings.demo_auth_enabled:
            raise ApiError(404, "demo_disabled", "本地演示身份未启用")
        subject = SUBJECTS.get(subject_id)
        if subject is None:
            raise ApiError(404, "subject_not_found", "演示身份不存在")
        return subject
