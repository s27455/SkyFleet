/** Event codes the backend can store (Feature 018A). Only ORDER_CREATED is emitted so far. */
export const EVENT_TYPES = [
  'ORDER_CREATED',
  'ORDER_CANCELLED',
  'DRONE_FAILURE',
  'RECIPIENT_UNAVAILABLE',
  'LPR_TRANSIT',
  'DRONE_RELOCATION',
] as const

export type EventType = (typeof EVENT_TYPES)[number]

export const EVENT_ORIGINS = ['SYSTEM', 'AUTOMATIC', 'MANUAL'] as const

export type EventOrigin = (typeof EVENT_ORIGINS)[number]

/** Mirrors `EventResponse` in backend/app/events/schemas.py (`GET /api/events`). */
export interface EventResponse {
  id: number
  event_type: EventType
  /** Real UTC time of the transition, not a simulated flight instant. */
  occurred_at: string
  origin: EventOrigin
  order_id: string | null
  mission_id: string | null
  flight_id: string | null
  drone_id: string | null
  reason: string | null
  details: Record<string, unknown> | null
}

/** UI model of one operational event. */
export interface OperationalEvent {
  id: number
  type: EventType
  occurredAt: string
  origin: EventOrigin
  orderId: string | null
  missionId: string | null
  droneId: string | null
  reason: string | null
}
