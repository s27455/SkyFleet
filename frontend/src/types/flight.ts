export const FLIGHT_PHASES = [
  'OUTBOUND',
  'DELIVERING',
  'RETURNING',
  'DIVERTING',
  'LANDED',
  'EMERGENCY',
] as const

export type FlightPhase = (typeof FLIGHT_PHASES)[number]

export const EMERGENCY_REASONS = [
  'NO_HUB_WITH_CAPACITY',
  'BATTERY_INSUFFICIENT',
  'BATTERY_CRITICAL',
] as const

export type EmergencyReason = (typeof EMERGENCY_REASONS)[number]

/** Mirrors `FlightResponse` in backend/app/simulation/schemas.py (snake_case JSON). */
export interface FlightResponse {
  mission_id: string
  order_id: string
  drone_id: string
  mission_status: string
  phase: FlightPhase
  progress: number
  position: [number, number]
  battery_pct: number
  battery_exact_pct: number
  target: { position: [number, number]; eta_s: number } | null
  origin_hub_id: string
  planned_return_hub_id: string
  landing_target_hub_id: string
  started_at: string
  delivered_at: string | null
  /** Set when the order was cancelled in flight and the drone is recalled with its parcel. */
  recalled_at: string | null
  updated_at: string
  emergency: { reason: EmergencyReason; at: string; position: [number, number] } | null
}

/** Mirrors `FlightsResponse` (`GET /api/flights`). */
export interface FlightsResponse {
  server_time: string
  worker_heartbeat_at: string | null
  worker_stale: boolean
  flights: FlightResponse[]
}

/** The backend's simulated emergency outcome. It is not a computed safe landing site. */
export interface FlightEmergency {
  reason: EmergencyReason
  at: string
  /** [longitude, latitude] where the simulated flight ended. */
  position: [longitude: number, latitude: number]
}

/** UI model of one flight, as the backend reports it at `updatedAt`. */
export interface Flight {
  missionId: string
  orderId: string
  droneId: string
  missionStatus: string
  phase: FlightPhase
  /** 0..1 of the current schedule. */
  progress: number
  /** The snapshot position at `updatedAt`: [longitude, latitude]. */
  position: [longitude: number, latitude: number]
  batteryPct: number
  /** Where the drone is heading and the simulated seconds to get there, at `updatedAt`. */
  target: { position: [longitude: number, latitude: number]; etaS: number } | null
  originHubId: string
  plannedReturnHubId: string
  landingTargetHubId: string
  startedAt: string
  deliveredAt: string | null
  /** Set when the order was cancelled in flight: the drone returns with the parcel on board. */
  recalledAt: string | null
  updatedAt: string
  /** Seconds between the snapshot and the response, both on the backend's clock. */
  snapshotAgeS: number
  emergency: FlightEmergency | null
}

export interface FlightsSnapshot {
  serverTime: string
  workerHeartbeatAt: string | null
  /** True when the worker's heartbeat is missing or old: the snapshots are no longer updated. */
  workerStale: boolean
  flights: Flight[]
}
