---
name: CloudAgent Master
description: 本地合成客服 Agent 的 SaaS 工作台视觉系统
status: final
updated: 2026-09-24
colors:
  canvas: '#F4F6FA'
  surface: '#FFFFFF'
  ink: '#172033'
  muted: '#64748B'
  brand: '#4F46E5'
  success: '#087F6D'
  warning: '#B45309'
  danger: '#BE123C'
  border: '#DDE3EC'
typography:
  body: { fontFamily: 'Inter, system-ui, sans-serif', fontSize: '14px', lineHeight: '1.55' }
  title: { fontFamily: 'Inter, system-ui, sans-serif', fontSize: '28px', fontWeight: 700 }
  code: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: '12px' }
rounded: { sm: '7px', md: '12px', lg: '18px' }
spacing: { '1': '4px', '2': '8px', '3': '12px', '4': '16px', '6': '24px', '8': '32px' }
components:
  card: { background: '{colors.surface}', border: '{colors.border}', radius: '{rounded.md}' }
  primary-button: { background: '{colors.brand}', color: '{colors.surface}', radius: '{rounded.sm}' }
  status-denied: { foreground: '{colors.danger}', surface: '#FFF1F2' }
---

## Brand & Style

CloudAgent 是本地 DEMO / MOCK 运行台。布局像可信的 SaaS 运维工作台：清晰、安静、信息密度适中；演示边界始终可见。产品定位来自已批准的阶段 A 方案。

## Colors

`{colors.brand}` 只用于主要操作和路由焦点。完成/授权、待确认、拒绝/故障分别使用 `{colors.success}`、`{colors.warning}`、`{colors.danger}`，同时附上文字标签。背景用 `{colors.canvas}`，数据卡片用 `{colors.surface}`。

## Typography

正文使用 `{typography.body}`；页面标题使用 `{typography.title}`；run ID、序号和事件类型使用 `{typography.code}`。中文回退到系统字体。

## Layout & Spacing

桌面端左侧导航和内容双栏，聊天与时间线并排；窄屏导航换行，内容单列。基本间距从 `{spacing.2}` 到 `{spacing.8}`，最大内容宽度 1440px。

## Elevation & Depth

卡片使用轻边框与轻阴影，禁止以重阴影暗示不真实的层级。

## Shapes

卡片使用 `{rounded.md}`，按钮和输入使用 `{rounded.sm}`。

## Components

主按钮采用 `{components.primary-button}`；焦点有 2px 轮廓。事件时间线逐条显示序号、时间、类型和脱敏摘要。引用、工具授权和最终答复是独立卡片。拒绝态采用 `{components.status-denied}` 并写明“未执行”。

## Do's and Don'ts

所有结果显示 DEMO / MOCK。显示状态文字，不只用颜色。不得展示 token、密钥、真实客户数据或原始授权上下文。

## Gate note

原方案指定的 UI/UX Pro Max skill 在本环境未安装；本设计以可用的 bmad-ux skill 作为 headless gate，按批准的技术方案形成。视觉 tokens 是基于 SaaS 工作台定位的实施假设。
