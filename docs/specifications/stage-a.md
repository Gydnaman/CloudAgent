# CloudAgent 阶段 A：实现与验收摘要

## 目标与范围

提供一个可在本机运行的合成客服 Agent 演示，展示意图路由、知识依据、只读工具授权和运行事件时间线。

阶段 A 仅使用 Mock 模型、固定知识 fixture 和只读 Mock 工具。身份和业务数据均为合成数据；不连接真实模型、外部业务 API、真实客户知识库或生产认证，不执行写操作。

## 技术组成

- 后端：FastAPI、LangGraph、SQLAlchemy/Alembic、PostgreSQL 与 AsyncPostgresSaver。
- 前端：Vue 3、TypeScript 与 Vite。
- 本地部署：Docker Compose；API 端口仅绑定 loopback，使用单 API 容器和单 worker。

## 已交付行为

- 合成会话 token 仅以摘要持久化，8 小时过期；关闭后只允许重放关闭结果。
- 运行按幂等键去重，事件先持久化再通过 SSE 发送；提供停止、结果对账和孤儿运行处理。
- Product 问题返回固定知识 fixture；Billing 用量只允许查询当前合成用户，越权请求会被拒绝且不执行工具；不支持的问题进入澄清流程。
- 前端展示 DEMO/MOCK 标记、依据、工具授权结果和运行事件。

## 验收结果

- 后端测试：21 项通过；Ruff 检查通过。
- 前端测试：4 项通过；ESLint、TypeScript 检查和生产构建通过。
- OpenAPI 导出与 TypeScript 类型同步通过；`docker compose config --quiet` 通过。
- Compose/PostgreSQL 手动集成检查覆盖合成 Product/Billing/unsupported 流程、持久事件、幂等和会话关闭重放。
- BMAD 三轮实现评审通过，未发现未解决的实现阻塞；完整发现与修复记录见[实现评审记录](../reviews/implementation-review.md)。

## 尚未完成的验证

真实浏览器断开 SSE 后的 UI 对账，以及真实 API/PostgreSQL 重启后的孤儿运行对账尚未端到端执行。现有单元测试覆盖了相关核心逻辑，详情见[已知验证限制](../known-limitations.md)。
