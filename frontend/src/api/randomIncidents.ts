import type { RandomIncidentsStatus, RandomIncidentsStatusResponse } from '../types/randomIncidents'
import { ApiError, apiGet, apiPost } from './client'

function invalid(reason: string): never {
  throw new ApiError(`Invalid random incidents data: ${reason}`)
}

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

/** Validates one untrusted API answer and maps it to the UI model. */
export function toRandomIncidentsStatus(item: unknown): RandomIncidentsStatus {
  if (typeof item !== 'object' || item === null) invalid('status is not an object')
  const raw = item as Partial<Record<keyof RandomIncidentsStatusResponse, unknown>>

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

export async function getRandomIncidents(signal?: AbortSignal): Promise<RandomIncidentsStatus> {
  return toRandomIncidentsStatus(await apiGet<unknown>('/api/incidents/random', signal))
}

/** Turns Random Incidents ON; the backend refuses (503) while no simulation worker is alive. */
export async function enableRandomIncidents(): Promise<RandomIncidentsStatus> {
  return toRandomIncidentsStatus(await apiPost<unknown>('/api/incidents/random/enable'))
}

/** Turns Random Incidents OFF. An incident already in progress is not undone. */
export async function disableRandomIncidents(): Promise<RandomIncidentsStatus> {
  return toRandomIncidentsStatus(await apiPost<unknown>('/api/incidents/random/disable'))
}

/** The stable 503 code the backend uses when no simulation worker is alive. */
export function isWorkerUnavailable(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 503) return false
  const { detail } = error
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { code?: unknown }).code === 'SIMULATION_WORKER_UNAVAILABLE'
  )
}
