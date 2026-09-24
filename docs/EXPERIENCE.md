---
title: CloudAgent 阶段 A 体验契约
status: final
updated: 2026-09-24
sources:
  - docs/technical-proposals/phase-a.md
  - _bmad-output/implementation-artifacts/spec-cloudagent-stage-a.md
---

## Foundation

浏览器内本地 SaaS 工作台，视觉契约见 [DESIGN.md](DESIGN.md)。仅合成身份和 Mock adapter。会话 token 暂存 `sessionStorage`，不在界面、URL 或事件中显示。

## Information Architecture

四个页面：客服聊天、运行详情、Provider 状态、知识源与工具。聊天页提供身份选择、消息历史、输入、引用/工具摘要与时间线；运行详情提供持久事件、耗时和错误；其他页说明 Mock/Live 状态和 fixture 范围。

## Voice and Tone

文字直接说明运行状态。固定标签为“DEMO / MOCK”“未执行”“结果待确认”“Live 尚未接入”。输入区说明本地持久化及不要输入个人或敏感信息。

## Component Patterns

输入按 NFC 规范化并裁剪空白后计数，使用 `Array.from(message).length`。空白、超过 4,000 码点、运行中和关闭的会话禁用发送。事件按 sequence 排序。工具卡显示名称、allow/deny 和脱敏摘要；拒绝时显示未执行。引用卡仅显示 fixture 来源。

## State Patterns

加载：显示明确等待；空态：说明还无会话或事件；拒绝：给出可理解原因；故障：保留已有时间线并允许重试；终态前 EOF：显示“结果待确认”并补查运行与事件，running 时继续轮询。完成只能依据持久终态事件或运行状态。已关闭会话禁止其他 API 操作，仅同 token 回放关闭响应。

## Interaction Primitives

发送创建 UUID 幂等键；网络重试沿用同一键。停止取消当前运行。关闭会话时显示返回的最终终态。SSE 使用 streaming `TextDecoder` 解码任意 UTF-8 分片并按空行分帧。键盘操作可达所有按钮、导航和输入；焦点可见。

## Accessibility Floor

状态均有文字，不依赖 `{colors.success}` / `{colors.danger}` 单独传意。错误与等待消息可由屏幕阅读器读到。输入有显式标签，时间线有可读顺序。

## Responsive & Platform

桌面并排显示聊天和时间线；窄屏改成单列。Web 平台仅连接本地 API 与前端开发源，CSP 禁止第三方脚本。

## Key Flows

1. **演示操作者小林查看产品信息：** 选择合成身份、创建会话、提问“产品支持哪些部署版本？”；看到 Product 路由、fixture 来源和 Mock 回答；打开运行详情核对事件。
2. **小林验证授权边界：** 查询自己的账户用量获得只读 Mock 结果；查询其他账户时看到 deny、skipped 与“未执行”回复。
3. **小林处理断流：** 流在终态前中断，界面显示待确认并按 run ID 补查；终态出现后更新时间线。关闭活动会话时看到取消结果，刷新后同 token 可回放关闭结果。

## Gate note

原方案指定的 UI/UX Pro Max skill 在本环境未安装；本文件用 bmad-ux headless 流程记录页面、事件 DTO 和交互状态。具名人物和视觉色值是实施假设，已批准的 API 与安全约束直接沿用原方案。
