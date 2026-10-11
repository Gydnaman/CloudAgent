<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
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
const runAnnouncement = ref('')
const messageInput = ref<HTMLTextAreaElement | null>(null)
const controller = ref<AbortController | null>(null)
const normalized = computed(() => input.value.normalize('NFC').trim())
const length = computed(() => Array.from(normalized.value).length)
const canSend = computed(() => !!demo.session && sessionWork.value === 0 && !initializing.value && !busy.value && !pending.value && !closePending.value && !closed.value && length.value > 0 && length.value <= 4000)
const evidence = computed(() => demo.events.filter(event => event.type === 'knowledge.search.completed'))
const tools = computed(() => demo.events.filter(event => event.type.startsWith('tool.')))
const scenarios = [
  { label: '知识问答', title: '产品支持哪些部署版本？', description: '查看本地知识资料和引用来源。', prompt: '产品支持哪些部署版本？' },
  { label: '本人用量', title: '查询我的账户用量', description: '查看本人账户的只读工具结果。', prompt: '查询我的账户用量' },
  { label: '权限拒绝', title: '查询其他账户用量', description: '观察越权请求如何被拒绝。', prompt: '查询其他账户用量' },
  { label: '无资料', title: '产品的 SLA 是多少？', description: '查看没有知识依据时如何回答。', prompt: '产品的 SLA 是多少？' },
  { label: '不支持的问题', title: '今天天气如何？', description: '观察 Agent 如何识别范围外问题。', prompt: '今天天气如何？' }
]
const promptNotice = ref('')

function startSessionWork(): void { sessionWork.value += 1 }
function finishSessionWork(): void { sessionWork.value = Math.max(0, sessionWork.value - 1) }
function describeError(caught: unknown, action: string): string {
  if (caught instanceof ApiFailure) {
    const guidance: Record<string, string> = {
      missing_session_token: '会话凭据缺失。请结束当前会话并切换演示身份，再重新尝试。',
      invalid_session_token: '会话凭据无效或已过期。请结束当前会话并切换演示身份。',
      session_not_found: '找不到当前会话。请结束当前会话并切换演示身份。',
      session_closed: '当前会话已经关闭。请结束当前会话并切换演示身份后继续。',
      demo_disabled: '本地演示身份尚未启用。请按 README 将 DEMO_AUTH_ENABLED 设为 true，再重启服务。',
      not_ready: '本地服务还在启动。请等待 API 和数据库就绪后重试。',
      run_in_progress: '当前会话已有问题正在处理。请等待片刻，再点“重新查询本次结果”。',
      global_run_limit: '当前演示任务较多。请等待片刻后重试。',
      demo_capacity_reached: '本地演示数据已达到容量上限。请按 README 的“重置本地演示数据”步骤清理后再试。',
      invalid_message: '问题长度须为 1 至 4,000 个码点。请修改输入后重试。',
      idempotency_conflict: '这条请求与先前提交的记录冲突。请重新输入问题后再发送。'
    }
    return guidance[caught.body.code] ?? `${action}未能完成：${caught.body.message}。请确认本地服务正常后重试。`
  }
  if (caught instanceof TypeError) return `${action}失败，无法连接本地服务。请确认 Docker Compose 正在运行，再重试。`
  return `${action}未能完成。请确认 CloudAgent 本地服务正常后重试。`
}
function announceRunOutcome(status: string): void {
  if (status === 'completed' || status === 'run.completed') runAnnouncement.value = 'Agent 已完成本次回答。'
  else if (status === 'failed' || status === 'run.failed') runAnnouncement.value = 'Agent 运行失败。请打开运行详情查看原因。'
  else if (status === 'cancelled' || status === 'run.cancelled') runAnnouncement.value = 'Agent 运行已取消。'
  else runAnnouncement.value = 'Agent 运行状态已更新。请打开运行详情查看。'
}
function announceLatestTerminalEvent(): void {
  const terminal = [...demo.events].reverse().find(event => isTerminal(event.type))
  if (terminal) announceRunOutcome(terminal.type)
}
function loadPrompt(prompt: string): void {
  if (closed.value || busy.value || pending.value) return
  input.value = prompt
  promptNotice.value = '示例问题已填入输入框；确认后点击“发送问题”才会运行。'
  void nextTick(() => messageInput.value?.focus())
}

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
    error.value = describeError(caught, '连接本地演示服务')
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

async function begin(prompt = ''): Promise<void> {
  if (initializing.value || busy.value) return
  startSessionWork()
  busy.value = true
  error.value = ''
  promptNotice.value = ''
  runAnnouncement.value = ''
  let sessionCreated = false
  try {
    setSession(await createSession(subjectId.value))
    sessionCreated = true
    closed.value = false
    demo.events = []
    messages.value = []
    answer.value = ''
    input.value = prompt
    if (prompt) promptNotice.value = '演示会话已创建，示例问题已填入输入框；点击“发送问题”后才会运行。'
  } catch (caught) { error.value = describeError(caught, '创建演示会话') }
  finally {
    busy.value = false
    finishSessionWork()
    if (sessionCreated) {
      await nextTick()
      messageInput.value?.focus()
    }
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
          announceRunOutcome(record.status)
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
  runAnnouncement.value = '正在处理你的问题。'
  error.value = ''
  promptNotice.value = ''
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
      announceLatestTerminalEvent()
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
        error.value = describeError(restoreError, '恢复演示会话')
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
          error.value = describeError(reconcileError, '查询运行结果')
        }
      } else {
        input.value = message
        error.value = describeError(caught, '发送问题')
      }
    } else if (runId) {
      try {
        await reconcile(runId)
        if (!pending.value && !error.value) clearPendingRequest(session.session_id, key)
        else input.value = message
      } catch (reconcileError) {
        pending.value = false
        input.value = message
        error.value = describeError(reconcileError, '查询运行结果')
      }
    } else {
      pending.value = false
      input.value = message
      error.value = caught instanceof DOMException && caught.name === 'AbortError'
        ? '停止请求尚未确认结果；重试同一条消息会沿用原幂等键。'
        : describeError(caught, '发送问题')
    }
  } finally {
    if (error.value && runAnnouncement.value === '正在处理你的问题。') runAnnouncement.value = '本次操作未完成，请阅读页面错误提示。'
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
    error.value = describeError(caught, '查询运行结果')
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
    if (result.terminal_event) {
      consume(result.terminal_event)
      announceRunOutcome(result.terminal_event.type)
    }
    closed.value = true
    pending.value = false
  } catch (caught) { error.value = describeError(caught, '关闭演示会话') }
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
  promptNotice.value = ''
  runAnnouncement.value = ''
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">LOCAL AGENT WORKSPACE</span>
      <h1>{{ demo.session ? '客服工作台' : 'CloudAgent 操作面板' }}</h1>
      <p>{{ demo.session ? '发送客服问题，观察回答依据和 Agent 运行过程。' : '从一个示例开始，直观看到客服 Agent 如何理解问题、查找资料和执行权限判断。' }}</p>
    </div>
    <span class="badge"><span class="badge-dot" aria-hidden="true"></span>本地演示 · MOCK</span>
  </div>
  <div class="notice"><strong>演示数据提醒</strong><span>消息只保存在本地数据库，直到清理演示数据。请勿输入个人或敏感信息。</span></div>
  <div v-if="error" class="alert" role="alert">{{ error }}</div>
  <section v-if="!demo.session" class="launch-dashboard" aria-labelledby="welcome-title">
    <div class="dashboard-top">
      <section class="welcome-hero">
        <span class="hero-label">阶段 A · 本地合成数据</span>
        <h2 id="welcome-title">从一个问题开始，<br />看懂 Agent 如何做决定</h2>
        <p>CloudAgent 是一个可在本机运行的客服 Agent 演示台。它会识别问题、检索固定的演示资料，或按权限尝试只读工具，并把每一步显示在工作台上。</p>
        <div class="hero-flow" aria-label="问题经过 Agent 处理后展示回答和运行过程">
          <span>你的问题</span><span class="flow-arrow" aria-hidden="true">→</span><span>Agent 判断</span><span class="flow-arrow" aria-hidden="true">→</span><span>回答与过程</span>
        </div>
      </section>
      <section class="launch-card card" aria-labelledby="launch-title">
        <div class="launch-heading"><span class="step-number">01</span><div><h2 id="launch-title">开始一个演示</h2><p>先选一个合成身份，再创建会话。</p></div></div>
        <label for="subject">演示身份</label>
        <select id="subject" v-model="subjectId" :disabled="busy || initializing">
          <option v-for="subject in subjects" :key="subject.id" :value="subject.id">{{ subject.label }}</option>
        </select>
        <button class="launch-button" :disabled="busy || initializing" @click="begin()">{{ initializing ? '正在连接本地服务…' : busy ? '正在创建…' : '创建空白演示会话' }}</button>
        <p class="launch-help">创建会话不会自动发送消息，也不会调用真实模型或外部业务服务。</p>
      </section>
    </div>

    <section class="mode-strip" aria-label="当前演示能力">
      <div><span>运行位置</span><strong>本机</strong><small>页面和 API 仅绑定本机</small></div>
      <div><span>回答模型</span><strong>Mock</strong><small>固定、可预测的演示回答</small></div>
      <div><span>知识资料</span><strong>本地 Fixture</strong><small>不接入真实 RAG 知识库</small></div>
      <div><span>业务工具</span><strong>只读 Mock</strong><small>越权请求会显示拒绝</small></div>
    </section>

    <section class="journey-card card" aria-labelledby="journey-title">
      <div class="section-heading"><div><span class="eyebrow">HOW IT WORKS</span><h2 id="journey-title">一次提问会经过这 4 步</h2></div><p>运行后，右侧的时间线会逐步展示这些过程。</p></div>
      <ol class="journey-steps">
        <li><span class="journey-index">1</span><div><strong>收到问题</strong><small>你发送一条客服消息</small></div></li>
        <li><span class="journey-index">2</span><div><strong>识别问题类型</strong><small>路由到产品、账户或澄清</small></div></li>
        <li><span class="journey-index">3</span><div><strong>查资料或校验权限</strong><small>展示引用，或决定是否允许只读工具</small></div></li>
        <li><span class="journey-index">4</span><div><strong>返回答复与记录</strong><small>看到回答、依据和运行事件</small></div></li>
      </ol>
    </section>

    <section class="examples-section" aria-labelledby="examples-title">
      <div class="section-heading"><div><span class="eyebrow">GUIDED DEMO</span><h2 id="examples-title">选择一个示例快速体验</h2></div><p>点击示例会创建会话并预填问题；确认后再点“发送”，不会自动运行。</p></div>
      <div class="example-grid">
        <button v-for="(scenario, index) in scenarios" :key="scenario.label" class="example-card" :disabled="busy || initializing" @click="begin(scenario.prompt)">
          <span class="example-topline"><span class="example-index">0{{ index + 1 }}</span><span class="example-category">{{ scenario.label }}</span></span>
          <strong>{{ scenario.title }}</strong>
          <span class="example-description">{{ scenario.description }}</span>
          <span class="example-action">载入示例 <span aria-hidden="true">→</span></span>
        </button>
      </div>
    </section>

    <section class="more-pages" aria-label="其他功能页面">
      <RouterLink to="/providers" class="more-page-card"><span class="more-page-label">模型与服务状态</span><strong>哪些服务已接入？</strong><span>查看 Mock 可用状态和暂未接入的 Live 服务。</span></RouterLink>
      <RouterLink to="/catalog" class="more-page-card"><span class="more-page-label">知识源与工具</span><strong>Agent 能查什么、能做什么？</strong><span>查看本地演示资料和只读工具清单。</span></RouterLink>
    </section>
  </section>

  <div v-else class="workspace">
    <section class="card chat-card">
      <div class="card-head"><div><span class="eyebrow">LIVE DEMO</span><h2>对话与操作</h2></div><span class="session-state" :class="{ closed }">{{ closed ? '会话已关闭' : '会话进行中' }}</span></div>
      <div class="messages" role="region" aria-label="对话消息">
        <div v-if="!messages.length && !answer" class="empty"><strong>会话已准备好</strong><span>选择示例问题或直接输入消息。发送后，Agent 的处理过程会显示在右侧。</span></div>
        <div v-for="(message, index) in messages" :key="index" class="bubble" :class="message.role"><small>{{ message.role === 'user' ? '合成用户' : 'CloudAgent · MOCK' }}</small><p>{{ message.content }}</p></div>
        <div v-if="answer && busy" class="bubble assistant"><small>CloudAgent · MOCK</small><p>{{ answer }}</p></div>
      </div>
      <div v-if="!messages.length && !closed" class="quick-prompts" role="group" aria-label="建议体验的问题"><span>试试：</span><button v-for="scenario in scenarios" :key="scenario.label" class="prompt-chip" :disabled="initializing || busy || pending" @click="loadPrompt(scenario.prompt)">{{ scenario.title }}</button></div>
      <p class="sr-only" role="status" aria-live="polite">{{ runAnnouncement }}</p>
      <p v-if="promptNotice" class="prompt-notice" role="status">{{ promptNotice }}</p>
      <div v-if="pending" class="pending" role="status">结果待确认，正在按运行编号查询已保存的事件…</div>
      <button v-if="demo.runId && !pending && !closed" class="secondary recheck-button" @click="recheckRun">重新查询本次结果</button>
      <div class="composer"><label for="message">输入客服问题</label><textarea id="message" ref="messageInput" v-model="input" :disabled="closed || initializing || busy || pending" placeholder="例如：产品支持哪些部署版本？"></textarea><div class="composer-actions"><small>{{ length }} / 4000 码点</small><div><button class="secondary" :disabled="!busy" @click="stop">停止运行</button><button :disabled="!canSend" @click="send">{{ busy ? '运行中…' : '发送问题' }}</button></div></div></div>
      <div class="session-actions"><button class="secondary" :disabled="closed || initializing || closePending" @click="close">关闭当前会话</button><button class="secondary" :disabled="sessionWork > 0 || initializing || busy || pending || closePending" @click="switchIdentity">结束并换一个身份</button></div>
    </section>
    <div class="side-stack">
      <section class="card timeline-card"><div class="card-head"><div><span class="eyebrow">RUN TRACE</span><h2>Agent 运行时间线</h2></div><RouterLink v-if="demo.runId" :to="`/runs/${demo.runId}`">查看完整详情 <span aria-hidden="true">→</span></RouterLink></div><p v-if="!demo.events.length" class="side-empty">发送问题后，这里会按顺序显示路由、知识检索、权限判断和回答等步骤。</p><Timeline :events="demo.events" /></section>
      <section class="card evidence-card"><div class="card-head"><div><span class="eyebrow">EVIDENCE & TOOLS</span><h2>回答依据与工具结果</h2></div></div><p v-if="!evidence.length && !tools.length" class="side-empty">如果本次运行检索到资料或检查了工具权限，结果会显示在这里。</p><div v-for="item in evidence" :key="item.event_id" class="result"><strong>知识来源</strong><p>{{ (item.payload.sources as string[]).join(', ') }}</p></div><div v-for="item in tools" :key="item.event_id" class="result" :class="{ denied: item.payload.decision === 'deny' || item.type === 'tool.skipped' }"><strong>{{ item.type === 'tool.skipped' ? '工具未执行' : item.type === 'tool.authorization' ? '授权决定' : '只读工具结果' }}</strong><p>{{ item.payload.decision ?? item.payload.reason ?? (item.payload.summary ? JSON.stringify(item.payload.summary) : '') }}</p></div></section>
    </div>
  </div>
</template>
