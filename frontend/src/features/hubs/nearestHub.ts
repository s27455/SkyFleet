import type { Hub } from '../../types/hub'
import { distanceMeters } from '../map/fleetPlacement'

export interface NearestHub {
  hub: Hub
  distanceM: number
}

const isCoordinate = (value: unknown): value is number => Number.isFinite(value)

/**
 * The Hub geographically closest to a [lng, lat] position (great-circle distance; a tie goes to the
 * lower Hub id, as in the backend). It is pure proximity: it says nothing about the drone's
 * assigned Hub, its mission, or whether the Hub is reachable or has room. Returns null when there
 * is no Hub or the position is unusable.
 */
export function nearestHub(
  position: readonly [number, number],
  hubs: readonly Hub[],
): NearestHub | null {
  if (!isCoordinate(position[0]) || !isCoordinate(position[1])) return null
  let best: NearestHub | null = null
  for (const hub of hubs) {
    if (!isCoordinate(hub.coordinates[0]) || !isCoordinate(hub.coordinates[1])) continue
    const distanceM = distanceMeters(position, hub.coordinates)
    if (
      best === null ||
      distanceM < best.distanceM ||
      (distanceM === best.distanceM && hub.id < best.hub.id)
    ) {
      best = { hub, distanceM }
    }
  }
  return best
}

/** "Forum Gdańsk · 1.4 km" (metres below one kilometre), or "—" when it cannot be determined. */
export function describeNearestHub(position: readonly [number, number], hubs: readonly Hub[]) {
  const nearest = nearestHub(position, hubs)
  if (nearest === null) return '—'
  const distance =
    nearest.distanceM < 1000
      ? `${Math.round(nearest.distanceM)} m`
      : `${(nearest.distanceM / 1000).toFixed(1)} km`
  return `${nearest.hub.name} · ${distance}`
}
