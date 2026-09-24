import type { RunEvent } from './types'

export class SSEParser {
  private decoder = new TextDecoder('utf-8')
  private buffer = ''

  feed(bytes: Uint8Array): RunEvent[] {
    this.buffer += this.decoder.decode(bytes, { stream: true })
    return this.drain()
  }

  finish(): RunEvent[] {
    this.buffer += this.decoder.decode()
    return this.drain()
  }

  private drain(): RunEvent[] {
    const events: RunEvent[] = []
    this.buffer = this.buffer.replace(/\r\n/g, '\n')
    let boundary = this.buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = this.buffer.slice(0, boundary)
      this.buffer = this.buffer.slice(boundary + 2)
      const fields: Record<string, string> = {}
      for (const line of frame.split('\n')) {
        if (line.startsWith(':')) continue
        const colon = line.indexOf(':')
        if (colon < 0) continue
        fields[line.slice(0, colon)] = line.slice(colon + 1).trimStart()
      }
      if (fields.data && fields.event && fields.id) {
        const parsed = JSON.parse(fields.data) as RunEvent
        if (parsed.type === fields.event && parsed.event_id === fields.id) events.push(parsed)
      }
      boundary = this.buffer.indexOf('\n\n')
    }
    return events
  }
}
