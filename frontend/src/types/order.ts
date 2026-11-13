/** Order states the backend currently allows: the initial states plus the two delivery states. */
export const ORDER_STATUSES = [
  'CREATED',
  'AWAITING_HANDOVER',
  'READY_FOR_PICKUP',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
] as const

export type OrderStatus = (typeof ORDER_STATUSES)[number]

/** Mirrors `OrderResponse` in backend/app/orders/schemas.py (`GET /api/orders`, snake_case JSON). */
export interface OrderResponse {
  id: string
  origin_hub_id: string
  destination_address: string
  destination_longitude: number
  destination_latitude: number
  package_weight_kg: number
  status: OrderStatus
  /** When the parcel was handed over; null if not delivered, or a legacy order without a time. */
  delivered_at: string | null
  created_at: string
  updated_at: string
}

/** UI model. The backend gives no drone assignment, so none is represented here. */
export interface Order {
  id: string
  originHubId: string
  destinationAddress: string
  /** Mapbox order: [longitude, latitude]. The real stored destination. */
  coordinates: [longitude: number, latitude: number]
  packageWeightKg: number
  status: OrderStatus
  /** ISO 8601 timestamps as sent by the backend (validated to parse). */
  deliveredAt: string | null
  createdAt: string
  updatedAt: string
}
