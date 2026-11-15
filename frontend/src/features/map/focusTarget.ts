import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'

export type FocusKind = 'hub' | 'drone' | 'order'

/** [longitude, latitude]. */
export type FocusPosition = readonly [longitude: number, latitude: number]

/**
 * One deliberate "show me this on the map" command from a list click (Feature 023). `seq` is unique
 * per click, so clicking the same row again is a new command, while a re-render or a data refresh
 * hands the map the very same command and moves nothing.
 */
export interface FocusRequest {
  kind: FocusKind
  id: string
  position: FocusPosition
  seq: number
}

/**
 * Whether a stored coordinate pair can be flown to: two finite numbers in the valid range, and not
 * (0, 0), which is the "no position" value of a missing or defaulted location, never a real place
 * in the operating area.
 */
export function isUsableCoordinate(value: unknown): value is FocusPosition {
  if (!Array.isArray(value) || value.length !== 2) return false
  const [longitude, latitude] = value as unknown[]
  if (typeof longitude !== 'number' || typeof latitude !== 'number') return false
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return false
  if (longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) return false
  return !(longitude === 0 && latitude === 0)
}

export interface FocusData {
  hubs: readonly Hub[]
  drones: readonly Drone[]
  orders: readonly Order[]
}

export interface ResolvedFocus {
  /** What the operator clicked, for a message. */
  label: string
  /** null when the entity is unknown or its stored location cannot be used. */
  position: FocusPosition | null
}

/**
 * Where the camera should go for an entity, from the data the app already holds: a drone's latest
 * known coordinates (a docked drone is at its Hub), a Hub's coordinates, and an order's stored
 * delivery destination (never its drone, and never a geocoded address). The stored coordinates are
 * used as they are; historical orders may carry approximate ones.
 */
export function resolveFocusTarget(kind: FocusKind, id: string, data: FocusData): ResolvedFocus {
  const entity =
    kind === 'hub'
      ? data.hubs.find((hub) => hub.id === id)
      : kind === 'drone'
        ? data.drones.find((drone) => drone.id === id)
        : data.orders.find((order) => order.id === id)
  const label = kind === 'hub' && entity ? (entity as Hub).name : id
  const coordinates = entity?.coordinates
  return { label, position: isUsableCoordinate(coordinates) ? coordinates : null }
}
