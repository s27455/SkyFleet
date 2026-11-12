export const MISSION_STATUSES = [
  'ASSIGNED',
  'IN_FLIGHT',
  'CANCELLED',
  'COMPLETED',
  'EMERGENCY',
] as const

export type MissionStatus = (typeof MISSION_STATUSES)[number]

/** The fields of `MissionResponse` (backend/app/missions/schemas.py) that the UI uses. */
export interface MissionResponse {
  id: string
  order_id: string
  drone_id: string
  origin_hub_id: string
  return_hub_id: string
  status: MissionStatus
  total_km: number
}

/** UI model. A mission claims an order and a drone; this UI only starts `ASSIGNED` ones. */
export interface Mission {
  id: string
  orderId: string
  droneId: string
  originHubId: string
  /** The planned return Hub: planned at confirmation, neither guaranteed nor reserved. */
  returnHubId: string
  status: MissionStatus
  totalKm: number
}
