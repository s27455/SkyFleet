import type { OrderSimulationStatus, OrderSimulationStatusResponse } from '../types/orderSimulation'
import { ApiError, apiGet, apiPost } from './client'

function invalid(reason: string): never {
  throw new ApiError(`Invalid order simulation data: ${reason}`)
}

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))
const isCount = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0

/** Validates one untrusted API answer and maps it to the UI model. */
export function toOrderSimulationStatus(item: unknown): OrderSimulationStatus {
  if (typeof item !== 'object' || item === null) invalid('status is not an object')
  const raw = item as Partial<Record<keyof OrderSimulationStatusResponse, unknown>>

  if (typeof raw.enabled !== 'boolean') invalid('bad enabled')
  if (typeof raw.worker_running !== 'boolean') invalid('bad worker_running')
  if (raw.last_check_at !== null && !isTimestamp(raw.last_check_at)) invalid('bad last_check_at')
  if (raw.last_outcome !== null && typeof raw.last_outcome !== 'string') invalid('bad last_outcome')
  if (!isCount(raw.outstanding_orders)) invalid('bad outstanding_orders')
  if (!isCount(raw.max_outstanding_orders)) invalid('bad max_outstanding_orders')

  return {
    enabled: raw.enabled,
    workerRunning: raw.worker_running,
    lastCheckAt: raw.last_check_at,
    lastOutcome: raw.last_outcome,
    outstandingOrders: raw.outstanding_orders,
    maxOutstandingOrders: raw.max_outstanding_orders,
  }
}

export async function getOrderSimulationStatus(
  signal?: AbortSignal,
): Promise<OrderSimulationStatus> {
  return toOrderSimulationStatus(await apiGet<unknown>('/api/orders/simulation/status', signal))
}

/** Turns automatic order generation ON; the backend refuses (503) while no worker is alive. */
export async function enableOrderSimulation(): Promise<OrderSimulationStatus> {
  return toOrderSimulationStatus(await apiPost<unknown>('/api/orders/simulation/enable'))
}

/** Turns automatic order generation OFF. Existing orders are untouched. */
export async function disableOrderSimulation(): Promise<OrderSimulationStatus> {
  return toOrderSimulationStatus(await apiPost<unknown>('/api/orders/simulation/disable'))
}
