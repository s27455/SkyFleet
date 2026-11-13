import { ApiError, apiPost } from './client'

/** What a manual Drone failure did (`POST /api/incidents/drone-failure`). */
export interface DroneFailureResult {
  droneId: string
  missionId: string
  orderId: string
  stage: string
  /** [longitude, latitude] of the simulated emergency landing point. */
  landingPosition: [number, number]
}

function invalid(reason: string): never {
  throw new ApiError(`Invalid incident data: ${reason}`)
}

function toResult(payload: unknown): DroneFailureResult {
  if (typeof payload !== 'object' || payload === null) invalid('not an object')
  const raw = payload as Record<string, unknown>
  const { drone_id: droneId, mission_id: missionId, order_id: orderId, stage } = raw
  const position = raw.landing_position
  if (typeof droneId !== 'string' || droneId === '') invalid('missing drone_id')
  if (typeof missionId !== 'string' || missionId === '') invalid('missing mission_id')
  if (typeof orderId !== 'string' || orderId === '') invalid('missing order_id')
  if (typeof stage !== 'string') invalid('missing stage')
  if (
    !Array.isArray(position) ||
    position.length !== 2 ||
    !position.every((value) => typeof value === 'number' && Number.isFinite(value))
  ) {
    invalid('bad landing_position')
  }
  return {
    droneId,
    missionId,
    orderId,
    stage,
    landingPosition: [position[0] as number, position[1] as number],
  }
}

/**
 * Asks the backend to fail one eligible flying drone. The backend chooses the drone; with none
 * eligible it answers 409 `NO_ELIGIBLE_TARGET` (see `isNoEligibleTarget`) and creates nothing.
 */
export async function triggerDroneFailure(): Promise<DroneFailureResult> {
  return toResult(await apiPost<unknown>('/api/incidents/drone-failure'))
}

/** True for the backend's clear "nothing to fail" answer, which is not an error of the request. */
export function isNoEligibleTarget(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false
  const { detail } = error
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { code?: unknown }).code === 'NO_ELIGIBLE_TARGET'
  )
}
