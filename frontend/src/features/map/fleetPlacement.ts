import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'

/**
 * Physical presence rule, kept identical to the backend (`app/missions/presence.py`): a drone is
 * "docked" at a Hub when its status is neither IN_FLIGHT nor MAINTENANCE and its stored position is
 * within this distance of the Hub (the nearest Hub wins, ties go to the lower id). A drone in
 * MAINTENANCE is never docked, whatever its coordinates: the simulated emergency outcome parks the
 * drone in MAINTENANCE where it stopped, and it must never count toward a Hub. `Drone.hubId` is
 * only the assigned/home Hub and is deliberately not used: a drone that landed elsewhere counts
 * there. Position and status approximate presence until docking hardware confirms it.
 */
export const DOCK_RADIUS_M = 50

/** Statuses in which a drone is never docked, whatever its position. */
const NOT_DOCKED_STATUSES: readonly string[] = ['IN_FLIGHT', 'MAINTENANCE']

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
   * Drones that get an individual map marker: every IN_FLIGHT drone, plus any other drone that is
   * not docked at a Hub, such as one in MAINTENANCE (flagged, so a drone is never silently hidden).
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
    const hub = NOT_DOCKED_STATUSES.includes(drone.status) ? undefined : hubAt(drone, hubs)
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
