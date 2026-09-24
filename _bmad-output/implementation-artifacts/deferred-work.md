# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-cloudagent-stage-a.md`
  summary: 真实浏览器 HTTP SSE 断开后的端到端 UI 对账流程尚未运行验证。
  evidence: `test_http_sse_generator_disconnect_calls_cancel` 只直接关闭 ASGI 流生成器并验证后端取消；没有真实浏览器 `AbortController`、socket 断开与界面随后查询持久事件的联动证据。
- source_spec: `_bmad-output/implementation-artifacts/spec-cloudagent-stage-a.md`
  summary: 真实 PostgreSQL/API 重启后由启动流程识别并终结在途孤儿运行的集成场景尚未验证。
  evidence: `test_reconcile_marks_persisted_orphan_run_failed` 覆盖服务对账函数的运行状态与终态事件；没有保留 PostgreSQL 在途记录、强制重启 API 并观察启动对账完成的现场证据。
