import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'

/** Whether a drone is still making its emergency landing, or already grounded and needs service. */
export type EmergencyLevel = 'approach' | 'grounded'

export interface EmergencyPoint {
  droneId: string
  /** null when a relocating drone failed: it served no order. */
  orderId: string | null
  level: EmergencyLevel
  /** [longitude, latitude] of the simulated emergency landing point. */
  position: readonly [number, number]
}

/**
 * Where a failed drone is landing or has landed (Feature 018C), straight from the backend's flights.
 *
 * During the approach the point is the flight's target. After the landing it is the flight's final
 * position, and it is shown only while the drone is still grounded (MAINTENANCE): once an operator
 * has taken the drone back into service the warning is gone. Nothing is invented: a flight the
 * backend did not mark as failed never produces a point.
 */
export function emergencyPoints(
  flights: readonly Flight[],
  drones: readonly Drone[],
): EmergencyPoint[] {
  const status = new Map(drones.map((drone) => [drone.id, drone.status]))
  const points: EmergencyPoint[] = []
  for (const flight of flights) {
    if (flight.failedAt === null) continue
    if (flight.phase === 'EMERGENCY_APPROACH' && flight.target) {
      points.push({
        droneId: flight.droneId,
        orderId: flight.orderId,
        level: 'approach',
        position: flight.target.position,
      })
    } else if (flight.phase === 'EMERGENCY' && status.get(flight.droneId) === 'MAINTENANCE') {
      points.push({
        droneId: flight.droneId,
        orderId: flight.orderId,
        level: 'grounded',
        position: flight.emergency?.position ?? flight.position,
      })
    }
  }
  return points
}

/** Drone id to emergency level, for the drone markers. */
export function droneEmergencies(points: readonly EmergencyPoint[]): Map<string, EmergencyLevel> {
  return new Map(points.map((point) => [point.droneId, point.level]))
}

/**
 * Orders whose delivery was interrupted by a drone failure: the parcel was not handed over, so the
 * order keeps its status (no new order status exists) and is flagged from its failed flight.
 */
export function interruptedOrderIds(flights: readonly Flight[]): Set<string> {
  return new Set(
    flights
      .filter((flight) => flight.failedAt !== null && flight.deliveredAt === null)
      .flatMap((flight) => (flight.orderId === null ? [] : [flight.orderId])),
  )
}
