import {
  MISSION_PURPOSES,
  MISSION_STATUSES,
  type Mission,
  type MissionResponse,
} from '../types/mission'
import { ApiError, apiGet, apiPost } from './client'
import { isFiniteNumberInRange, isNonEmptyString } from './validation'

function invalid(reason: string): never {
  throw new ApiError(`Invalid mission data: ${reason}`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Validates one untrusted API item and maps it to the UI model. */
function toMission(item: unknown): Mission {
  if (!isRecord(item)) invalid('mission is not an object')
  const raw = item as Partial<Record<keyof MissionResponse, unknown>>

  const { id, order_id: orderId, drone_id: droneId, status, total_km: totalKm } = raw
  if (!isNonEmptyString(id)) invalid('missing id')
  // A payload without it predates Feature 019A: every mission then was a delivery.
  const purpose = raw.purpose ?? 'DELIVERY'
  if (typeof purpose !== 'string' || !(MISSION_PURPOSES as readonly string[]).includes(purpose)) {
    invalid(`unknown purpose for ${id}`)
  }
  // Only a relocation (Feature 019A) has no order; a delivery always has one.
  if (purpose === 'DELIVERY' && !isNonEmptyString(orderId)) invalid(`missing order_id for ${id}`)
  if (purpose === 'RELOCATION' && orderId !== null && orderId !== undefined) {
    invalid(`a relocation must not have an order_id for ${id}`)
  }
  if (!isNonEmptyString(droneId)) invalid(`missing drone_id for ${id}`)
  if (!isNonEmptyString(raw.origin_hub_id)) invalid(`missing origin_hub_id for ${id}`)
  if (!isNonEmptyString(raw.return_hub_id)) invalid(`missing return_hub_id for ${id}`)
  if (typeof status !== 'string' || !(MISSION_STATUSES as readonly string[]).includes(status)) {
    invalid(`unknown status for ${id}`)
  }
  if (!isFiniteNumberInRange(totalKm, 0, Number.MAX_SAFE_INTEGER)) invalid(`bad total_km for ${id}`)

  return {
    id,
    orderId: typeof orderId === 'string' ? orderId : null,
    purpose: purpose as Mission['purpose'],
    droneId,
    originHubId: raw.origin_hub_id,
    returnHubId: raw.return_hub_id,
    status: status as Mission['status'],
    totalKm,
  }
}

/** Fetches all missions. Rejects with `ApiError` on HTTP, network or data errors. */
export async function getMissions(signal?: AbortSignal): Promise<Mission[]> {
  const payload = await apiGet<unknown>('/api/missions', signal)
  if (!Array.isArray(payload)) invalid('response is not a list')

  const missions = payload.map(toMission)
  if (new Set(missions.map((mission) => mission.id)).size !== missions.length) {
    invalid('duplicate mission ids')
  }
  return missions
}

export type StartMissionFailure =
  'WORKER_UNAVAILABLE' | 'NOT_STARTABLE' | 'NOT_ELIGIBLE' | 'NOT_FOUND' | 'UNREACHABLE' | 'UNKNOWN'

/** Why a start was refused, with a message that can be shown to the operator as is. */
export class StartMissionError extends Error {
  readonly failure: StartMissionFailure
  /** The backend's reasons when the mission is no longer eligible. */
  readonly reasons: string[]

  constructor(failure: StartMissionFailure, message: string, reasons: string[] = []) {
    super(message)
    this.name = 'StartMissionError'
    this.failure = failure
    this.reasons = reasons
  }
}

function detailRecord(error: ApiError): Record<string, unknown> {
  return isRecord(error.detail) ? error.detail : {}
}

function toStartError(error: unknown): StartMissionError {
  if (!(error instanceof ApiError)) {
    return new StartMissionError('UNKNOWN', 'The mission could not be started.')
  }
  if (error.status === undefined) {
    return new StartMissionError(
      'UNREACHABLE',
      'The backend is unreachable, so nothing was started.',
    )
  }
  const detail = detailRecord(error)
  if (error.status === 503 && detail.code === 'SIMULATION_WORKER_UNAVAILABLE') {
    return new StartMissionError(
      'WORKER_UNAVAILABLE',
      'The simulation worker is not running, so the mission cannot fly. Start it with "uv run python -m app.worker" and try again.',
    )
  }
  if (error.status === 404) {
    return new StartMissionError('NOT_FOUND', 'This mission no longer exists.')
  }
  if (error.status === 409 && detail.code === 'MISSION_NOT_STARTABLE') {
    return new StartMissionError(
      'NOT_STARTABLE',
      `This mission can no longer be started (it is ${String(detail.status ?? 'not assigned')}).`,
    )
  }
  if (error.status === 409 && detail.code === 'MISSION_NOT_ELIGIBLE') {
    const plan = isRecord(detail.plan) ? detail.plan : {}
    const reasons = Array.isArray(plan.reasons)
      ? plan.reasons.flatMap((reason: unknown) =>
          isRecord(reason) && typeof reason.message === 'string' ? [reason.message] : [],
        )
      : []
    return new StartMissionError(
      'NOT_ELIGIBLE',
      'The mission is no longer eligible to start:',
      reasons,
    )
  }
  return new StartMissionError('UNKNOWN', `The mission could not be started (${error.status}).`)
}

/** Takeoff: asks the backend to start an assigned mission. Rejects with `StartMissionError`. */
export async function startMission(missionId: string, signal?: AbortSignal): Promise<Mission> {
  let payload: unknown
  try {
    payload = await apiPost<unknown>(`/api/missions/${encodeURIComponent(missionId)}/start`, signal)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw toStartError(error)
  }
  try {
    return toMission(payload)
  } catch {
    throw new StartMissionError(
      'UNKNOWN',
      'The backend answered with unexpected data; check the mission before trying again.',
    )
  }
}
