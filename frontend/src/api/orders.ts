import { ORDER_STATUSES, type Order, type OrderResponse } from '../types/order'
import { ApiError, apiDelete, apiGet, apiPost, apiSend } from './client'
import { isFiniteNumberInRange, isNonEmptyString, isPositiveFiniteNumber } from './validation'

function invalid(reason: string): never {
  throw new ApiError(`Invalid order data: ${reason}`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

// The backend sends timezone-aware timestamps. Requiring a zone designator keeps a naive value from
// being read as local time and then shown with a "UTC" label.
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

/** Validates one untrusted API item and maps it to the UI model. */
export function toOrder(item: unknown): Order {
  if (!isRecord(item)) invalid('order is not an object')
  const raw = item as Partial<Record<keyof OrderResponse, unknown>>

  const {
    id,
    origin_hub_id: originHubId,
    destination_address: address,
    destination_longitude: longitude,
    destination_latitude: latitude,
    package_weight_kg: weight,
    status,
    delivered_at: deliveredAt = null,
    cancelled_at: cancelledAt = null,
    delivery_failed_at: deliveryFailedAt = null,
    created_at: createdAt,
    updated_at: updatedAt,
  } = raw
  if (!isNonEmptyString(id)) invalid('missing id')
  if (!isNonEmptyString(originHubId)) invalid(`missing origin_hub_id for ${id}`)
  if (!isNonEmptyString(address) || address.trim() === '') {
    invalid(`missing destination_address for ${id}`)
  }
  if (!isFiniteNumberInRange(longitude, -180, 180)) invalid(`bad destination_longitude for ${id}`)
  if (!isFiniteNumberInRange(latitude, -90, 90)) invalid(`bad destination_latitude for ${id}`)
  if (!isPositiveFiniteNumber(weight)) invalid(`bad package_weight_kg for ${id}`)
  if (typeof status !== 'string' || !(ORDER_STATUSES as readonly string[]).includes(status)) {
    invalid(`unknown status for ${id}`)
  }
  if (deliveredAt !== null && !isTimestamp(deliveredAt)) invalid(`bad delivered_at for ${id}`)
  if (cancelledAt !== null && !isTimestamp(cancelledAt)) invalid(`bad cancelled_at for ${id}`)
  if (deliveryFailedAt !== null && !isTimestamp(deliveryFailedAt)) {
    invalid(`bad delivery_failed_at for ${id}`)
  }
  if (!isTimestamp(createdAt)) invalid(`bad created_at for ${id}`)
  if (!isTimestamp(updatedAt)) invalid(`bad updated_at for ${id}`)

  return {
    id,
    originHubId,
    destinationAddress: address,
    coordinates: [longitude, latitude],
    packageWeightKg: weight,
    status: status as Order['status'],
    deliveredAt,
    cancelledAt,
    deliveryFailedAt,
    createdAt,
    updatedAt,
  }
}

async function readOrders(path: string, signal?: AbortSignal): Promise<Order[]> {
  const payload = await apiGet<unknown>(path, signal)
  if (!Array.isArray(payload)) invalid('response is not a list')

  const orders = payload.map(toOrder)
  if (new Set(orders.map((order) => order.id)).size !== orders.length)
    invalid('duplicate order ids')
  return orders
}

/** Fetches every order, the full history. Rejects with `ApiError` on HTTP, network or data errors. */
export function getOrders(signal?: AbortSignal): Promise<Order[]> {
  return readOrders('/api/orders', signal)
}

/**
 * Fetches the orders for the active operational views (Feature 017A). The backend decides which
 * delivered orders have expired, from their stored delivery time and its own clock, so the client
 * clock is never involved. The map, the lists and the counters all use this one answer.
 */
export function getActiveOrders(signal?: AbortSignal): Promise<Order[]> {
  return readOrders('/api/orders?active=true', signal)
}

/**
 * Fields the administrator provides for an order (Feature 012 `POST /api/orders`). Without
 * `originHubId` the backend picks the nearest Hub that can serve the destination (Feature 021D);
 * the edit form can still name one.
 */
export interface OrderInput {
  originHubId?: string
  destinationAddress: string
  longitude: number
  latitude: number
  packageWeightKg: number
}

const toOrderBody = (input: Partial<OrderInput>) => ({
  origin_hub_id: input.originHubId,
  destination_address: input.destinationAddress,
  destination_longitude: input.longitude,
  destination_latitude: input.latitude,
  package_weight_kg: input.packageWeightKg,
})

/** Creates an order; the backend assigns the id, the status and (if none is given) the origin Hub. */
export async function createOrder(input: OrderInput): Promise<Order> {
  return toOrder(await apiSend<unknown>('POST', '/api/orders', toOrderBody(input)))
}

/**
 * Asks the backend to generate exactly one simulated order (`POST /api/orders/generate`, no body).
 * The route and weight are chosen by the backend; it works whatever the automatic mode is.
 */
export async function generateOrder(): Promise<Order> {
  return toOrder(await apiPost<unknown>('/api/orders/generate'))
}

/** Updates only the given fields (`PATCH`); the backend rejects ineligible orders with 409. */
export async function updateOrder(orderId: string, changes: Partial<OrderInput>): Promise<Order> {
  const body = Object.fromEntries(
    Object.entries(toOrderBody(changes)).filter(([, value]) => value !== undefined),
  )
  return toOrder(
    await apiSend<unknown>('PATCH', `/api/orders/${encodeURIComponent(orderId)}`, body),
  )
}

/**
 * Cancels an order (`POST /api/orders/{id}/cancel`, no body). The backend decides: a flying drone
 * that has not handed over the parcel is recalled with it; a delivered order is refused (409).
 * Cancelling an already cancelled order is harmless and returns it unchanged.
 */
export async function cancelOrder(orderId: string): Promise<Order> {
  return toOrder(await apiPost<unknown>(`/api/orders/${encodeURIComponent(orderId)}/cancel`))
}

/** Physically deletes an order; the backend refuses it when any mission references the order. */
export function deleteOrder(orderId: string): Promise<void> {
  return apiDelete(`/api/orders/${encodeURIComponent(orderId)}`)
}
