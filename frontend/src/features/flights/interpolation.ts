/** Position and target as the backend reports them at one instant (a snapshot). */
export interface FlightMotion {
  /** [longitude, latitude] at the snapshot. */
  position: readonly [number, number]
  /** Where the drone is heading, with the simulated seconds to get there at the snapshot. */
  target: { position: readonly [number, number]; etaS: number } | null
  /** Seconds between the snapshot and the response, both on the backend's clock. */
  snapshotAgeS: number
}

/** What the map needs to draw one flying drone between two authoritative snapshots. */
export interface FlightVisual {
  droneId: string
  motion: FlightMotion
  /** `performance.now()` when the snapshot arrived. */
  receivedAt: number
  /** False for reduced motion or a worker that stopped updating: the marker stays at the snapshot. */
  animate: boolean
}

const clamp01 = (value: number) => Math.min(Math.max(value, 0), 1)

/**
 * Where to draw a drone `secondsSinceReceived` after the response arrived.
 *
 * This only smooths the picture between two authoritative snapshots: it moves the marker in a
 * straight line from the snapshot position toward the backend's target, over the backend's own
 * seconds-to-target, and never past the target. It does not run the mission: phases, battery and
 * landing all come from the backend, and each new snapshot replaces whatever is drawn here.
 */
export function interpolatePosition(
  motion: FlightMotion,
  secondsSinceReceived: number,
): [number, number] {
  const { position, target } = motion
  if (target === null || target.etaS <= 0) return [position[0], position[1]]
  const flown = clamp01((motion.snapshotAgeS + Math.max(secondsSinceReceived, 0)) / target.etaS)
  return [
    position[0] + (target.position[0] - position[0]) * flown,
    position[1] + (target.position[1] - position[1]) * flown,
  ]
}
