import type { AutoDispatchStatus, AutoDispatchStatusResponse } from '../types/dispatch'
import { ApiError, apiGet, apiPost } from './client'

function invalid(reason: string): never {
  throw new ApiError(`Invalid dispatch data: ${reason}`)
}

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

/** Validates one untrusted API answer and maps it to the UI model. */
export function toAutoDispatchStatus(item: unknown): AutoDispatchStatus {
  if (typeof item !== 'object' || item === null) invalid('status is not an object')
  const raw = item as Partial<Record<keyof AutoDispatchStatusResponse, unknown>>

  if (typeof raw.enabled !== 'boolean') invalid('bad enabled')
  if (typeof raw.worker_running !== 'boolean') invalid('bad worker_running')
  if (raw.last_check_at !== null && !isTimestamp(raw.last_check_at)) invalid('bad last_check_at')
  if (raw.last_outcome !== null && typeof raw.last_outcome !== 'string') invalid('bad last_outcome')

  return {
    enabled: raw.enabled,
    workerRunning: raw.worker_running,
    lastCheckAt: raw.last_check_at,
    lastOutcome: raw.last_outcome,
  }
}

export async function getAutoDispatchStatus(signal?: AbortSignal): Promise<AutoDispatchStatus> {
  return toAutoDispatchStatus(await apiGet<unknown>('/api/dispatch/auto/status', signal))
}

/** Turns automatic dispatch ON; the backend refuses (503) while no simulation worker is alive. */
export async function enableAutoDispatch(): Promise<AutoDispatchStatus> {
  return toAutoDispatchStatus(await apiPost<unknown>('/api/dispatch/auto/enable'))
}

/** Turns automatic dispatch OFF. Flights already started continue. */
export async function disableAutoDispatch(): Promise<AutoDispatchStatus> {
  return toAutoDispatchStatus(await apiPost<unknown>('/api/dispatch/auto/disable'))
}
