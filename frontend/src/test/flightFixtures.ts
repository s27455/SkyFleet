import type { FlightResponse, FlightsResponse } from '../types/flight'
import type { MissionResponse } from '../types/mission'

/** A moment on the backend's clock for the flight fixtures (timezone-aware, like the API). */
export const SERVER_TIME = '2026-11-12T10:00:10Z'

/** An outbound flight of DRN-010 from Galeria Bałtycka, snapshotted one second before the response. */
export const OUTBOUND_FLIGHT: FlightResponse = {
  mission_id: 'MIS-AAAA0001',
  order_id: 'ORD-001',
  drone_id: 'DRN-010',
  mission_status: 'IN_FLIGHT',
  phase: 'OUTBOUND',
  progress: 0.25,
  position: [18.599, 54.38],
  battery_pct: 98,
  battery_exact_pct: 98.4,
  target: { position: [18.5972, 54.3768], eta_s: 10 },
  origin_hub_id: 'hub-galeria-baltycka',
  planned_return_hub_id: 'hub-galeria-baltycka',
  landing_target_hub_id: 'hub-galeria-baltycka',
  started_at: '2026-11-12T10:00:00Z',
  delivered_at: null,
  updated_at: '2026-11-12T10:00:09Z',
  emergency: null,
}

export const EMERGENCY_FLIGHT: FlightResponse = {
  ...OUTBOUND_FLIGHT,
  mission_status: 'EMERGENCY',
  phase: 'EMERGENCY',
  progress: 1,
  position: [18.6012, 54.3821],
  target: null,
  delivered_at: '2026-11-12T10:00:03Z',
  emergency: {
    reason: 'NO_HUB_WITH_CAPACITY',
    at: '2026-11-12T10:00:09Z',
    position: [18.6012, 54.3821],
  },
}

export function flightsResponse(
  flights: FlightResponse[] = [],
  overrides: Partial<FlightsResponse> = {},
): FlightsResponse {
  return {
    server_time: SERVER_TIME,
    worker_heartbeat_at: '2026-11-12T10:00:09Z',
    worker_stale: false,
    flights,
    ...overrides,
  }
}

export const ASSIGNED_MISSION: MissionResponse = {
  id: 'MIS-AAAA0001',
  order_id: 'ORD-001',
  drone_id: 'DRN-010',
  origin_hub_id: 'hub-galeria-baltycka',
  return_hub_id: 'hub-galeria-baltycka',
  status: 'ASSIGNED',
  total_km: 1.372,
}
