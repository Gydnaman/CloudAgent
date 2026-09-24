<script setup lang="ts">
import type { RunEvent } from '../api/types'
defineProps<{ events: RunEvent[] }>()
const labels: Record<string, string> = {
  'run.started': '运行开始', 'route.selected': '路由选择', 'route.unsupported': '需要澄清',
  'agent.started': 'Agent 开始', 'knowledge.search.completed': '知识命中', 'knowledge.empty': '知识为空',
  'tool.authorization': '工具授权', 'tool.skipped': '工具未执行', 'tool.completed': '工具完成',
  'llm.delta': '回复片段', 'run.completed': '运行完成', 'run.failed': '运行失败', 'run.cancelled': '运行取消'
}
function summary(event: RunEvent): string {
  if (event.type === 'llm.delta') return String(event.payload.text ?? '')
  if (event.type === 'tool.authorization') return String(event.payload.decision ?? '')
  if (event.type === 'tool.skipped') return '未执行'
  if (event.type === 'knowledge.search.completed') return (event.payload.sources as string[] ?? []).join(', ')
  if (event.type === 'run.completed') return 'Mock 答案已保存'
  if (event.type === 'run.failed') return String(event.payload.error_code ?? 'runtime_error')
  return ''
}
</script>

<template>
  <div v-if="!events.length" class="empty">尚无运行事件</div>
  <ol v-else class="timeline">
    <li v-for="event in events" :key="event.event_id" :class="{ denied: event.payload.decision === 'deny' || event.type === 'tool.skipped', terminal: event.type.startsWith('run.') }">
      <span class="seq">{{ event.sequence }}</span>
      <div><strong>{{ labels[event.type] ?? event.type }}</strong><small>{{ new Date(event.created_at).toLocaleTimeString() }}</small>
        <p v-if="summary(event)">{{ summary(event) }}</p></div>
    </li>
  </ol>
</template>
