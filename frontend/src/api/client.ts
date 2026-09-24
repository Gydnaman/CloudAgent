import { SSEParser } from './sse'
import type { ApiErrorBody, DemoSession, Message, RunEvent, RunRecord } from './types'

const base = '/api/v1'

export class ApiFailure extends Error {
  constructor(public status: number, public body: ApiErrorBody) { super(body.message) }
}

async function checked(response: Response): Promise<Response> {
  if (response.ok) return response
  let body: ApiErrorBody = { code: 'network_error', message: `请求失败 (${response.status})` }
  try { body = await response.json() as ApiErrorBody } catch { /* retain generic error */ }
  throw new ApiFailure(response.status, body)
}

function auth(token: string): HeadersInit { return { 'X-Demo-Session-Token': token } }

export async function getSubjects(): Promise<Array<{id: string; label: string; role: string}>> {
  return (await checked(await fetch(`${base}/demo/subjects`))).json()
}

export async function createSession(subjectId: string): Promise<DemoSession> {
  return (await checked(await fetch(`${base}/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subject_id: subjectId }) }))).json()
}

export async function getSession(session: DemoSession): Promise<{messages: Message[]}> {
  return (await checked(await fetch(`${base}/sessions/${session.session_id}`, { headers: auth(session.demo_session_token) }))).json()
}

export async function closeSession(session: DemoSession): Promise<{closed_at: string; close_run_id: string | null; terminal_event: RunEvent | null}> {
  return (await checked(await fetch(`${base}/sessions/${session.session_id}/close`, { method: 'POST', headers: auth(session.demo_session_token) }))).json()
}

export async function getRun(runId: string, token: string): Promise<RunRecord> {
  return (await checked(await fetch(`${base}/runs/${runId}`, { headers: auth(token) }))).json()
}

export async function getEvents(runId: string, token: string): Promise<RunEvent[]> {
  return (await checked(await fetch(`${base}/runs/${runId}/events`, { headers: auth(token) }))).json()
}

export async function streamRun(session: DemoSession, message: string, key: string, signal: AbortSignal,
                                onRunId: (id: string) => void, onEvent: (event: RunEvent) => void): Promise<boolean> {
  const response = await checked(await fetch(`${base}/sessions/${session.session_id}/runs/stream`, {
    method: 'POST', headers: { ...auth(session.demo_session_token), 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify({ message }), signal
  }))
  const runId = response.headers.get('X-Run-ID')
  if (runId) onRunId(runId)
  if (!response.body) throw new Error('SSE 响应没有流')
  const reader = response.body.getReader()
  const parser = new SSEParser()
  let terminal = false
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    for (const event of parser.feed(value)) {
      onEvent(event)
      if (['run.completed', 'run.failed', 'run.cancelled'].includes(event.type)) terminal = true
    }
  }
  for (const event of parser.finish()) {
    onEvent(event)
    if (['run.completed', 'run.failed', 'run.cancelled'].includes(event.type)) terminal = true
  }
  return terminal
}

export async function providerStatus(): Promise<{providers: Array<{name: string; status: string; mode: string}>}> {
  return (await checked(await fetch(`${base}/providers/status`))).json()
}

export async function catalog(): Promise<{knowledge: Array<{id: string; name: string; type: string; status: string}>; tools: Array<{name: string; type: string; status: string}>}> {
  return (await checked(await fetch(`${base}/catalog`))).json()
}
