<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiFailure, closeSession, createSession, getEvents, getRun, getSession, getSubjects, streamRun } from '../api/client'
import { isTerminal } from '../api/types'
import type { Message, DemoSession } from '../api/types'
import { clearPendingRequest, getOrCreatePendingRequest, loadPendingRequest } from '../api/retry-state'
import { addEvent, demo, setRunId, setSession } from '../stores/demo'
import Timeline from '../components/Timeline.vue'

const subjects = ref<Array<{id: string; label: string}>>([])
const subjectId = ref('demo-alice')
const messages = ref<Message[]>([])
const input = ref('')
const busy = ref(false)
const closePending = ref(false)
const initializing = ref(false)
const sessionWork = ref(0)
const pending = ref(false)
const closed = ref(false)
const error = ref('')
const answer = ref('')
const controller = ref<AbortController | null>(null)
const normalized = computed(() => input.value.normalize('NFC').trim())
const length = computed(() => Array.from(normalized.value).length)
const canSend = computed(() => !!demo.session && sessionWork.value === 0 && !initializing.value && !busy.value && !pending.value && !closePending.value && !closed.value && length.value > 0 && length.value <= 4000)
const evidence = computed(() => demo.events.filter(event => event.type === 'knowledge.search.completed'))
const tools = computed(() => demo.events.filter(event => event.type.startsWith('tool.')))

function startSessionWork(): void { sessionWork.value += 1 }
function finishSessionWork(): void { sessionWork.value = Math.max(0, sessionWork.value - 1) }

onMounted(async () => {
  startSessionWork()
  initializing.value = true
  try {
    subjects.value = await getSubjects()
    if (demo.session) {
      const session = demo.session
      const retry = loadPendingRequest(session.session_id)
      if (retry) input.value = retry.message
      if (session.closed_at) {
        await restoreClosedSession(session)
      } else {
        try {
          const current = await getSession(session)
          messages.value = current.messages
        } catch (caught) {
          if (caught instanceof ApiFailure && caught.body.code === 'session_closed') await restoreClosedSession(session)
          else throw caught
        }
        if (!closed.value && demo.runId) {
          demo.events = await getEvents(demo.runId, session.demo_session_token)
          const run = await getRun(demo.runId, session.demo_session_token)
          if (run.status === 'running') await reconcile(demo.runId)
        }
      }
    }
  } catch (caught) {
    pending.value = false
    error.value = String(caught instanceof Error ? caught.message : caught)
  } finally {
    initializing.value = false
    finishSessionWork()
  }
})

async function restoreClosedSession(session: DemoSession): Promise<void> {
  startSessionWork()
  try {
    const receipt = await closeSession(session)
    setSession({ ...session, closed_at: receipt.closed_at, close_run_id: receipt.close_run_id })
    if (receipt.close_run_id) setRunId(receipt.close_run_id)
    if (receipt.terminal_event) consume(receipt.terminal_event)
    closed.value = true
    pending.value = false
  } finally { finishSessionWork() }
}

async function begin(): Promise<void> {
  if (initializing.value || busy.value) return
  startSessionWork()
  busy.value = true
  error.value = ''
  try {
    setSession(await createSession(subjectId.value))
    closed.value = false
    demo.events = []
    messages.value = []
    answer.value = ''
  } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) }
  finally {
    busy.value = false
    finishSessionWork()
  }
}

function consume(event: import('../api/types').RunEvent): void {
  addEvent(event)
  if (event.type === 'llm.delta') answer.value += String(event.payload.text ?? '')
  if (event.type === 'run.completed') answer.value = String(event.payload.answer ?? answer.value)
  if (isTerminal(event.type)) pending.value = false
}

async function reconcile(runId: string): Promise<void> {
  if (!demo.session || closed.value) return
  startSessionWork()
  pending.value = true
  try {
    for (let attempt = 0; attempt < 125; attempt++) {
      const session = demo.session
      if (!session || closed.value) return
      const record = await getRun(runId, session.demo_session_token)
      const events = await getEvents(runId, session.demo_session_token)
      events.forEach(consume)
      if (record.status !== 'running' || events.some(event => isTerminal(event.type))) {
        pending.value = false
        if (!closed.value) {
          const current = await getSession(session)
          messages.value = current.messages
        }
        return
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
    pending.value = false
    error.value = '运行仍在处理中；可点击“重新查询结果”继续对账。'
  } finally {
    finishSessionWork()
  }
}

async function send(): Promise<void> {
  if (!canSend.value || !demo.session) return
  startSessionWork()
  const session = demo.session
  const message = normalized.value
  const pendingRequest = getOrCreatePendingRequest(session.session_id, message)
  const key = pendingRequest.key
  input.value = ''
  answer.value = ''
  error.value = ''
  pending.value = false
  busy.value = true
  demo.events = []
  setRunId('')
  controller.value = new AbortController()
  let runId = ''
  try {
    const terminal = await streamRun(session, message, key, controller.value.signal,
      id => { runId = id; setRunId(id) }, consume)
    if (!terminal && runId) await reconcile(runId)
    if (terminal || (!pending.value && !error.value && runId)) clearPendingRequest(session.session_id, key)
    else input.value = message
    if (!closed.value && (terminal || (!pending.value && !error.value && runId))) {
      const current = await getSession(session)
      messages.value = current.messages
    }
  } catch (caught) {
    if (closed.value) {
      pending.value = false
      clearPendingRequest(session.session_id, key)
    } else if (caught instanceof ApiFailure && caught.body.code === 'session_closed') {
      try {
        await restoreClosedSession(session)
        clearPendingRequest(session.session_id, key)
      } catch (restoreError) {
        pending.value = false
        error.value = String(restoreError instanceof Error ? restoreError.message : restoreError)
      }
    } else if (caught instanceof ApiFailure && caught.body.run_id) {
      runId = caught.body.run_id
      setRunId(runId)
      if (caught.body.code === 'duplicate_request') {
        try {
          await reconcile(runId)
          if (!pending.value && !error.value) clearPendingRequest(session.session_id, key)
          else input.value = message
        } catch (reconcileError) {
          pending.value = false
          input.value = message
          error.value = String(reconcileError instanceof Error ? reconcileError.message : reconcileError)
        }
      } else {
        input.value = message
        error.value = caught.body.message
      }
    } else if (runId) {
      try {
        await reconcile(runId)
        if (!pending.value && !error.value) clearPendingRequest(session.session_id, key)
        else input.value = message
      } catch (reconcileError) {
        pending.value = false
        input.value = message
        error.value = String(reconcileError instanceof Error ? reconcileError.message : reconcileError)
      }
    } else {
      pending.value = false
      input.value = message
      error.value = caught instanceof DOMException && caught.name === 'AbortError'
        ? '停止请求尚未确认结果；重试同一条消息会沿用原幂等键。'
        : String(caught instanceof Error ? caught.message : caught)
    }
  } finally {
    busy.value = false
    controller.value = null
    finishSessionWork()
  }
}

function stop(): void {
  controller.value?.abort()
  if (demo.runId) pending.value = true
  else {
    pending.value = false
    error.value = '停止请求已发送；若结果尚未确认，可重试同一条消息进行对账。'
  }
}

async function recheckRun(): Promise<void> {
  if (!demo.runId || !demo.session || closed.value) return
  startSessionWork()
  error.value = ''
  try {
    await reconcile(demo.runId)
    if (!pending.value && !error.value) {
      const retry = loadPendingRequest(demo.session.session_id)
      if (retry) clearPendingRequest(demo.session.session_id, retry.key)
    }
  } catch (caught) {
    pending.value = false
    error.value = String(caught instanceof Error ? caught.message : caught)
  } finally {
    finishSessionWork()
  }
}

async function close(): Promise<void> {
  if (!demo.session) return
  const wasBusy = busy.value
  startSessionWork()
  closePending.value = true
  busy.value = true
  try {
    const session = demo.session
    const result = await closeSession(session)
    setSession({ ...session, closed_at: result.closed_at, close_run_id: result.close_run_id })
    if (result.close_run_id) setRunId(result.close_run_id)
    if (result.terminal_event) consume(result.terminal_event)
    closed.value = true
    pending.value = false
  } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) }
  finally {
    closePending.value = false
    if (!wasBusy) busy.value = false
    finishSessionWork()
  }
}

function switchIdentity(): void {
  if (sessionWork.value > 0 || initializing.value || busy.value || pending.value || closePending.value) return
  setSession(null)
  closed.value = false
  messages.value = []
  answer.value = ''
  input.value = ''
  error.value = ''
}
</script>

<template>
  <div class="page-head"><div><span class="eyebrow">CUSTOMER WORKSPACE</span><h1>客服工作台</h1><p>固定场景展示意图路由、知识引用和只读工具授权。</p></div><span class="badge">DEMO / MOCK</span></div>
  <div class="notice">本地演示消息会保存在本地数据库，直至运行全量重置。请勿输入个人或敏感信息。</div>
  <div v-if="error" class="alert" role="alert">{{ error }}</div>
  <div class="workspace">
    <section class="card chat-card">
      <div class="card-head"><h2>对话</h2><span v-if="demo.session" class="muted">{{ closed ? '已关闭' : '会话进行中' }}</span></div>
      <div v-if="!demo.session" class="session-start"><label for="subject">合成演示身份</label><select id="subject" v-model="subjectId" :disabled="busy || initializing"><option v-for="subject in subjects" :key="subject.id" :value="subject.id">{{ subject.label }}</option></select><button :disabled="busy || initializing" @click="begin">创建演示会话</button></div>
      <template v-else>
        <div class="messages" aria-live="polite"><div v-if="!messages.length && !answer" class="empty">可尝试“产品支持哪些部署版本？”或“查询我的账户用量”。</div><div v-for="(message, index) in messages" :key="index" class="bubble" :class="message.role"><small>{{ message.role === 'user' ? '合成用户' : 'CloudAgent · MOCK' }}</small><p>{{ message.content }}</p></div><div v-if="answer && busy" class="bubble assistant"><small>CloudAgent · MOCK</small><p>{{ answer }}</p></div></div>
        <div v-if="pending" class="pending" role="status">结果待确认，正在按 run ID 查询持久事件…</div>
        <button v-if="demo.runId && !pending && !closed" class="secondary" @click="recheckRun">重新查询结果</button>
        <div class="composer"><label for="message">消息</label><textarea id="message" v-model="input" :disabled="closed" placeholder="输入产品或账户用量问题"></textarea><div class="composer-actions"><small>{{ length }} / 4000 码点</small><div><button class="secondary" :disabled="!busy" @click="stop">停止</button><button :disabled="!canSend" @click="send">{{ busy ? '运行中…' : '发送' }}</button></div></div></div>
        <div class="session-actions"><button class="secondary" :disabled="closed || initializing || closePending" @click="close">关闭当前会话</button><button class="secondary" :disabled="sessionWork > 0 || initializing || busy || pending || closePending" @click="switchIdentity">切换身份</button></div>
      </template>
    </section>
    <div class="side-stack"><section class="card"><div class="card-head"><h2>Agent 时间线</h2><RouterLink v-if="demo.runId" :to="`/runs/${demo.runId}`">运行详情 →</RouterLink></div><Timeline :events="demo.events" /></section><section class="card"><h2>依据与工具</h2><div v-if="!evidence.length && !tools.length" class="empty">运行后显示 fixture 引用或脱敏工具结果。</div><div v-for="item in evidence" :key="item.event_id" class="result"><strong>知识来源</strong><p>{{ (item.payload.sources as string[]).join(', ') }}</p></div><div v-for="item in tools" :key="item.event_id" class="result" :class="{ denied: item.payload.decision === 'deny' || item.type === 'tool.skipped' }"><strong>{{ item.type === 'tool.skipped' ? '工具未执行' : item.type === 'tool.authorization' ? '授权决定' : '只读工具结果' }}</strong><p>{{ item.payload.decision ?? item.payload.reason ?? (item.payload.summary ? JSON.stringify(item.payload.summary) : '') }}</p></div></section></div>
  </div>
</template>
