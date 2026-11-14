import {
  EVENT_ORIGINS,
  EVENT_TYPES,
  type EventOrigin,
  type EventResponse,
  type EventType,
  type OperationalEvent,
} from '../types/event'
import { ApiError, apiGet } from './client'

function invalid(reason: string): never {
  throw new ApiError(`Invalid event data: ${reason}`)
}

// The backend states UTC explicitly; a naive value would be read as local time and mislabelled.
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

const nullableString = (value: unknown, name: string, id: unknown): string | null => {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') invalid(`bad ${name} for event ${String(id)}`)
  return value
}

/** Validates one untrusted API item and maps it to the UI model. */
export function toEvent(item: unknown): OperationalEvent {
  if (typeof item !== 'object' || item === null) invalid('event is not an object')
  const raw = item as Partial<Record<keyof EventResponse, unknown>>
  const { id, event_type: type, occurred_at: occurredAt, origin } = raw

  if (typeof id !== 'number' || !Number.isInteger(id)) invalid('missing id')
  if (typeof type !== 'string' || !(EVENT_TYPES as readonly string[]).includes(type)) {
    invalid(`unknown event_type for event ${id}`)
  }
  if (!isTimestamp(occurredAt)) invalid(`bad occurred_at for event ${id}`)
  if (typeof origin !== 'string' || !(EVENT_ORIGINS as readonly string[]).includes(origin)) {
    invalid(`unknown origin for event ${id}`)
  }

  return {
    id,
    type: type as EventType,
    occurredAt,
    origin: origin as EventOrigin,
    orderId: nullableString(raw.order_id, 'order_id', id),
    missionId: nullableString(raw.mission_id, 'mission_id', id),
    droneId: nullableString(raw.drone_id, 'drone_id', id),
    reason: nullableString(raw.reason, 'reason', id),
  }
}

/**
 * Fetches one order's events, oldest first (bounded by the backend's default limit). Rejects with
 * `ApiError` on HTTP, network or data errors; an order without events is an empty list.
 */
export async function getOrderEvents(
  orderId: string,
  signal?: AbortSignal,
): Promise<OperationalEvent[]> {
  return getEvents(`order_id=${encodeURIComponent(orderId)}`, signal)
}

/** One drone's events, oldest first: the Activity of a drone, a relocation included (Feature 019A). */
export async function getDroneEvents(
  droneId: string,
  signal?: AbortSignal,
): Promise<OperationalEvent[]> {
  return getEvents(`drone_id=${encodeURIComponent(droneId)}`, signal)
}

async function getEvents(query: string, signal?: AbortSignal): Promise<OperationalEvent[]> {
  const payload = await apiGet<unknown>(`/api/events?${query}`, signal)
  if (!Array.isArray(payload)) invalid('response is not a list')
  return payload.map(toEvent)
}
