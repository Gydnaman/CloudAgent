<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getEvents, getRun } from '../api/client'
import type { RunEvent, RunRecord } from '../api/types'
import { demo } from '../stores/demo'
import Timeline from '../components/Timeline.vue'
const route = useRoute()
const run = ref<RunRecord | null>(null)
const events = ref<RunEvent[]>([])
const error = ref('')
const eventsError = ref('')
const loading = ref(true)
const needsSession = ref(false)
const eventsLoaded = ref(false)
const statusLabels: Record<string, string> = { running: '运行中', completed: '已完成', failed: '运行失败', cancelled: '已取消' }
const intentLabels: Record<string, string> = { product: '产品咨询', billing: '账户用量', unsupported: '范围外问题' }
const failureExplanations: Record<string, string> = {
  run_timeout: 'Agent 处理超过时限后自动停止。可以返回操作面板重新提交；如果反复发生，请查看 API 服务日志。',
  runtime_interrupted: '服务在本次运行期间重启或中断，未完成的运行不会自动继续。可以返回操作面板重新提交。',
  runtime_error: 'Agent 处理时遇到服务端错误。可以返回操作面板重新提交；如果问题持续，请查看 API 服务日志。'
}
const failureExplanation = computed(() => run.value?.error_code ? failureExplanations[run.value.error_code] ?? 'Agent 处理未能完成。可以返回操作面板重新提交；如果问题持续，请查看 API 服务日志。' : '')
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  eventsError.value = ''
  needsSession.value = false
  eventsLoaded.value = false
  run.value = null
  events.value = []
  try {
    if (!demo.session) {
      needsSession.value = true
      error.value = '请先返回操作面板创建或恢复演示会话，再打开运行详情。'
      return
    }
    const id = String(route.params.id)
    run.value = await getRun(id, demo.session.demo_session_token)
    try {
      events.value = await getEvents(id, demo.session.demo_session_token)
      eventsLoaded.value = true
    } catch (caught) {
      eventsError.value = String(caught instanceof Error ? caught.message : caught)
    }
  } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) }
  finally { loading.value = false }
}
onMounted(load)
watch(() => route.params.id, load)
</script>
<template>
  <div class="page-head">
    <div><span class="eyebrow">RUN TRACE</span><h1>运行详情</h1><p>查看这次问题处理的状态和按时间保存的 Agent 事件。</p></div>
    <span class="badge"><span class="badge-dot" aria-hidden="true"></span>本地演示 · MOCK</span>
  </div>
  <div v-if="error" class="alert" role="alert">无法读取运行记录：{{ error }} <RouterLink v-if="needsSession" to="/" class="alert-link">返回操作面板</RouterLink><button v-else class="secondary" :disabled="loading" @click="load">重新加载</button></div>
  <div v-if="eventsError" class="alert" role="alert">运行状态已读取，但处理事件读取失败：{{ eventsError }} <button class="secondary" :disabled="loading" @click="load">重新加载</button></div>
  <div v-if="loading" class="card load-state" role="status" aria-live="polite">正在读取本次运行的状态和事件…</div>
  <template v-else-if="run">
    <div class="metrics">
      <div class="card"><small>运行结果</small><strong>{{ statusLabels[run.status] ?? run.status }}</strong><p v-if="run.status === 'running'" class="provider-description">此处显示最近一次读取的状态和事件。</p><button v-if="run.status === 'running'" class="secondary" :disabled="loading" @click="load">重新加载状态与事件</button></div>
      <div class="card"><small>识别的问题类型</small><strong>{{ run.intent ? intentLabels[run.intent] ?? run.intent : '尚未识别' }}</strong></div>
      <div class="card"><small>错误记录</small><strong>{{ run.error_code ? '运行未完成' : '无错误' }}</strong><p v-if="run.error_code" class="provider-description">{{ failureExplanation }} <span class="code">错误代码：{{ run.error_code }}</span></p></div>
    </div>
    <section class="card"><div class="card-head"><div><span class="eyebrow">SAVED EVENTS</span><h2>处理步骤</h2></div><RouterLink to="/">返回操作面板 <span aria-hidden="true">→</span></RouterLink></div><p class="muted code">运行编号：{{ run.run_id }}</p><p v-if="eventsLoaded && !events.length" class="side-empty">这次运行没有已保存的处理事件。</p><Timeline :events="events" /></section>
  </template>
</template>
