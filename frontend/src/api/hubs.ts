import type { Hub, HubResponse } from '../types/hub'
import { ApiError, apiGet } from './client'

function invalid(reason: string): never {
  throw new ApiError(`Invalid hub data: ${reason}`)
}

function isFiniteNumberInRange(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
}

/** Validates one untrusted API item and maps it to the UI model. */
function toHub(item: unknown): Hub {
  if (typeof item !== 'object' || item === null) invalid('hub is not an object')
  const raw = item as Partial<Record<keyof HubResponse, unknown>>

  const { id, name, address, longitude, latitude, drone_capacity: droneCapacity } = raw
  if (typeof id !== 'string' || id === '') invalid('missing id')
  if (typeof name !== 'string' || name === '') invalid(`missing name for ${id}`)
  if (typeof address !== 'string') invalid(`missing address for ${id}`)
  if (!isFiniteNumberInRange(longitude, -180, 180)) invalid(`bad longitude for ${id}`)
  if (!isFiniteNumberInRange(latitude, -90, 90)) invalid(`bad latitude for ${id}`)
  if (typeof droneCapacity !== 'number' || !Number.isInteger(droneCapacity) || droneCapacity <= 0) {
    invalid(`bad drone_capacity for ${id}`)
  }

  // Mapbox expects [longitude, latitude].
  return { id, name, address, coordinates: [longitude, latitude], droneCapacity }
}

/** Fetches all Hubs from the backend. Rejects with `ApiError` on HTTP, network or data errors. */
export async function getHubs(signal?: AbortSignal): Promise<Hub[]> {
  const payload = await apiGet<unknown>('/api/hubs', signal)
  if (!Array.isArray(payload)) invalid('response is not a list')

  const hubs = payload.map(toHub)
  if (new Set(hubs.map((hub) => hub.id)).size !== hubs.length) invalid('duplicate hub ids')
  return hubs
}
