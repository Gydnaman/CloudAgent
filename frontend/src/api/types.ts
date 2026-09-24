import type { components } from './openapi.gen'

export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled'
export type RunEvent = components['schemas']['RunEventDTO']
export type RunRecord = components['schemas']['RunDTO'] & { status: RunStatus }
export type Message = components['schemas']['MessageDTO']
export type DemoSession = components['schemas']['CreatedSessionDTO'] & {
  closed_at?: string
  close_run_id?: string | null
}
export interface ApiErrorBody { code: string; message: string; run_id?: string }
export const isTerminal = (type: string): boolean => ['run.completed', 'run.failed', 'run.cancelled'].includes(type)
