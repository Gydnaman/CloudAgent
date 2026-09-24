# CloudAgent 阶段 A

本地合成客服 Agent 演示。仅使用 Mock LLM、Mock 知识源和只读 Mock 工具；演示身份不是真实认证。不要输入个人或敏感信息。消息与运行事件会保存在本地 PostgreSQL，直到全量重置。

## 启动

需要 Docker Compose plugin。首次构建会下载 PostgreSQL 18.6、Node 24、Python 3.12 和项目依赖；Mock 运行不访问外部模型或 tracing。`.env` 由 Compose 用于变量替换。

```powershell
Copy-Item .env.example .env
# 将 .env 中 DEMO_AUTH_ENABLED 改为 true，限 APP_ENV=local
docker compose up --build
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。API 只在宿主机 loopback 发布，数据库无宿主机端口。API 只支持一个容器、一个 worker。启动先等待数据库健康，再运行 Alembic、LangGraph checkpointer setup 和孤儿运行对账；全部成功后 ready 才返回 200。`GET /api/v1/health/live` 用于进程存活，`GET /api/v1/health/ready` 用于就绪。

## 演示路径

1. 选择“小林”并创建会话，发送“产品支持哪些部署版本？”；观察 Product 路由和 `product-compatibility` 引用。
2. 发送“查询我的账户用量”；观察 `tool.authorization=allow` 与只读工具结果。
3. 发送“查询其他账户用量”；观察 deny、skipped 和明确的“未执行”答复。
4. 发送“今天天气如何？”；观察 unsupported 澄清，没有知识检索或工具调用。
5. 发送“产品的 SLA 是多少？”；观察 `knowledge.empty` 和不编造资料的答复。
6. 点击停止或关闭会话，查看取消终态和运行详情。SSE 中断后，页面按 `X-Run-ID` 查询持久化状态和事件。

创建会话返回的 token 只保存在浏览器 `sessionStorage`，仅由 `X-Demo-Session-Token` 请求头发送。关闭后，同一未过期 token 只能重放关闭结果；其他 session/run API 会拒绝。token 自创建起 8 小时过期。

## 开发与契约

前端可单独运行 `cd frontend; pnpm install; pnpm dev`，Vite 将 `/api` 代理至 Compose API。后端 API 文档位于 `/docs`，OpenAPI 文件位于 `docs/api/openapi.json`。更新后端契约后运行 `uv run --project backend python -m app.openapi`，再在 `frontend/` 执行 `pnpm gen:types`，生成 `src/api/openapi.gen.ts`；客户端 DTO 位于 `frontend/src/api/types.ts`。SSE 为 POST fetch 流；每帧带 `id`、`event`、JSON `data`，持久化后才发送。重复 UUID 幂等键返回 409 和原 `run_id`，客户端据此补查，不重启图。

本地后端检查：`uv run --project backend pytest`、`uv run --project backend ruff check backend/app`。前端检查：在 `frontend/` 下运行 `pnpm test`、`pnpm lint`、`pnpm typecheck`、`pnpm build`。Compose 配置检查：`docker compose config --quiet`。

停止容器：`docker compose stop`。这会保留 PostgreSQL volume；下次 `docker compose up -d` 可继续使用已有演示数据。

## 重置本地演示数据

先停 API，再运行开发命令，最后重启 API：

```powershell
docker compose stop api
docker compose run --rm --no-deps api uv run --no-sync python -m app.cli reset-demo-data
docker compose up -d api
```

此命令删除全部本地会话、消息、运行、事件和 checkpoint。也可 `docker compose down --volumes` 删除该 Compose 项目 PostgreSQL volume 中的全部持久数据。token 丢失时使用全量重置。Stage A 不提供 SQLite 回退、真实模型接入、真实认证或写操作。
