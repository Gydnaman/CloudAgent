import test from 'node:test'
import assert from 'node:assert/strict'

const values = new Map()
globalThis.sessionStorage = {
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: key => values.delete(key)
}
const state = await import('../src/stores/demo.ts')

test('switching sessions clears the previous run and event timeline', () => {
  const first = { session_id: 'session-a', subject_id: 'demo-alice', subject_label: '小林', demo_session_token: 'token-a', token_expires_at: '2030-01-01T00:00:00Z', source: 'mock' }
  const second = { ...first, session_id: 'session-b', subject_id: 'demo-bob', demo_session_token: 'token-b' }
  state.setSession(first)
  state.setRunId('run-a')
  state.demo.events.push({ event_id: 'event-a' })

  state.setSession(second)

  assert.equal(state.demo.runId, '')
  assert.deepEqual(state.demo.events, [])
})
