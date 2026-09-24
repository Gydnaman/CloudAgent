import test from 'node:test'
import assert from 'node:assert/strict'

const retryState = await import('../src/api/retry-state.ts').catch(() => ({}))

test('a resend of the same session message reuses its idempotency key', () => {
  assert.equal(typeof retryState.getOrCreatePendingRequest, 'function')
  const values = new Map()
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key)
  }

  const first = retryState.getOrCreatePendingRequest('session-a', '查询我的账户用量', storage)
  const retry = retryState.getOrCreatePendingRequest('session-a', '查询我的账户用量', storage)
  assert.equal(first.key, retry.key)

  const changedMessage = retryState.getOrCreatePendingRequest('session-a', '产品支持哪些部署版本？', storage)
  assert.notEqual(changedMessage.key, first.key)
  assert.equal(retryState.loadPendingRequest('session-a', storage).message, '产品支持哪些部署版本？')
  retryState.clearPendingRequest('session-a', changedMessage.key, storage)
  assert.equal(retryState.loadPendingRequest('session-a', storage), null)
})
