import type { RelocationPlan, RelocationReason, RelocationStarted } from '../types/relocation'
import { ApiError, apiGet, apiSend } from './client'
import { isFiniteNumberInRange, isNonEmptyString } from './validation'

function invalid(reason: string): never {
  throw new ApiError(`Invalid relocation data: ${reason}`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toReasons(value: unknown): RelocationReason[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item: unknown) =>
    isRecord(item) && typeof item.code === 'string' && typeof item.message === 'string'
      ? [{ code: item.code, message: item.message }]
      : [],
  )
}

function toPlan(payload: unknown): RelocationPlan {
  if (!isRecord(payload)) invalid('plan is not an object')
  const raw = payload
  if (!isNonEmptyString(raw.drone_id)) invalid('missing drone_id')
  if (!isNonEmptyString(raw.destination_hub_id)) invalid('missing destination_hub_id')
  if (typeof raw.eligible !== 'boolean') invalid('missing eligible')
  const numbers = [
    'distance_km',
    'required_battery_pct',
    'expected_battery_use_pct',
    'drone_battery_pct',
    'destination_docked_drones',
    'destination_capacity',
  ] as const
  for (const key of numbers) {
    if (!isFiniteNumberInRange(raw[key], 0, Number.MAX_SAFE_INTEGER)) invalid(`bad ${key}`)
  }
  return {
    droneId: raw.drone_id,
    eligible: raw.eligible,
    reasons: toReasons(raw.reasons),
    originHubId: typeof raw.origin_hub_id === 'string' ? raw.origin_hub_id : null,
    destinationHubId: raw.destination_hub_id,
    distanceKm: raw.distance_km as number,
    requiredBatteryPct: raw.required_battery_pct as number,
    expectedBatteryUsePct: raw.expected_battery_use_pct as number,
    droneBatteryPct: raw.drone_battery_pct as number,
    destinationDockedDrones: raw.destination_docked_drones as number,
    destinationCapacity: raw.destination_capacity as number,
    warnings: Array.isArray(raw.warnings)
      ? raw.warnings.filter((warning): warning is string => typeof warning === 'string')
      : [],
  }
}

/** Read-only preview: can this drone relocate to that Hub now, and why not. */
export async function getRelocationPlan(
  droneId: string,
  destinationHubId: string,
  signal?: AbortSignal,
): Promise<RelocationPlan> {
  const query = `destination_hub_id=${encodeURIComponent(destinationHubId)}`
  return toPlan(
    await apiGet<unknown>(
      `/api/drones/${encodeURIComponent(droneId)}/relocation-plan?${query}`,
      signal,
    ),
  )
}

/** A refused or failed start, with a message that can be shown to the operator as is. */
export class RelocateError extends Error {
  /** The backend's reasons when the drone is no longer eligible. */
  readonly reasons: string[]

  constructor(message: string, reasons: string[] = []) {
    super(message)
    this.name = 'RelocateError'
    this.reasons = reasons
  }
}

function toRelocateError(error: unknown): RelocateError {
  if (!(error instanceof ApiError)) return new RelocateError('The relocation could not be started.')
  if (error.status === undefined) {
    return new RelocateError('The backend is unreachable, so nothing was started.')
  }
  const detail = isRecord(error.detail) ? error.detail : {}
  if (error.status === 503 && detail.code === 'SIMULATION_WORKER_UNAVAILABLE') {
    return new RelocateError(
      'The simulation worker is not running, so the drone cannot fly. Start it with "uv run python -m app.worker" and try again.',
    )
  }
  if (error.status === 409 && detail.code === 'RAIN_WARNING_ACTIVE') {
    return new RelocateError(
      'Takeoff is prohibited while the rain warning is active. Nothing was started.',
    )
  }
  if (error.status === 404) {
    return new RelocateError('The drone or the destination Hub no longer exists.')
  }
  if (error.status === 409 && detail.code === 'RELOCATION_NOT_ELIGIBLE') {
    const plan = isRecord(detail.plan) ? detail.plan : {}
    return new RelocateError(
      'The drone can no longer be relocated:',
      toReasons(plan.reasons).map((reason) => reason.message),
    )
  }
  return new RelocateError(`The relocation could not be started (${error.status}).`)
}

/** Starts an empty relocation flight; rejects with `RelocateError`. */
export async function relocateDrone(
  droneId: string,
  destinationHubId: string,
): Promise<RelocationStarted> {
  let payload: unknown
  try {
    payload = await apiSend<unknown>(
      'POST',
      `/api/drones/${encodeURIComponent(droneId)}/relocate`,
      {
        destination_hub_id: destinationHubId,
      },
    )
  } catch (error) {
    throw toRelocateError(error)
  }
  if (
    !isRecord(payload) ||
    !isNonEmptyString(payload.mission_id) ||
    !isNonEmptyString(payload.drone_id) ||
    !isNonEmptyString(payload.origin_hub_id) ||
    !isNonEmptyString(payload.destination_hub_id)
  ) {
    throw new RelocateError(
      'The backend answered with unexpected data; check the drone before trying again.',
    )
  }
  return {
    missionId: payload.mission_id,
    droneId: payload.drone_id,
    originHubId: payload.origin_hub_id,
    destinationHubId: payload.destination_hub_id,
  }
}
