import { getDrones } from '../../api/drones'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** Loads the drone fleet and keeps it fresh (a flying drone's snapshot changes every tick). */
export function useDrones() {
  return usePolledResource(getDrones, POLL_INTERVALS_MS.fleet)
}
