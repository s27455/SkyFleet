import type { DroneModelResponse, DroneResponse } from '../types/drone'
import { HUB_RESPONSES } from './hubFixtures'

/** The seeded SF-1 Courier as `GET /api/drones` nests it. Test data only. */
export const SF1_MODEL_RESPONSE: DroneModelResponse = {
  id: 'SF-1',
  name: 'SkyFleet SF-1 Courier',
  airframe_type: 'hexacopter',
  max_payload_kg: 3.0,
  max_range_km: 20.0,
  recommended_mission_range_km: 14.0,
  cruise_speed_kmh: 45.0,
  max_speed_kmh: 60.0,
  nominal_flight_time_min: 32,
  min_battery_reserve_pct: 20,
  charge_to_80_minutes: 45,
  max_wind_mps: 10.0,
  empty_weight_kg: 9.0,
}

const BATTERY_LEVELS = [100, 90, 80]

/** The 12 seeded drones (DRN-001..012, three per Hub at the Hub's coordinates), ordered by id. */
export const DRONE_RESPONSES: DroneResponse[] = HUB_RESPONSES.flatMap((hub, hubIndex) =>
  BATTERY_LEVELS.map((battery, slot) => ({
    id: `DRN-${String(hubIndex * BATTERY_LEVELS.length + slot + 1).padStart(3, '0')}`,
    hub_id: hub.id,
    status: 'IDLE' as const,
    battery_pct: battery,
    longitude: hub.longitude,
    latitude: hub.latitude,
    model: SF1_MODEL_RESPONSE,
  })),
)
