import { DRONE_STATUSES, type Drone, type DroneModel, type DroneResponse } from '../types/drone'
import type { DroneModelResponse } from '../types/drone'
import { ApiError, apiGet } from './client'
import { isFiniteNumberInRange, isNonEmptyString, isPositiveFiniteNumber } from './validation'

function invalid(reason: string): never {
  throw new ApiError(`Invalid drone data: ${reason}`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toDroneModel(item: unknown, droneId: string): DroneModel {
  if (!isRecord(item)) invalid(`missing model for ${droneId}`)
  const raw = item as Partial<Record<keyof DroneModelResponse, unknown>>

  if (!isNonEmptyString(raw.id)) invalid(`missing model id for ${droneId}`)
  if (!isNonEmptyString(raw.name)) invalid(`missing model name for ${droneId}`)
  if (!isPositiveFiniteNumber(raw.max_payload_kg)) invalid(`bad max_payload_kg for ${droneId}`)
  if (!isPositiveFiniteNumber(raw.max_range_km)) invalid(`bad max_range_km for ${droneId}`)
  if (!isPositiveFiniteNumber(raw.recommended_mission_range_km)) {
    invalid(`bad recommended_mission_range_km for ${droneId}`)
  }
  if (!isPositiveFiniteNumber(raw.cruise_speed_kmh)) invalid(`bad cruise_speed_kmh for ${droneId}`)
  if (!isPositiveFiniteNumber(raw.nominal_flight_time_min)) {
    invalid(`bad nominal_flight_time_min for ${droneId}`)
  }
  if (!isFiniteNumberInRange(raw.min_battery_reserve_pct, 0, 100)) {
    invalid(`bad min_battery_reserve_pct for ${droneId}`)
  }

  return {
    id: raw.id,
    name: raw.name,
    maxPayloadKg: raw.max_payload_kg,
    maxRangeKm: raw.max_range_km,
    recommendedMissionRangeKm: raw.recommended_mission_range_km,
    cruiseSpeedKmh: raw.cruise_speed_kmh,
    nominalFlightTimeMin: raw.nominal_flight_time_min,
    minBatteryReservePct: raw.min_battery_reserve_pct,
  }
}

/** Validates one untrusted API item and maps it to the UI model. */
function toDrone(item: unknown): Drone {
  if (!isRecord(item)) invalid('drone is not an object')
  const raw = item as Partial<Record<keyof DroneResponse, unknown>>

  const { id, hub_id: hubId, status, battery_pct: batteryPct, longitude, latitude } = raw
  if (!isNonEmptyString(id)) invalid('missing id')
  if (!isNonEmptyString(hubId)) invalid(`missing hub_id for ${id}`)
  if (typeof status !== 'string' || !(DRONE_STATUSES as readonly string[]).includes(status)) {
    invalid(`unknown status for ${id}`)
  }
  if (!isFiniteNumberInRange(batteryPct, 0, 100) || !Number.isInteger(batteryPct)) {
    invalid(`bad battery_pct for ${id}`)
  }
  if (!isFiniteNumberInRange(longitude, -180, 180)) invalid(`bad longitude for ${id}`)
  if (!isFiniteNumberInRange(latitude, -90, 90)) invalid(`bad latitude for ${id}`)

  return {
    id,
    hubId,
    status: status as Drone['status'],
    batteryPct,
    // Mapbox expects [longitude, latitude]. These are the real stored values.
    coordinates: [longitude, latitude],
    model: toDroneModel(raw.model, id),
  }
}

/** Fetches all drones from the backend. Rejects with `ApiError` on HTTP, network or data errors. */
export async function getDrones(signal?: AbortSignal): Promise<Drone[]> {
  const payload = await apiGet<unknown>('/api/drones', signal)
  if (!Array.isArray(payload)) invalid('response is not a list')

  const drones = payload.map(toDrone)
  if (new Set(drones.map((drone) => drone.id)).size !== drones.length)
    invalid('duplicate drone ids')
  return drones
}
