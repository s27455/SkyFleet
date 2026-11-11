import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'

/**
 * MVP rule (approved): a drone is "docked" at a Hub when its status is not IN_FLIGHT and its stored
 * position is within this distance of the Hub. `Drone.hubId` is only the assigned/home Hub, so it
 * is deliberately not used: a drone that landed at another Hub counts there. This is a reversible
 * simplification until the simulation defines "docked" (business-rules Q8).
 */
export const DOCK_RADIUS_M = 50

const EARTH_RADIUS_M = 6_371_000
const toRadians = (degrees: number) => (degrees * Math.PI) / 180

/** Great-circle distance in metres between two [lng, lat] points. */
export function distanceMeters(a: readonly [number, number], b: readonly [number, number]) {
  const dLat = toRadians(b[1] - a[1])
  const dLng = toRadians(b[0] - a[0])
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(a[1])) * Math.cos(toRadians(b[1])) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

export interface FleetPlacement {
  /** Docked drones by Hub id, in drone-id order. Hubs with no docked drone have no entry. */
  dockedByHub: ReadonlyMap<string, readonly Drone[]>
  /**
   * Drones that get an individual map marker: every IN_FLIGHT drone, plus any non-flying drone that
   * is not at a Hub (flagged exception, so a drone is never silently hidden).
   */
  markerDrones: readonly Drone[]
}

/** The nearest Hub within the docking radius, if any. */
function hubAt(drone: Drone, hubs: readonly Hub[]): Hub | undefined {
  let nearest: Hub | undefined
  let nearestDistance = Infinity
  for (const hub of hubs) {
    const distance = distanceMeters(drone.coordinates, hub.coordinates)
    const closer =
      distance < nearestDistance || (distance === nearestDistance && hub.id < (nearest?.id ?? ''))
    if (distance <= DOCK_RADIUS_M && closer) {
      nearest = hub
      nearestDistance = distance
    }
  }
  return nearest
}

/** Display grouping only; never changes a drone or its coordinates. */
export function partitionFleet(drones: readonly Drone[], hubs: readonly Hub[]): FleetPlacement {
  const docked = new Map<string, Drone[]>()
  const markerDrones: Drone[] = []

  for (const drone of drones) {
    const hub = drone.status === 'IN_FLIGHT' ? undefined : hubAt(drone, hubs)
    if (hub) docked.set(hub.id, [...(docked.get(hub.id) ?? []), drone])
    else markerDrones.push(drone)
  }

  const dockedByHub = new Map<string, readonly Drone[]>()
  for (const [hubId, group] of docked) {
    dockedByHub.set(
      hubId,
      [...group].sort((a, b) => a.id.localeCompare(b.id)),
    )
  }
  return { dockedByHub, markerDrones }
}
