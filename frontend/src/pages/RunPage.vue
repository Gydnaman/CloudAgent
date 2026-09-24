<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getEvents, getRun } from '../api/client'
import type { RunEvent, RunRecord } from '../api/types'
import { demo } from '../stores/demo'
import Timeline from '../components/Timeline.vue'
const route = useRoute()
const run = ref<RunRecord | null>(null)
const events = ref<RunEvent[]>([])
const error = ref('')
async function load(): Promise<void> {
  if (!demo.session) { error.value = '请先在工作台创建或恢复会话。'; return }
  try {
    const id = String(route.params.id)
    run.value = await getRun(id, demo.session.demo_session_token)
    events.value = await getEvents(id, demo.session.demo_session_token)
  } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) }
}
onMounted(load)
watch(() => route.params.id, load)
</script>
<template><div class="page-head"><div><span class="eyebrow">TRACE</span><h1>运行详情</h1><p>持久化的 Mock 事件记录。</p></div><span class="badge">DEMO / MOCK</span></div><div v-if="error" class="alert" role="alert">{{ error }} <button class="secondary" @click="load">重试</button></div><template v-if="run"><div class="metrics"><div class="card"><small>状态</small><strong>{{ run.status }}</strong></div><div class="card"><small>意图</small><strong>{{ run.intent ?? '待定' }}</strong></div><div class="card"><small>错误</small><strong>{{ run.error_code ?? '无' }}</strong></div></div><section class="card"><h2>事件序列</h2><p class="muted code">{{ run.run_id }}</p><Timeline :events="events" /></section></template></template>
