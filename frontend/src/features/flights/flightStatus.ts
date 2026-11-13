import type { StatusTone } from '../../components/ui/StatusIndicator'
import type { EmergencyReason, Flight, FlightPhase } from '../../types/flight'

export const FLIGHT_PHASE_DISPLAY: Record<FlightPhase, { tone: StatusTone; label: string }> = {
  OUTBOUND: { tone: 'ok', label: 'Outbound with the parcel' },
  DELIVERING: { tone: 'ok', label: 'Delivering the parcel' },
  RETURNING: { tone: 'ok', label: 'Returning to a Hub' },
  DIVERTING: { tone: 'warning', label: 'Diverting to another Hub' },
  LANDED: { tone: 'neutral', label: 'Landed' },
  EMERGENCY_APPROACH: { tone: 'critical', label: 'Emergency landing: drone failure' },
  EMERGENCY: { tone: 'critical', label: 'Emergency' },
}

export const EMERGENCY_REASON_TEXT: Record<EmergencyReason, string> = {
  NO_HUB_WITH_CAPACITY: 'every Hub it could reach was full',
  BATTERY_INSUFFICIENT: 'no other Hub was within reach of its battery',
  BATTERY_CRITICAL: 'its battery fell below the critical level',
  DRONE_FAILURE: 'a simulated drone failure',
}

/** Phases in which the drone is moving and a marker can be animated. */
const MOVING_PHASES: readonly string[] = [
  'OUTBOUND',
  'DELIVERING',
  'RETURNING',
  'DIVERTING',
  'EMERGENCY_APPROACH',
]

/** Flights a drone failure can still interrupt (the backend decides; this only enables the control). */
const FAILABLE_PHASES: readonly string[] = ['OUTBOUND', 'DELIVERING', 'RETURNING', 'DIVERTING']

export const isFailable = (flight: Flight) =>
  flight.failedAt === null &&
  flight.missionStatus === 'IN_FLIGHT' &&
  FAILABLE_PHASES.includes(flight.phase)

export const isActiveFlight = (flight: Flight) => MOVING_PHASES.includes(flight.phase)

/**
 * Whether flying markers may glide between snapshots. They must not when the user prefers reduced
 * motion, when the worker stopped updating, or when the latest refresh failed: the data on screen
 * is then the last known and must not be moved on its own.
 */
export function canAnimateFlights(conditions: {
  reducedMotion: boolean
  workerStale: boolean
  refreshFailed: boolean
}) {
  return !conditions.reducedMotion && !conditions.workerStale && !conditions.refreshFailed
}

/** One flight per drone; an active flight wins over an older one that ended in an emergency. */
export function flightsByDrone(flights: readonly Flight[]): Map<string, Flight> {
  const byDrone = new Map<string, Flight>()
  for (const flight of flights) {
    const known = byDrone.get(flight.droneId)
    if (known === undefined || (isActiveFlight(flight) && !isActiveFlight(known))) {
      byDrone.set(flight.droneId, flight)
    }
  }
  return byDrone
}
