import test from 'node:test'
import assert from 'node:assert/strict'
import { SSEParser } from '../src/api/sse.ts'

const event = {
  event_id: 'e-1', run_id: 'r-1', sequence: 1, created_at: '2026-09-24T00:00:00Z',
  type: 'llm.delta', payload: { text: '中文🙂' }
}
const frame = new TextEncoder().encode(`id: e-1\nevent: llm.delta\ndata: ${JSON.stringify(event)}\n\n`)

test('SSE parser preserves UTF-8 across every two-way byte split', () => {
  for (let cut = 1; cut < frame.length; cut++) {
    const parser = new SSEParser()
    const result = [...parser.feed(frame.subarray(0, cut)), ...parser.feed(frame.subarray(cut)), ...parser.finish()]
    assert.deepEqual(result, [event], `split at byte ${cut}`)
  }
})

test('SSE parser handles single-byte chunks and does not invent a terminal at EOF', () => {
  const parser = new SSEParser()
  const result = []
  for (const byte of frame) result.push(...parser.feed(Uint8Array.of(byte)))
  result.push(...parser.finish())
  assert.deepEqual(result, [event])
  const incomplete = new SSEParser()
  assert.deepEqual(incomplete.feed(frame.subarray(0, frame.length - 1)), [])
  assert.deepEqual(incomplete.finish(), [])
})
