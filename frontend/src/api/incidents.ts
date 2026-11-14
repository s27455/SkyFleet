import type { LprScenario, LprStatus } from '../types/lpr'
import { ApiError, apiGet, apiPost } from './client'
import { isFiniteNumberInRange, isNonEmptyString, isPositiveFiniteNumber } from './validation'

/** What a manual Drone failure did (`POST /api/incidents/drone-failure`). */
export interface DroneFailureResult {
  droneId: string
  missionId: string
  /** null when a relocating drone failed (Feature 019A). */
  orderId: string | null
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
  if (orderId !== null && (typeof orderId !== 'string' || orderId === '')) {
    invalid('bad order_id')
  }
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
    orderId: orderId ?? null,
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

/** What a manual Recipient unavailable did (`POST /api/incidents/recipient-unavailable`). */
export interface RecipientUnavailableResult {
  droneId: string
  missionId: string
  orderId: string
  /** ISO 8601: when the drone reaches the destination and the delivery really fails. */
  attemptAt: string
}

/**
 * Asks the backend to mark one delivery on its way as "recipient unavailable". The outcome is
 * pending: the drone still flies to the destination and the order only fails there. With nothing
 * eligible it answers 409 `NO_ELIGIBLE_TARGET` (see `isNoEligibleTarget`) and creates nothing.
 */
export async function triggerRecipientUnavailable(): Promise<RecipientUnavailableResult> {
  const payload = await apiPost<unknown>('/api/incidents/recipient-unavailable')
  if (typeof payload !== 'object' || payload === null) invalid('not an object')
  const raw = payload as Record<string, unknown>
  const { drone_id: droneId, mission_id: missionId, order_id: orderId, attempt_at: attemptAt } = raw
  if (typeof droneId !== 'string' || droneId === '') invalid('missing drone_id')
  if (typeof missionId !== 'string' || missionId === '') invalid('missing mission_id')
  if (typeof orderId !== 'string' || orderId === '') invalid('missing order_id')
  if (typeof attemptAt !== 'string' || Number.isNaN(Date.parse(attemptAt))) {
    invalid('bad attempt_at')
  }
  return { droneId, missionId, orderId, attemptAt }
}

function toPosition(value: unknown, what: string): [number, number] {
  if (
    !Array.isArray(value) ||
    value.length !== 2 ||
    !isFiniteNumberInRange(value[0], -180, 180) ||
    !isFiniteNumberInRange(value[1], -90, 90)
  ) {
    invalid(`bad ${what}`)
  }
  return [value[0] as number, value[1] as number]
}

const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && /(Z|[+-]\d\d:?\d\d)$/.test(value) && !Number.isNaN(Date.parse(value))

function toLprScenario(payload: unknown): LprScenario {
  if (typeof payload !== 'object' || payload === null) invalid('LPR scenario is not an object')
  const raw = payload as Record<string, unknown>
  if (!isNonEmptyString(raw.id)) invalid('missing LPR scenario id')
  if (!isTimestamp(raw.started_at)) invalid('bad started_at')
  if (!isTimestamp(raw.ends_at)) invalid('bad ends_at')
  if (!isPositiveFiniteNumber(raw.speed_ms)) invalid('bad speed_ms')
  if (!isPositiveFiniteNumber(raw.radius_m)) invalid('bad radius_m')
  if (!isFiniteNumberInRange(raw.hold_margin_m, 0, Number.MAX_SAFE_INTEGER)) {
    invalid('bad hold_margin_m')
  }
  return {
    id: raw.id,
    startedAt: raw.started_at,
    endsAt: raw.ends_at,
    position: toPosition(raw.position, 'LPR position'),
    routeStart: toPosition(raw.route_start, 'LPR route_start'),
    routeEnd: toPosition(raw.route_end, 'LPR route_end'),
    speedMs: raw.speed_ms,
    radiusM: raw.radius_m,
    holdMarginM: raw.hold_margin_m,
  }
}

/**
 * Starts the LPR helicopter pass (`POST /api/incidents/lpr-helicopter`). Only one scenario runs at
 * a time: a second trigger answers 409 `LPR_ALREADY_ACTIVE` (see `isLprAlreadyActive`).
 */
export async function triggerLprHelicopter(): Promise<LprScenario> {
  return toLprScenario(await apiPost<unknown>('/api/incidents/lpr-helicopter'))
}

/** The running LPR scenario, or `{ scenario: null }` (`GET /api/incidents/lpr`). */
export async function getLprStatus(signal?: AbortSignal): Promise<LprStatus> {
  const payload = await apiGet<unknown>('/api/incidents/lpr', signal)
  if (typeof payload !== 'object' || payload === null) invalid('LPR status is not an object')
  const { scenario } = payload as { scenario?: unknown }
  return { scenario: scenario === null || scenario === undefined ? null : toLprScenario(scenario) }
}

/** True for the backend's clear "a helicopter is already crossing" answer, not a failed request. */
export function isLprAlreadyActive(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false
  const { detail } = error
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { code?: unknown }).code === 'LPR_ALREADY_ACTIVE'
  )
}
