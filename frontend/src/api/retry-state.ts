export interface PendingRequest {
  sessionId: string
  message: string
  key: string
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const storageKey = 'cloudagent-pending-request'

function read(storage: StorageLike): PendingRequest | null {
  const raw = storage.getItem(storageKey)
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Partial<PendingRequest>
    if (typeof value.sessionId === 'string' && typeof value.message === 'string' && typeof value.key === 'string') {
      return value as PendingRequest
    }
  } catch {
    // Drop corrupt local retry state and let the next send start a new request.
  }
  storage.removeItem(storageKey)
  return null
}

export function loadPendingRequest(sessionId: string, storage: StorageLike = window.sessionStorage): PendingRequest | null {
  const value = read(storage)
  return value?.sessionId === sessionId ? value : null
}

export function getOrCreatePendingRequest(
  sessionId: string,
  message: string,
  storage: StorageLike = window.sessionStorage
): PendingRequest {
  const existing = loadPendingRequest(sessionId, storage)
  if (existing?.message === message) return existing
  const next = { sessionId, message, key: crypto.randomUUID() }
  storage.setItem(storageKey, JSON.stringify(next))
  return next
}

export function clearPendingRequest(
  sessionId: string,
  key: string,
  storage: StorageLike = window.sessionStorage
): void {
  const existing = loadPendingRequest(sessionId, storage)
  if (existing?.key === key) storage.removeItem(storageKey)
}
