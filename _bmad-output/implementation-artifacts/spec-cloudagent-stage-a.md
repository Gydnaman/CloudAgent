---
title: 'CloudAgent 阶段 A 本地 Mock 客服演示'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 3
baseline_commit: 'NO_VCS'
context:
  - 'docs/technical-proposals/phase-a.md'
---

<frozen-after-approval reason="human-approved technical proposal and implementation authorization">

## Intent

**Problem:** CloudAgent 目前缺少可本地运行的客服 Agent 演示，无法展示意图路由、知识依据、只读工具授权和可追踪运行过程。

**Approach:** 建立 FastAPI、LangGraph、PostgreSQL 与 Vue 模块化单体；以合成身份、固定客服图和 Mock adapters 完成 Product/Billing/unsupported 流程，并用应用自有 RunEvent/SSE 契约呈现运行。

## Boundaries & Constraints

**Always:** 采用已通过方案的版本候选、模块边界、API 事件契约与验收；阶段 A 只运行 Mock；身份与授权上下文由服务端从会话 token 生成；只读工具执行前校验 allowlist、参数和资源归属；token 只存摘要；运行事件先持久化再发流；每个运行仅一个终态；本地 Compose loopback 绑定、单 API worker。

**Never:** 连接真实 LLM、业务 API、客户数据或外部 tracing；提供生产认证、多租户或工具写操作；把授权上下文、token、密钥或完整 prompt 写入图状态、checkpoint、事件或日志；用 SQLite 作为 PostgreSQL/checkpointer 的静默回退。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Product knowledge hit | 已授权 session + 命中合成知识的问题 | 返回带 fixture 来源的 Mock 答案和有序运行事件 | 空证据时 abstain，不伪造引用 |
| Billing tool allow/deny | 查询本人/他人合成账户用量 | 本人执行只读 Mock tool；他人收到拒绝结果且 adapter 不执行 | 写入 deny 与 skipped 事件 |
| unsupported intent | 不属于演示场景的问题 | 请求澄清，不检索、不调用工具 | 返回可理解的 Mock 答复 |
| idempotent retry | 同 key 同/不同规范化消息 | 稳定返回原 run 或 409 与既有 run_id，不重复执行 | 数据库约束冲突回滚后重读映射 |
| close/run race | 运行启动、完成与关闭并发 | per-run gate 决定唯一终态；关闭结果可用同 token 重放 | 关闭后其他 session API 拒绝 |
| SSE interruption | 任意 UTF-8 分片、提前 EOF | 按 cursor 查询持久事件/状态；不假报完成 | 未终态显示待确认并重试查询 |

</frozen-after-approval>

## Code Map

- `docs/technical-proposals/phase-a.md` -- 已通过的实现基线、接口、约束和验收；本 spec 的详细决策来源。
- `backend/`、`frontend/`、`compose.yaml` -- 当前均不存在，从零建立独立 CloudAgent 实现；不要改动其他任务中的 RAG 工作台。
- `_bmad/` -- 本项目独立副本，只保存本项目 BMAD 配置与生成物。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/` -- 建立领域类型、授权、Mock provider、LangGraph 运行时、持久化和 API，保持依赖方向与方案一致。
- [x] `backend/alembic/`、`backend/pyproject.toml` -- 版本化 schema、锁定依赖并约束 `langgraph-checkpoint >=4.1.1,<5`。
- [x] `frontend/`、`docs/DESIGN.md`、`docs/EXPERIENCE.md` -- 先过 UX Gate，再实现 Vue 工作台、fetch SSE parser 和运行页面。
- [x] `compose.yaml`、`.env.example`、`README.md`、`docs/api/openapi.json` -- 提供本地部署、OpenAPI 类型生成、运行和重置说明。

**Acceptance Criteria:**
- Given 空 PostgreSQL volume, when 启动 Compose, then 健康检查、Alembic、checkpointer setup 后 API 才 ready，Web/API 仅监听 loopback。
- Given 本地合成用户, when 创建、查询或关闭 session, then token 仅存摘要且 8 小时过期；关闭后的同 token 只可重放 close，其他 API 拒绝。
- Given Product/Billing/unsupported 输入, when Agent 执行, then 路由、知识、授权、工具与答案事件符合场景表；拒绝时工具没有副作用，空证据不编造。
- Given 重复 key、并发 run、close/完成竞争或服务中断, when 请求重试/对账, then hash 冲突映射稳定，状态仅有一个终态，孤儿 run 被标记失败。
- Given SSE 字节任意切分或终态前断流, when Vue 解析/查询, then UTF-8 完整，按 run_id 补查事件，不伪报完成。
- Given 任意界面结果, when 用户浏览, then 显示 DEMO/MOCK、拒绝态、空态和错误态，不含密钥、token 或真实数据。

</frozen-after-approval>

## Implementation Notes

### 项目边界

- CloudAgent 独立位于 `outputs/cloudagent/`，拥有自己的前后端、Compose 项目、PostgreSQL volume、BMAD 输出、UX 文档和 OpenAPI 契约。
- 既有企业 RAG 工作台未读取、修改或复用；本阶段不接入 RAG。
- 实现只启用 Mock LLM、Mock 知识源和只读 Mock 工具；Compose 只绑定 loopback，API 单 worker。

### 实现概要

- 后端使用 FastAPI、LangGraph、SQLAlchemy/Alembic、PostgreSQL 与 AsyncPostgresSaver；运行事件先持久化后通过 POST + SSE 发送。
- 前端为 Vue 3、TypeScript、Vite 工作台；请求幂等键保存在浏览器 sessionStorage，重试沿用同一 key。
- OpenAPI 现在包含手工限长解析的请求体、运行时必需的自定义请求头和 ApiErrorDTO；前端类型已重新生成。
- 前端质量门包含 ESLint、全量 Node 测试、vue-tsc 和生产构建。

## Spec Change Log

- 2026-09-24：实现阶段 A；不改动 `<frozen-after-approval>` 中的任何内容。
- 2026-09-24：按代码复核修正 OpenAPI 请求体/必需 header/错误 schema、Docker 构建上下文 `.env` 排除和 Compose env 插值；补齐前端测试与 ESLint 质量门。

## Review Triage Log

- P1 幂等重试可能使用新 key 重复启动：已修复，sessionStorage 对同一 session/message 重用 key；加入重试状态测试。
- P2 账单/账户类问题误路由用量工具：已修复，只有明确的“查询/查看/多少 + 用量”请求才路由；增加反例测试。
- P2 close 与 run 注册并发：已修复，关闭会话在 session row 锁内检查活动运行；加入竞态回归测试。
- P2 手工解析的请求体和必需 header 未进入 OpenAPI，错误响应未描述：已修复，生成契约与 TypeScript 类型已更新，测试校验 body/header/error schema。
- P2 `.env` 会进入 Docker build context：已修复，`.dockerignore` 排除本地 `.env*` 并保留 `.env.example`。
- P2 可选 `env_file.required` 要求较新的 Compose：已改为 Compose `.env` 变量插值及明确默认值，不再使用该选项。
- P3 前端测试未纳入常规命令、缺少 ESLint：已增加 `pnpm test` 和 `pnpm lint`。
- P2 AgentState 把用户问题和对话历史写进 LangGraph checkpoint：已修复，只将必要的 `intent/answer/source_ids` 留在图状态，问题与历史通过运行上下文传入；新增 checkpoint 内容测试。
- P2 关闭会话时旧 SSE/对账回调可能污染切换后的身份：已修复，异步会话工作期间禁止身份切换；`canSend` 还会检查 `sessionWork` 与 `closePending`，关闭等待不会提前解锁发送。
- P2 HTTP SSE generator 断连处理和孤儿运行对账缺少直接覆盖：已新增路由 generator 断连取消测试和 persisted orphan reconciliation 测试。
- 复核中将“GET closed session 可读”判定为误报；实现遵循关闭后仅允许重放 close。多 worker 不支持已在方案和 README 中明确限制为单 worker。
- 三轮 BMAD 实现评审均已通过：未发现未解决的实现阻塞；两项真实浏览器/真实 PostgreSQL 重启集成验证仍待执行，已记录在 `docs/reviews/implementation-review.md` 与 `_bmad-output/implementation-artifacts/deferred-work.md`。

## Verification

**Commands:**
- `backend/.venv/Scripts/python.exe -m pytest tests` (from `backend/`) -- 21 passed.
- `backend/.venv/Scripts/ruff.exe check app tests` (from `backend/`) -- passed.
- `pnpm run test` -- 4 passed; includes retry/session-state and SSE parser tests.
- `pnpm run lint` -- passed.
- `pnpm run typecheck` -- passed.
- `pnpm run build` -- passed; production bundle generated.
- `backend/.venv/Scripts/python.exe -m app.openapi` and `pnpm run gen:types` -- passed; contract and generated TS types synchronized.
- `docker compose config --quiet` -- passed with loopback-only port publication.

**Manual checks:**
- Fresh Compose run was verified before final contract/docs-only changes: ready checks after migration/checkpointer setup; Product hit, Billing allow/deny, unsupported, empty knowledge; durable ordered SSE and one terminal event; duplicate/conflicting idempotency; close replay and closed-session denial; provider status. Database check confirmed checkpoint rows and token digests, and no active runs or duplicate terminal events.
- Added unit coverage for forced service cancellation, close/run race, request-length boundaries and OpenAPI contract.
- Added unit coverage for LangGraph checkpoint privacy, HTTP SSE generator disconnect cancellation and persisted orphan-run reconciliation.
- Not exercised in the final run: a real browser HTTP disconnect followed by UI reconciliation, and a forced API/PostgreSQL restart with an in-flight orphan run. Reconciliation code and unit paths exist; these remain live integration validation gaps.
- Compose services were stopped after integration; PostgreSQL volume was preserved. The reset command was not run.

## Review Findings

- **结论：通过。** 依照 BMAD 完成三轮实现评审；每轮覆盖盲审、边界场景和验证缺口。最终复核未发现未解决的实现阻塞。
- 第一轮与第二轮关闭了幂等重试、用量意图路由、close/run 竞态、OpenAPI 契约、构建上下文和 Compose 兼容性等问题；修复及回归证据见上方 Review Triage Log。
- 后续边界复核发现 checkpoint 隐私与会话关闭/SSE 身份竞态，均已修复并增加测试；最终复核确认关闭请求期间发送按钮保持禁用，身份切换等待所有会话异步工作结束。
- HTTP 流生成器取消与 persisted orphan reconciliation 已有单元测试覆盖。真实浏览器断开后的端到端 UI 对账，以及真实 API/PostgreSQL 中断后启动对账未验证；作为验证范围 deferred，详见 `deferred-work.md`。
- 完整评审记录：`docs/reviews/implementation-review.md`。
