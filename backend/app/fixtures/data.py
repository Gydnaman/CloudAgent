from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSubject:
    id: str
    label: str
    role: str
    account_id: str
    tenant_id: str = "demo"


SUBJECTS = {
    "demo-alice": DemoSubject("demo-alice", "小林 · 产品用户", "customer", "acct-alice"),
    "demo-bob": DemoSubject("demo-bob", "小陈 · 产品用户", "customer", "acct-bob"),
}
USAGE = {
    "acct-alice": {"period": "2026-09", "units": 42, "unit": "demo-requests"},
    "acct-bob": {"period": "2026-09", "units": 17, "unit": "demo-requests"},
}
KNOWLEDGE = {
    "product-compatibility": {
        "title": "合成产品兼容说明",
        "body": "CloudAgent DEMO 支持本地 Docker Compose 部署演示；真实产品版本与兼容性尚未接入。",
    }
}
