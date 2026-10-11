---
name: CloudAgent Master
description: 本地合成客服 Agent 的 SaaS 演示工作台视觉系统
status: final
updated: 2026-10-11
colors:
  canvas: '#F4F6FA'
  surface: '#FFFFFF'
  surface-soft: '#F8F9FC'
  ink: '#172033'
  muted: '#5D6B80'
  brand: '#4F46E5'
  brand-strong: '#3933A8'
  brand-soft: '#EEF0FF'
  sidebar: '#172033'
  success: '#087F6D'
  warning: '#9A5A08'
  danger: '#BE123C'
  border: '#DCE3ED'
  border-strong: '#BDC9D9'
typography:
  body: { fontFamily: 'Inter, Segoe UI, system-ui, sans-serif', fontSize: '15px', lineHeight: '1.6' }
  title: { fontFamily: 'Inter, Segoe UI, system-ui, sans-serif', fontSize: '32px', fontWeight: 700, lineHeight: '1.2' }
  code: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: '12px' }
rounded: { sm: '8px', md: '12px', lg: '16px' }
spacing: { '1': '4px', '2': '8px', '3': '12px', '4': '16px', '6': '24px', '8': '32px' }
components:
  primary-button: { background: '{colors.brand}', color: '{colors.surface}', radius: '{rounded.sm}' }
  panel-card: { background: '{colors.surface}', border: '{colors.border}', radius: '{rounded.md}' }
  status-denied: { foreground: '{colors.danger}', surface: '#FFF1F2' }
  status-authorized: { foreground: '{colors.success}', surface: '#E9F8F3' }
---

## Brand & Style

CloudAgent 是本机运行的 Agent 演示工作台。界面采用清晰、平实的 SaaS 运维面板风格：先说明运行边界，再引导用户开始一次演示，并把回答和运行过程放在同一个工作区。视觉层级主要靠排版、间距和色面建立，不用装饰性渐变或重阴影。

UI/UX Pro Max 的设计系统检索建议使用 Operations Landing 与 Flat Design 的信息组织：介绍产品、展示运行模式、解释处理流程、提供开始操作入口。配色沿用项目已批准的靛蓝体系，避免为“AI”增加粉紫渐变或新的视觉语言。

## Colors

- `{colors.canvas}` 是页面背景，`{colors.surface}` 是内容卡片背景；`{colors.surface-soft}` 用于轻量辅助分区。
- `{colors.brand}` 只用于主要操作、链接和交互焦点；`{colors.brand-soft}` 用于示例标签、步骤编号和低强度选中态。
- `{colors.sidebar}` 用于左侧导航；深色区域只承载导航与首页主介绍，不把主要表单放在暗色底上。
- `{colors.success}`、`{colors.warning}`、`{colors.danger}` 分别表示允许/完成、等待/待确认、拒绝/故障。必须同时显示可读文字，不只用颜色表达状态。
- 正文与按钮文字优先使用 `{colors.ink}`；次级说明使用 `{colors.muted}`，保证对比度和可读性。

## Typography

使用系统字体栈 `Inter, Segoe UI, system-ui, sans-serif`，不从外部加载字体；这与本地运行和内容安全策略一致。标题用清晰的无衬线粗体，正文保持易读行高。桌面正文字号约 15px，窄屏输入文字至少 16px，避免移动浏览器自动放大输入框。

运行编号、事件序号和代码使用 `{typography.code}`。正文不可因状态颜色、截断或低对比而难以理解；长 ID 可以换行。

## Layout & Spacing

桌面端左侧为导航，主区域最大宽度 1600px。首次打开的操作面板采用“介绍与启动入口 → 运行模式 → 处理步骤 → 示例场景 → 更多页面”的顺序。会话运行后，桌面端并列显示聊天和 Agent 时间线；依据与工具结果独立成卡片。

窄屏逐级改为单列：导航移到顶部，启动表单跟在介绍后面，运行时间线和依据卡片排在聊天下方。断点保持在 1200px、980px、700px 和 390px 附近；不得产生横向滚动。间距使用 `{spacing.2}` 至 `{spacing.8}` 的 4/8px 节奏。

## Elevation & Depth

采用平面分区。卡片通过浅色边框和背景区分，不使用重阴影；悬停仅改变边框或背景，不移动布局，不产生跳动。

## Shapes

输入和小按钮使用 `{rounded.sm}`，内容卡片使用 `{rounded.md}`，首页主介绍使用 `{rounded.lg}`。状态标签可以使用胶囊形状；大面积内容卡片不使用胶囊轮廓。

## Components

- **首页欢迎区**：说明这是本地合成数据演示，并把“问题 → Agent 判断 → 回答与过程”可视化。
- **启动表单**：显示合成身份标签，提供唯一主按钮“创建空白演示会话”；点击示例卡片也可创建会话并预填问题，但不会自动发送。
- **运行模式条**：用文字标出本机、Mock、Fixture 和只读 Mock，不伪装成真实服务健康指标。
- **流程步骤**：用顺序编号和解释文案表达处理阶段；窄屏按逻辑顺序换行。
- **示例卡片**：以问题标题、场景说明和“载入示例”行动文字表达用途；整个卡片可键盘聚焦和点击，载入后仍需用户显式发送。
- **会话工作区**：聊天、运行时间线、依据与工具结果分别成区；拒绝操作明确显示“未执行”。
- **错误与等待**：错误靠近页面顶部且可由屏幕阅读器发现；运行中、待确认和关闭会话均显示文字状态。

## Do's and Don'ts

| Do | Don't |
| --- | --- |
| 使用文字和顺序解释 Agent 做了什么 | 只用颜色或图标表达授权和运行状态 |
| 让示例卡片预填问题，并由用户明确点击发送 | 点示例后直接执行工具调用 |
| 为加载、错误、空状态、拒绝和终态提供清楚提示 | 留空白面板或只显示技术错误码 |
| 使用一致的靛蓝品牌色、边框和间距 | 使用装饰性 AI 渐变、表情符号图标或重阴影 |
| 支持键盘操作、可见焦点和减少动态效果设置 | 依赖 hover 或细小图标作为唯一操作入口 |

## Gate note

本次工作使用 UI/UX Pro Max 对 SaaS/Operations Dashboard、UX 空状态与 Vue 栈做设计系统检索；检索结果已结合既有阶段 A 品牌、CSP 和本机演示边界落实。体验与页面状态见 [EXPERIENCE.md](EXPERIENCE.md)。
