import {
  EMERGENCY_REASONS,
  FLIGHT_PHASES,
  type Flight,
  type FlightEmergency,
  type FlightResponse,
  type FlightsSnapshot,
} from '../types/flight'
import { MISSION_PURPOSES, MISSION_STATUSES } from '../types/mission'
import { ApiError, apiGet } from './client'
import { isFiniteNumberInRange, isNonEmptyString } from './validation'

function invalid(reason: string): never {
  throw new ApiError(`Invalid flight data: ${reason}`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Timestamps from the backend are timezone-aware ISO 8601 strings. */
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

function toPosition(value: unknown, what: string): [number, number] {
  if (
    !Array.isArray(value) ||
    value.length !== 2 ||
    !isFiniteNumberInRange(value[0], -180, 180) ||
    !isFiniteNumberInRange(value[1], -90, 90)
  ) {
    invalid(`bad ${what}`)
  }
  // Mapbox expects [longitude, latitude]; these are the stored values.
  return [value[0] as number, value[1] as number]
}

function toEmergency(value: unknown, id: string): FlightEmergency | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) invalid(`bad emergency for ${id}`)
  const { reason, at, position, acknowledged_at: acknowledgedAt } = value
  if (typeof reason !== 'string' || !(EMERGENCY_REASONS as readonly string[]).includes(reason)) {
    invalid(`unknown emergency reason for ${id}`)
  }
  if (!isTimestamp(at)) invalid(`bad emergency time for ${id}`)
  // Absent (an older backend) or null means not acknowledged.
  if (acknowledgedAt !== undefined && acknowledgedAt !== null && !isTimestamp(acknowledgedAt)) {
    invalid(`bad emergency acknowledgement time for ${id}`)
  }
  return {
    reason: reason as FlightEmergency['reason'],
    at,
    position: toPosition(position, `emergency position for ${id}`),
    acknowledgedAt: acknowledgedAt ?? null,
  }
}

/** Validates one untrusted API item and maps it to the UI model. */
function toFlight(item: unknown, serverTimeMs: number): Flight {
  if (!isRecord(item)) invalid('flight is not an object')
  const raw = item as Partial<Record<keyof FlightResponse, unknown>>

  const id = raw.mission_id
  if (!isNonEmptyString(id)) invalid('missing mission_id')
  // A payload without it predates Feature 019A: every mission then was a delivery.
  const purpose = raw.purpose ?? 'DELIVERY'
  if (typeof purpose !== 'string' || !(MISSION_PURPOSES as readonly string[]).includes(purpose)) {
    invalid(`unknown purpose for ${id}`)
  }
  // Only a relocation (Feature 019A) has no order; a delivery always has one.
  if (purpose === 'DELIVERY' && !isNonEmptyString(raw.order_id))
    invalid(`missing order_id for ${id}`)
  for (const key of [
    'drone_id',
    'origin_hub_id',
    'planned_return_hub_id',
    'landing_target_hub_id',
  ] as const) {
    if (!isNonEmptyString(raw[key])) invalid(`missing ${key} for ${id}`)
  }
  if (typeof raw.mission_status !== 'string') invalid(`bad mission_status for ${id}`)
  if (!(MISSION_STATUSES as readonly string[]).includes(raw.mission_status)) {
    invalid(`unknown mission_status for ${id}`)
  }
  if (typeof raw.phase !== 'string' || !(FLIGHT_PHASES as readonly string[]).includes(raw.phase)) {
    invalid(`unknown phase for ${id}`)
  }
  if (!isFiniteNumberInRange(raw.progress, 0, 1)) invalid(`bad progress for ${id}`)
  if (!isFiniteNumberInRange(raw.battery_pct, 0, 100)) invalid(`bad battery_pct for ${id}`)
  if (!isTimestamp(raw.started_at)) invalid(`bad started_at for ${id}`)
  if (!isTimestamp(raw.updated_at)) invalid(`bad updated_at for ${id}`)
  if (
    raw.delivered_at !== null &&
    raw.delivered_at !== undefined &&
    !isTimestamp(raw.delivered_at)
  ) {
    invalid(`bad delivered_at for ${id}`)
  }
  if (raw.recalled_at !== null && raw.recalled_at !== undefined && !isTimestamp(raw.recalled_at)) {
    invalid(`bad recalled_at for ${id}`)
  }
  if (raw.failed_at !== null && raw.failed_at !== undefined && !isTimestamp(raw.failed_at)) {
    invalid(`bad failed_at for ${id}`)
  }
  for (const key of ['recipient_unavailable_at', 'handover_failed_at'] as const) {
    const value = raw[key]
    if (value !== null && value !== undefined && !isTimestamp(value))
      invalid(`bad ${key} for ${id}`)
  }

  let target: Flight['target'] = null
  if (raw.target !== null && raw.target !== undefined) {
    if (!isRecord(raw.target)) invalid(`bad target for ${id}`)
    if (!isFiniteNumberInRange(raw.target.eta_s, 0, Number.MAX_SAFE_INTEGER)) {
      invalid(`bad target eta for ${id}`)
    }
    target = {
      position: toPosition(raw.target.position, `target position for ${id}`),
      etaS: raw.target.eta_s,
    }
  }

  return {
    missionId: id,
    orderId: typeof raw.order_id === 'string' ? raw.order_id : null,
    purpose: purpose as Flight['purpose'],
    droneId: raw.drone_id as string,
    missionStatus: raw.mission_status,
    phase: raw.phase as Flight['phase'],
    progress: raw.progress,
    position: toPosition(raw.position, `position for ${id}`),
    batteryPct: raw.battery_pct,
    target,
    originHubId: raw.origin_hub_id as string,
    plannedReturnHubId: raw.planned_return_hub_id as string,
    landingTargetHubId: raw.landing_target_hub_id as string,
    startedAt: raw.started_at,
    deliveredAt: (raw.delivered_at as string | null | undefined) ?? null,
    recalledAt: (raw.recalled_at as string | null | undefined) ?? null,
    failedAt: (raw.failed_at as string | null | undefined) ?? null,
    recipientUnavailableAt: (raw.recipient_unavailable_at as string | null | undefined) ?? null,
    handoverFailedAt: (raw.handover_failed_at as string | null | undefined) ?? null,
    yieldingToLpr: raw.yielding_to_lpr === true,
    updatedAt: raw.updated_at,
    snapshotAgeS: Math.max((serverTimeMs - Date.parse(raw.updated_at)) / 1000, 0),
    emergency: toEmergency(raw.emergency, id),
  }
}

/**
 * Fetches the active and emergency flights with the worker's status. Rejects with `ApiError` on
 * HTTP, network or data errors; one invalid record rejects the whole response.
 */
export async function getFlights(signal?: AbortSignal): Promise<FlightsSnapshot> {
  const payload = await apiGet<unknown>('/api/flights', signal)
  if (!isRecord(payload)) invalid('response is not an object')
  const { server_time: serverTime, worker_heartbeat_at: heartbeat, worker_stale: stale } = payload
  if (!isTimestamp(serverTime)) invalid('bad server_time')
  if (heartbeat !== null && heartbeat !== undefined && !isTimestamp(heartbeat)) {
    invalid('bad worker_heartbeat_at')
  }
  if (typeof stale !== 'boolean') invalid('bad worker_stale')
  if (!Array.isArray(payload.flights)) invalid('flights is not a list')

  const serverTimeMs = Date.parse(serverTime)
  const flights = payload.flights.map((item) => toFlight(item, serverTimeMs))
  if (new Set(flights.map((flight) => flight.missionId)).size !== flights.length) {
    invalid('duplicate mission ids')
  }
  return {
    serverTime,
    workerHeartbeatAt: (heartbeat as string | null | undefined) ?? null,
    workerStale: stale,
    flights,
  }
}
