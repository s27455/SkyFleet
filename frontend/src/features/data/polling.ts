/**
 * How often the live resources are re-read (milliseconds); `null` disables polling, so the
 * resource is read once. The object is mutable so tests can switch polling off globally.
 */
export const POLL_INTERVALS_MS: { flights: number | null; fleet: number | null } = {
  // Flight snapshots are written by the worker about once a second.
  flights: 1000,
  // Drones, orders and missions change at takeoff, delivery and landing.
  fleet: 2000,
}

/**
 * How long one read may take before it counts as a failure. Without it a stalled connection would
 * freeze the live data without any notice. Mutable so tests can shorten it.
 */
export const REQUEST_TIMEOUT_MS = { value: 10_000 }
