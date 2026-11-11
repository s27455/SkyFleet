export const DRONE_STATUSES = ['IDLE', 'IN_FLIGHT', 'CHARGING', 'MAINTENANCE'] as const

/** Operational states stored by the backend (a snapshot, not live telemetry). */
export type DroneStatus = (typeof DRONE_STATUSES)[number]

/** Mirrors `DroneModelResponse` in backend/app/drones/schemas.py (snake_case JSON). */
export interface DroneModelResponse {
  id: string
  name: string
  airframe_type: string
  max_payload_kg: number
  max_range_km: number
  recommended_mission_range_km: number
  cruise_speed_kmh: number
  max_speed_kmh: number
  nominal_flight_time_min: number
  min_battery_reserve_pct: number
  charge_to_80_minutes: number
  max_wind_mps: number
  empty_weight_kg: number
}

/** Mirrors `DroneResponse` in backend/app/drones/schemas.py (`GET /api/drones`). */
export interface DroneResponse {
  id: string
  hub_id: string
  status: DroneStatus
  battery_pct: number
  longitude: number
  latitude: number
  model: DroneModelResponse
}

/** The subset of model capabilities shown in the UI. Values are simulation assumptions. */
export interface DroneModel {
  id: string
  name: string
  maxPayloadKg: number
  /** Nominal upper bound on total distance per charge, not a delivery radius. */
  maxRangeKm: number
  /** Conservative total mission distance including the return to a Hub. */
  recommendedMissionRangeKm: number
  cruiseSpeedKmh: number
  nominalFlightTimeMin: number
  minBatteryReservePct: number
}

/** One drone unit as last stored by the backend. */
export interface Drone {
  id: string
  /** Assigned/home Hub id (see `Hub.id`). */
  hubId: string
  status: DroneStatus
  batteryPct: number
  /** The real stored position as [lng, lat]; never altered for display. */
  coordinates: [number, number]
  model: DroneModel
}
