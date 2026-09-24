# CloudAgent 阶段 A 技术方案

> 状态：已通过（BMAD 三轮评审，2026-09-24）。本结论批准按本方案进入阶段 A；实现前仍须按 §12 执行版本复核、UX Gate 和验收。

> 评审焦点：技术栈与依赖兼容、Agent 上下文及检查点、会话/授权边界、POST + fetch SSE 协议、本地 PostgreSQL 前提和 UX Gate。关键选型或接口发生变化时，修订方案并重新评审。

## 1. 技术选型

| 层 | 阶段 A 方案 | 版本核对 |
| --- | --- | --- |
| Runtime | Python 3.12；uv；pyproject.toml + uv.lock | 实现开始当天再锁补丁版本 |
| API | FastAPI 0.141 系列；Pydantic v2；SSE 响应 | 0.141.1 是 2026-09-24 可见最新发布 |
| Agent Runtime | LangGraph 1.2 系列；StateGraph；AsyncPostgresSaver | 1.2.12 / checkpointer 3.1.2 是本次调研快照 |
| Database | PostgreSQL 18 稳定分支；本地 Docker Compose | 18.6 是本次调研快照 |
| Schema migrations | Alembic；迁移文件纳入版本控制 | 空库启动先执行 `alembic upgrade head` |
| Frontend | Vue 3.5；TypeScript；Vite；create-vue；Vue Router | Vue 3.5.43 是本次调研快照 |
| Node | Node.js 24 LTS | 2026-09-24 官方状态为 LTS |
| Test/quality tooling | 后端 pytest/ruff；前端 vue-tsc/eslint | 实施时按锁文件和 UX Gate 配置 |

这里确定的是技术方向和主版本候选；项目尚未安装这些依赖。依照调研，阶段实现前重新核验版本、兼容矩阵和安全公告，再建立锁文件。

取舍：LangGraph 与原方案指定的状态图和客服示例一致；Pydantic AI 是备选，但阶段 A 不并行维护两种编排模型。SSE 满足单向运行进度，不引入 WebSocket。阶段 A 固定使用 PostgreSQL；依照已知公告，锁文件必须将 `langgraph-checkpoint` 约束为 `>=4.1.1,<5`，同时使用修复版本的 checkpointer；若兼容解析或集成验证失败，先重新评审组合，不切换数据库或 saver。

## 2. 目标与非目标

### 目标

- 在没有真实 AI_API_KEY、知识库和业务 API 时，通过合成账户完整演示客服流程。
- 建立 LangGraph AgentRuntime、统一 RunEvent、LLM/Knowledge/Tool/Auth 接口、Mock 实现和权限策略。
- 提供 FastAPI API 与 SSE 事件流、PostgreSQL 运行记录与检查点，以及 Vue 3 工作台。
- 展示客户对话、Agent 路由、引用/工具结果、运行追踪、身份选择和 Provider 状态。
- 保持后续切换真实模型时前端和 AgentRuntime 的事件/Provider 契约不变。

### 非目标

真实 LLM/API 接入、真实客户或业务数据、写操作、支付/退款、多租户 SSO、生产认证、MCP、真实 RAG、Redis、Milvus、Neo4j、后台任务集群与云部署。

## 3. 总体架构

采用模块化单体，按依赖方向分层：

- Vue 工作台只访问 CloudAgent HTTP API。
- FastAPI 路由负责请求校验、错误映射、SSE 和 API 响应，不直接包含 Agent 或授权业务逻辑。
- AgentRuntime 调用 Provider、Knowledge、Tool、Auth 和 Persistence 的接口，不引用供应商 SDK。
- AuthorizationPolicy 和 AuthContextProvider 位于服务端；Provider/Tool adapter 不接受客户端提供的授权上下文。每次图调用使用独立、不可变的 LangGraph Runtime context，禁止共享会话主体变量。
- PostgreSQL 存储应用记录；LangGraph checkpoint 表由 AsyncPostgresSaver 管理。
- Mock Provider/Knowledge/Tool 是阶段 A 唯一实现，live 配置不在 UI 触发模型调用。

### 请求与状态流

1. 本地 Demo 用户选择合成演示角色并创建会话；服务端签发限时会话 token。该身份只模拟授权策略，不是真实身份认证，阶段 A 只处理合成业务数据。
2. 每次调用携带会话 token、UUID 格式 `Idempotency-Key` 和经 Unicode NFC 规范化、首尾空白裁剪后的 1 至 4,000 个码点消息。前端用 `Array.from(normalizedMessage).length` 提示长度，服务端按同一规则校验；请求体上限为 64 KiB，超限返回 413。同一会话至多运行一个图任务，不同 session/key 的并发运行返回 `409 run_in_progress`。幂等规则见 §6–7。
3. AgentRuntime 从已校验会话构造冻结的 run-scoped `DemoRunContext`，逐次传给 LangGraph；图节点通过 `Runtime.context` 读取主体，不用共享可变全局状态。图状态仅含客服流程数据。
4. Router 按 §5 的场景表分流 Product、Billing 或 unsupported；无匹配知识时说明缺少演示资料；只有明确请求 allowlist 工具时才校验授权并调用 Mock Tool。
5. 单一 per-run event writer 分配递增 sequence、持久化事件，再按 §5 的 SSE 契约发送。AgentRun 状态和唯一终态由应用数据库管理；每个 run 使用独立 checkpoint thread，以应用表中已完成轮次的消息构造对话上下文，不恢复中断中的运行。
6. 用户停止或客户端断开时服务端取消图任务。若 SSE 在终态前结束，前端按 `run_id` 查询状态与事件；若数据库不可用，停止执行并在存储恢复后对账。状态机和故障规则见 §§5–7、12。

## 4. 模块边界与建议目录

    backend/
      app/api/              # HTTP 路由、SSE、响应 schema
      app/core/             # 配置、错误、日志、密钥过滤
      app/auth/             # AuthContextProvider、Demo principal fixture
      app/policy/            # AuthorizationPolicy、Decision
      app/agent/             # LangGraph StateGraph、AgentRuntime、RunEvent
      app/providers/         # LLMProvider、MockLLMProvider
      app/knowledge/         # KnowledgeProvider、MockKnowledgeProvider
      app/tools/             # ToolProvider、MockToolProvider、参数 schema
      app/persistence/       # ORM、repositories、migrations、checkpoint
      app/fixtures/          # 合成用户、知识和只读工具数据
      pyproject.toml
    frontend/
      src/api/               # API client、fetch SSE parser、DTO
      src/components/        # Chat、Timeline、Evidence、ToolResult
      src/pages/             # Chat、Run detail、Provider status、Sources/tools
      src/stores/             # 页面级会话/运行状态
      src/router/
      package.json
    compose.yaml
    .env.example
    README.md

## 5. Provider、工具与事件契约

### LLMProvider

定义由业务拥有的类型，不暴露 LangChain/LangGraph 或供应商 SDK 类型：

- generate(request) → LLMResponse
- stream(request) → AsyncIterator[LLMChunk]
- health() → ProviderStatus

MockLLMProvider 用固定、可预测的合成应答按片段流式输出。响应来源标记为 mock；不将随机闲聊伪装为真实客服结论。错误统一为 provider_not_configured、provider_auth_failed、provider_rate_limited、provider_timeout、provider_unavailable、provider_invalid_response。

### Knowledge/Tool/Auth

- KnowledgeProvider.search(query, filters, auth_context) 返回 Evidence 列表；MockKnowledgeProvider 仅从合成文档检索。
- `DemoRunContext` 是 frozen dataclass，以 `StateGraph(context_schema=...)` 声明，并在每次 `ainvoke/astream(..., context=...)` 调用时传入；节点从 `Runtime.context` 读取本次调用的主体。context 不放进共享全局变量、图 state 或 checkpoint。
- `ToolProvider.invoke(tool_name, validated_args, auth_context)` 先匹配只读 allowlist，再由 `AuthorizationPolicy.check(subject, action, resource)` 决策，最后在 adapter 内复核资源归属。示例工具为 `read_account_usage(account_id: str)`，Pydantic 参数模型禁止额外字段；账号归属从本次调用的 DemoRunContext 校验。
- 策略拒绝时记录 `tool.authorization`（decision=deny）和 `tool.skipped`，返回明确的 `ToolDenied` 结果给 Agent；最终答复说明未执行，不得伪称工具成功或补造结果。
- MockIntentRouter 对照固定场景表确定 Product、Billing 或 unsupported 路由；不把用户消息当授权依据。空 Evidence 发 `knowledge.empty`，不执行依赖该 Evidence 的工具，也不编造具体业务结论。
- AuthContextProvider.resolve(demo_subject_id) 只在 APP_ENV=local 且 DEMO_AUTH_ENABLED=true 时读取 fixture；部署环境默认关闭。
- 模型生成内容、工具参数或用户消息不能修改 subject_id、role、tenant_id 或策略决策。

### Mock 路由场景契约

| 场景 | 输入/Fixture | 路由与数据操作 | 关键事件顺序与结果 |
| --- | --- | --- | --- |
| Product 命中 | “产品支持哪些部署版本？”；fixture 含兼容说明 | Product；检索 `product-compatibility`；不调用工具 | `run.started → route.selected → agent.started → knowledge.search.completed → llm.delta* → run.completed` |
| Billing 允许 | “查询我的账户用量”；绑定主体拥有 demo account | Billing；`read_account_usage(account_id)` 获准 | `run.started → route.selected → agent.started → tool.authorization(allow) → tool.completed → llm.delta* → run.completed` |
| Billing 拒绝 | “查询其他账户用量”；工具参数指向非所属 demo account | Billing；策略拒绝，不执行 adapter | `run.started → route.selected → agent.started → tool.authorization(deny) → tool.skipped → run.completed`；回复说明未执行 |
| 无匹配意图 | 不属于 Product/Billing 的演示问题 | unsupported；澄清，不检索、不调用工具 | `run.started → route.unsupported → llm.delta* → run.completed` |
| 无知识结果 | Product 查询但 fixture 不含匹配文档 | Product；无工具调用 | `run.started → route.selected → agent.started → knowledge.empty → llm.delta* → run.completed`；回复说明没有匹配的演示资料 |

### RunEvent

应用自有事件 envelope：

- event_id、run_id、sequence、created_at、type、payload
- 类型至少包含 run.started、route.selected、route.unsupported、agent.started、knowledge.search.completed、knowledge.empty、tool.authorization、tool.skipped、tool.completed、llm.delta、run.completed、run.failed、run.cancelled
- 工具事件只含名称、权限决定和脱敏摘要，不含密钥或完整 prompt
- 单一 per-run writer 接收 Agent、Provider 和工具事件，串行分配 sequence 并持久化，数据库确认后才向 SSE 发送。终态事件与 AgentRun 状态更新在一个事务中完成；状态仅能由 running 转为 completed、failed 或 cancelled，失败恢复时仍用 `status=failed` 并设置 `error_code=runtime_interrupted`。
- 任务启动与关闭取消共用 per-run gate，并按“锁定 session 行，再锁 per-run gate”的顺序操作。启动任务持 gate 重读 AgentRun 状态：仅当仍为 `running` 时创建图任务并保存 task handle；若关闭事务先提交为 `cancelled`，启动路径直接退出。关闭事务持 gate 将 `running` 条件更新为 `cancelled`、撤销 token 并写入唯一 `run.cancelled` 终态；提交后通知已登记的图任务取消。若图任务先取得 gate 并开始运行，关闭路径随后取消该 task；进入终态后 event writer 拒绝写入任何后续事件。关闭接口若关联活动 run，则响应返回最终生效的完整终态事件，供页面显示结果；若无关联 run，则不含终态事件。系统将 `close_run_id`（无关联运行时为 null）与 `Conversation.closed_at` 在同一事务记录，以便网络重试时回放关闭结果。
- 正常完成、失败、超时与取消都通过同一 per-run gate 和 event writer 提交终态；固定锁顺序为 session 行、per-run gate、event writer。若完成先于关闭取得 gate，关闭不得覆盖原终态，并在关闭响应中返回已存在的终态事件；若关闭先取得 gate，图任务不能在 cancelled 状态后启动或再提交其他终态。
- 在同一数据库事务中创建 AgentRun 和 sequence=1 的 `run.started` 事件；提交后才开始 200 响应，首帧必须是 `run.started`。API 在事务提交前将 run_id 预留到单进程 active-run 注册表，提交失败即释放；事务提交后启动图任务。响应头 `X-Run-ID` 供客户端在首帧丢失时查询状态，并通过 CORS 暴露。
- 每个 SSE 帧使用 LF 结束的 `id: <event_id>`、`event: <type>`、`data: <单行 JSON>`，空行分帧；payload 携带 `run_id` 和从 1 递增的 `sequence`。响应为 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`，不设置 Content-Length；每 15 秒发 SSE 注释心跳，终态事件后关闭流。
- POST 在 SSE 响应开始前的校验/权限错误以非 2xx JSON 返回；流开始后的失败以唯一 `run.failed` 终态事件返回。客户端不自动续传或重连；网络重试沿用同一 `Idempotency-Key`，避免重复执行。
- Vue 使用 `fetch` + `ReadableStream` 消费流。解析器用 `TextDecoder('utf-8')` 的 streaming 模式累计字节，按完整空行分帧，不假设浏览器 chunk 与 SSE 帧边界一致，并在流结束时 flush decoder。EOF 前若未收到终态，按 `X-Run-ID` 调用运行和事件查询；状态仍 running 时显示“结果待确认”并重试查询，不能伪报完成。
- 前端不依赖 LangGraph 的内部事件名称。AgentRuntime 负责将图节点和 Provider 输出转换为上面的稳定类型。

## 6. API 初始契约

| Endpoint | 目的 |
| --- | --- |
| GET /api/v1/health/live | 进程存活 |
| GET /api/v1/health/ready | PostgreSQL 和运行时准备状态 |
| GET /api/v1/demo/subjects | 返回本地合成身份；非本地环境关闭 |
| POST /api/v1/sessions | 创建会话并返回本地演示角色绑定及 `demo_session_token`；该角色是模拟输入，不是已认证用户 |
| GET /api/v1/sessions/{session_id} | 通过 `X-Demo-Session-Token` 查询会话消息历史 |
| POST /api/v1/sessions/{session_id}/close | 验证 token 后撤销会话；若有活动 run，同一事务仅在其状态仍为 `running` 时将其终结为 `cancelled`；若其已终结则保留原终态，并记录 `close_run_id`。若关联活动 run 则返回最终生效的完整终态事件（否则不含终态事件）；同一未过期 token 可在关闭后仅用于回放本次关闭结果，其他接口均拒绝已关闭会话；不删除记录 |
| POST /api/v1/sessions/{session_id}/runs/stream | 以 token 校验会话，校验消息和 `Idempotency-Key` 请求头，执行图并返回 SSE RunEvent |
| GET /api/v1/runs/{run_id} | 以 token 校验关联会话后查看运行状态、时间与脱敏摘要 |
| GET /api/v1/runs/{run_id}/events | 以 token 校验关联会话后查询持久化事件时间线 |
| GET /api/v1/providers/status | 返回已装配的 Mock 状态；明确标记 Live 尚未接入，不返回密钥 |
| GET /api/v1/catalog | 返回 Mock 工具和知识源的名称、类型与状态 |

浏览器在 `sessionStorage` 中按会话保存 demo token；token 仅通过 `X-Demo-Session-Token` 请求头发送，不进入 URL、SSE payload 或日志。token 从创建时起 8 小时后过期；会话关闭接口可立即吊销它。若 token 丢失，README 提供 `uv run python -m app.cli reset-demo-data`，清除本地会话、消息、运行、事件与全部 checkpoint；该命令仅用于开发数据并会清空所有本地演示记录。所有 run 详情和事件查询都须由 run 反查所属 session，并验证 token 与该 session 匹配。同一 `Idempotency-Key` 重复请求时，若 SHA-256(Unicode NFC 规范化并首尾裁剪后的消息 UTF-8 字节) 相同，返回 409 `duplicate_request` 与既有 `run_id`；前端据此查询原运行，不重开 SSE 或执行图。hash 不同则返回 409 `idempotency_conflict` 和既有 `run_id`，不执行图。服务端先限制请求体最多 64 KiB，再解析 JSON；消息长度按 NFC 规范化、首尾裁剪后的 Unicode 码点计算，范围为 1–4,000。阶段 A 默认 `AI_PROVIDER=mock`，不实现 live adapter，也不需要 `AI_API_KEY`；状态页显示 Live「未接入」，不得将 Live 标示为可用，也不得将静默回退标示为成功。真实 provider 留到阶段 B。

## 7. 数据与状态所有权

应用表：

- Conversation：会话 ID、合成主体 ID、创建/更新时间、`closed_at` 及 nullable `close_run_id`（本次关闭响应关联的 run；用于稳定回放其唯一终态事件）。
- 创建会话时由服务端用密码学安全随机源生成至少 32 字节的不透明 token；仅保存其 SHA-256 摘要及 `token_expires_at`，不保存原始 token。所有受保护请求都在锁定会话行后重新校验 token 摘要和过期时间，并以常量时间比较摘要；`closed_at` 会拒绝除关闭结果回放外的全部请求。会话关闭后，只有相同且未过期的 token 可再次调用 close：服务端不再执行关闭副作用，而是依据持久化的 `close_run_id` 回放相同终态事件；不带关联运行时回放空终态结果。应用日志过滤 `X-Demo-Session-Token` 和 `Idempotency-Key`。
- Message：用于刷新后恢复聊天页的用户消息和最终回答，并标明 mock 来源。阶段 A 的本地数据库可能保存用户输入，因此请勿输入个人或敏感信息。
- AgentRun：状态、意图、Agent 路径、开始/结束时间、错误码、`request_hash`；对 `(session_id, idempotency_key)` 建唯一约束，并用 `(session_id)` 的 `status='running'` partial unique index 防止同会话并发运行。数据保留上限为 100 个会话和 1,000 条运行记录，达到上限时 API 返回 `409 demo_capacity_reached`，README 指引运行全量重置命令。
- RunEvent：`run_id` 外键引用 AgentRun，按 `(run_id, sequence)` 唯一排序，用于时间线和审计；幂等唯一约束只建在 AgentRun 上。
- Evidence/ToolResult 可作为事件 payload 的脱敏摘要；系统 prompt、Authorization header、API key 和 AuthContext 不进入图状态、事件、应用日志或数据库。

开始运行时先按 `session_id` 锁定会话行，并在锁内重新校验 token 摘要、过期时间和 `closed_at`；再检查相同 Idempotency-Key：已有 run 按 request_hash 返回 `duplicate_request` 或 `idempotency_conflict`，均附原 `run_id`；否则检查该 session 的活动 run，存在时返回 `run_in_progress` 和活动 `run_id`；两项均通过才插入 AgentRun 与 `run.started`。唯一约束和 partial unique index 是并发下的数据库兜底；如仍遇约束冲突，回滚后重新读取记录并映射为上述 409，不向客户端泄漏数据库错误。进程内注册表在数据库提交前预留运行 ID，失败时释放；进程启动时先完成迁移、checkpointer setup 和既有孤儿运行对账，再将 ready 置为 true，避免把刚提交但尚未启动的运行判成孤儿。

每个 AgentRun 使用自己的 `thread_id=run_id`；应用表仅向新运行提供已完成轮次的对话消息，避免取消或进程中断留下的部分 checkpoint 污染后续轮次。checkpointer 保存该次运行必要的合成流程状态，不保存授权上下文、会话 token、密钥或系统 prompt；中断运行不恢复。对账时，以应用事件和运行表为准。单实例 API 维护 active-run 注册表，全局最多 4 个活动运行；超出返回 `429 global_run_limit`。每个图任务最长运行 120 秒；超时取消图并终结为 `status=failed`、`error_code=run_timeout`，之后可重新提交。事件持久化失败时以 100/300/900 ms 间隔最多重试 3 次，然后取消图并关闭流，不发送未持久化的事件。数据库恢复后，运行查询若发现状态仍为 running 且 run 不在注册表中，就以 `status=failed`、`error_code=runtime_interrupted` 原子补写终态；启动时也执行同样的孤儿运行对账。SQLAlchemy 使用自己的异步连接池；AsyncPostgresSaver 在 FastAPI lifespan 内管理独立的 psycopg AsyncConnectionPool，并在启动时执行 saver setup、关闭时释放连接。本地数据库不设自动过期；停止 API 后运行 README 的 `uv run python -m app.cli reset-demo-data`，清除所有应用记录和 checkpoint。Compose volume 重置也会删除该项目全部持久数据。

## 8. UI 范围与体验门禁

- 客服工作台：合成用户切换、消息输入、mock 标记、引用和工具摘要、停止/重试、关闭当前会话；关闭有活动运行的会话时显示已取消终态；提示用户演示输入只保存在本地数据库直至全量重置，不输入个人或敏感信息。
- Agent 时间线：路由、Agent、知识检索、工具授权和最终回复状态。
- 运行详情：事件、耗时、错误、权限拒绝和脱敏调用摘要。
- Provider 状态：显示 Mock 可用和 Live「尚未接入」；不回显密钥。
- 工具/知识源页：只展示 adapter 类型、fixture 状态和后续接入说明。

开始新页面前执行用户原方案指定的 UI/UX Pro Max skill：确认产品定位为 SaaS 工作台；使用该 Skill 为 Vue 项目检索设计系统，并将结果保存为 CloudAgent Master；阅读 UX/Vue 规则并梳理页面交互状态。UX 结果与本方案、API event DTO 一起进入 Story。只有前端设计通过该 Gate 后，才开始页面编码。

浏览器存储中的会话 token 可被同源注入脚本读取，因此阶段 A 只处理合成数据；页面和 Vite 开发服务配置内容安全策略，禁止第三方脚本，使用 `default-src 'self'`、`script-src 'self'`、`object-src 'none'`、`base-uri 'none'`，并将 `connect-src` 限定为本地 API 与前端开发源。

## 9. 身份、权限、密钥和错误边界

- Stage A 演示身份只用于本机合成数据，不表示真实身份认证；token 有效期为 8 小时，过期后须创建新会话。
- 只有服务端能从已校验的 demo session token 和会话记录创建 AuthContext；演示主体由用户在创建会话时选择，但后续请求不能改写它。AgentState/LLM prompt 不包含该上下文。
- 每一次工具执行均先做 allowlist、schema 验证和 AuthorizationPolicy 检查，拒绝结果可观察但不泄露资源。
- AI_API_KEY 从后端环境读取；不得写入仓库、前端构建变量、SSE、Provider 状态或日志。
- 统一异常映射为用户可操作消息与稳定错误码；日志保留 run_id 和错误类别，不记完整敏感输入。
- 对含提示注入的合成消息执行同一策略路径；权限结果必须由确定性的服务端策略决定。

## 10. 本地运行和依赖

- 本地基线用 compose 启动 PostgreSQL 与 API；Vue 在开发时可通过 Node 24 的 dev server 启动，构建版由 API 静态托管或同 compose 提供。
- .env.example 默认 AI_PROVIDER=mock；不包含真实凭据。
- 依赖安装和 PostgreSQL 镜像首次拉取需要网络；镜像使用固定的 `postgres:18.6` tag。下载完成后，Mock 验收运行不访问外部模型或 tracing 服务。
- 不引入 Redis、Milvus、Neo4j、MCP Server、外部队列或托管观测服务。
- 阶段 A 验收基线要求目标机器可运行 Docker Compose。Compose 将 API 端口绑定到 `127.0.0.1`，PostgreSQL 不发布宿主机端口；直接运行 API 时只监听 loopback。`APP_ENV=local` 下 `DEMO_AUTH_ENABLED` 默认关闭，README 仅在本地明确启用；非 local 环境启用 Demo 身份时启动失败。若目标环境不能运行 Docker，停止依赖实施并先修订本方案的数据库基线；不把 SQLite saver 配置成 PostgreSQL 的回退。
- PostgreSQL 服务配置 `pg_isready` healthcheck；API 容器 `depends_on` 等待数据库健康，并对数据库连接做最多 30 秒的有界重试。API 入口先执行版本化 Alembic migration，再执行 checkpointer setup 和孤儿运行对账；这些步骤全部成功后才报告 ready，迁移或 setup 失败时进程以非零状态退出。
- 阶段 A 仅支持一个 API 容器、一个 Uvicorn worker；禁止 Compose scale 或多副本。孤儿运行判断依赖该单进程的 active-run 注册表，不支持多 worker/多副本部署。
- 设置 `MAX_ACTIVE_RUNS=4`、`MAX_SESSIONS=100`、`MAX_RUNS=1000`；单进程用容量锁串行完成配额检查和会话/运行名额预留，写入失败即释放；达到活动运行上限返回 `429 global_run_limit`，达到持久数据上限返回 `409 demo_capacity_reached`，由 README 引导重置本地数据。
- CORS 仅允许本地 Vue dev origin、`GET/POST/OPTIONS` 方法和明列的 `Content-Type`、`X-Demo-Session-Token`、`Idempotency-Key` 请求头；允许暴露 `X-Run-ID`。若加入反向代理，必须关闭 SSE buffering 并转发 `X-Accel-Buffering: no`。
- 提供明确的本地数据清理命令；删除 Compose volume 是可选的全量重置，文档说明会移除该 Compose 项目的持久数据。

## 11. 任务拆分

1. 安装官方 BMad stable + BMM 并检查工具支持；生成 Product Brief、PRD 和初始架构基线。
2. 执行 UI/UX Pro Max 设计系统 Gate，确定 Vue 页面 tokens 和 UX 状态。
3. 将 Gate 输出纳入 BMad UX 文档与 Story，冻结 API/Event DTO 和页面状态。
4. 初始化 Python/Vue 项目，记录依赖版本、锁文件、Alembic migration、compose 和 .env.example。
5. 实现 Pydantic 请求/响应和 RunEvent schema、应用错误类型、配置与日志脱敏。
6. 实现 Demo AuthContext、AuthorizationPolicy、合成 fixtures 和只读 mock tool。
7. 实现 Provider/Knowledge interfaces 与 Mock adapters。
8. 实现 LangGraph 固定状态图、独立 Runtime context、串行事件 writer 与异步 PostgreSQL checkpoint。
9. 实现 FastAPI session/run/provider/catalog API、session close/reset 与 SSE 协议。
10. 实现 Vue chat、timeline、run detail、provider status 和 catalog 页面。
11. 增加自动验证任务：覆盖主体/token 绑定与过期、资源 ID 不匹配、Unicode 长度、路由场景、空检索、工具拒绝、重复 key 的相同/不同 payload（含并发提交）、同会话并发、活动 run 时关闭会话、关闭响应丢失后的同 token 结果回放、完成/关闭竞态终态保持、CORS preflight、SSE 分片/提前 EOF/单一终态、数据库故障对账和敏感字段不落日志/检查点。
12. 补充 `reset-demo-data` 命令、README、架构图、演示脚本与 .env 操作说明。

## 12. 验收与验证方式

总体完成条件是：无 key 的 Mock 流程可完整演示，意图、Agent、知识、工具、授权和错误都可见，无效及越权访问被后端拒绝，密钥和会话 token 不泄露，且加载、无数据、权限拒绝、取消和错误状态都有合理呈现。实现后按原方案逐项走查：

- 无 AI_API_KEY 启动并完成 Product/Billing 两条合成会话；每一条显示 Mock。
- 从空 Compose volume 启动时，PostgreSQL healthcheck、Alembic migration、checkpointer setup 和 ready 顺序可重复；迁移失败时 API 不报告 ready。
- 锁定依赖满足 `langgraph-checkpoint >=4.1.1,<5`，并确认实际锁文件中没有 GHSA-47pj-3jcm-6whg、GHSA-fjqc-hq36-qh5p 和 GHSA-g48c-2wqr-h844 标注的受影响版本。
- Provider 状态准确显示 Mock 可用、Live 尚未接入；不得将 Live 标示为可用，也不得将静默回退标示为成功。
- 同一运行的事件关联相同 `run_id`，按 `sequence` 排序后可查询；每次运行仅有一个终态。
- 未知工具、错误 schema、资源归属不匹配和策略拒绝均不执行工具。
- unsupported 意图与空知识结果走安全分支；空白/超限消息在创建运行前拒绝；同一 Idempotency-Key 不会执行两次。
- SSE 解析器须通过任意字节切分测试，覆盖 UTF-8 多字节字符和帧边界；客户端取消或服务异常后，不得留下状态仍为 `running` 且原因不明的记录。
- 会话、运行和事件查询均验证 `X-Demo-Session-Token` 与绑定资源；AuthContext、demo token、key、Authorization header 不进入 graph checkpoint、响应、事件或日志；数据库仅保存 token 摘要。
- 同一 Idempotency-Key 的并发提交按 request_hash 返回稳定的 409 和原 run_id；结束运行、关闭活动会话及超时取消均只产生一个终态。另强制关闭事务提交发生在图任务首次调度前的时序，确认关闭后的图不会启动。关闭成功后模拟丢弃 HTTP 响应，再以同一未过期 token 重试 close，必须返回相同 `close_run_id` 和终态事件；该 token 访问其他已关闭会话接口仍须被拒绝。超时后会话可再次提交。
- 多会话并发不超过活动运行上限；会话/运行存储达到上限返回稳定错误码。API 仅使用单实例、单 worker 运行配置。
- 检查生产构建和 Vite 开发响应中的 CSP：不加载第三方脚本，连接仅限本地前端与 API。
- 用户消息中的提示注入不能改变策略结果或主体身份。
- 搜索代码仓库并检查前端响应、构建变量和日志，确认其中均不含 AI_API_KEY 或 Authorization 内容。
- 核对主聊天、权限拒绝、Mock 标识、未配置 provider、加载、停止、重试和服务错误的 UX 状态。
- 至少复查客户端断开 SSE 连接时后端的处理，以及 PostgreSQL 重启后 checkpoint 的行为。

## 13. 主要风险与回退

| 风险 | 处理/回退 |
| --- | --- |
| LangGraph 与 checkpointer 兼容性变化 | 实施前锁定并做最小 PostgreSQL 集成验证；失败时暂停并重新评审组合（见 §1）。 |
| SSE 断开后无法续传 | 阶段 A 终结为 cancelled，保留事件供查询；续传需求另行设计（见 §5）。 |
| 目标机器不能运行 Docker Compose | 先修订 PostgreSQL 本地基线，再开始依赖实施（见 §10）。 |
| 设计系统与页面需求冲突 | UX Gate 通过并冻结 DTO 后再编码（见 §8、§11）。 |
| 后续接真实 API 时发生密钥或主体泄漏 | 服务端装配 Provider 和主体，并执行密钥检查与越权验收（见 §§9、12）。 |

## 14. 方案评审记录

2026-09-24 完成三轮 BMAD 文档评审，结论为**通过**。三轮均覆盖对抗性、边界、结构和措辞视角；发现项已修订关闭，或作为不影响方案正确性的编辑建议记录理由后不采纳。结案复核未发现未解决的阻断或实质问题。

| 轮次 | 对抗性 | 边界 | 结构 | 措辞 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 第一轮 | 14 | 6 | 3 | 9 | 32 项均关闭 |
| 第二轮 | 14 | 6 | 6 | 8 | 34 项已处置；1 项编辑建议未采纳并说明理由 |
| 第三轮 | 14 | 2 | 1 | 6 | 23 项已处置；1 项编辑建议未采纳并说明理由 |

结案复核另发现并关闭了 4 处并发与接口一致性问题：关闭/任务启动竞态；关闭与已有终态的 API 描述不一致；关闭结果与已撤销 token 的响应丢失重试；无关联运行时的空回放语义。现在 `close_run_id` 与 `Conversation.closed_at` 同事务持久化；同一未过期 token 只可重放 close 结果，其他已关闭会话接口仍拒绝访问。验收条目覆盖这些时序与重试情形。

结构评审提出将调研报告中的 GitHub 项目比较表移到框架分析之后。该编辑建议未采纳：本调研首先响应用户要求的 GitHub 项目检索，现有执行摘要已先给出技术判断，比较表先列证据符合调研阅读目的；不构成未解决问题。

[查看三轮方案评审记录](../reviews/phase-a-bmad-review.md)。阶段 A 实现与验收结果见[实现摘要](../specifications/stage-a.md)和[实现评审记录](../reviews/implementation-review.md)；尚未执行的端到端验证列在[已知验证限制](../known-limitations.md)。技术选型或接口发生变化时须修订方案并重新评审。
