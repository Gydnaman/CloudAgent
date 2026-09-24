import { reactive } from 'vue'
import type { DemoSession, RunEvent } from '../api/types'

const saved = sessionStorage.getItem('cloudagent-demo-session')
let restored: DemoSession | null = null
if (saved) {
  try { restored = JSON.parse(saved) as DemoSession } catch { sessionStorage.removeItem('cloudagent-demo-session') }
}

export const demo = reactive({
  session: restored as DemoSession | null,
  runId: sessionStorage.getItem('cloudagent-run-id') ?? '',
  events: [] as RunEvent[]
})

export function setSession(session: DemoSession | null): void {
  if (demo.session?.session_id !== session?.session_id) {
    setRunId('')
    demo.events = []
  }
  demo.session = session
  if (session) sessionStorage.setItem('cloudagent-demo-session', JSON.stringify(session))
  else sessionStorage.removeItem('cloudagent-demo-session')
}

export function setRunId(runId: string): void {
  demo.runId = runId
  if (runId) sessionStorage.setItem('cloudagent-run-id', runId)
  else sessionStorage.removeItem('cloudagent-run-id')
}

export function addEvent(event: RunEvent): void {
  if (demo.events.some(item => item.event_id === event.event_id)) return
  demo.events.push(event)
  demo.events.sort((a, b) => a.sequence - b.sequence)
}
