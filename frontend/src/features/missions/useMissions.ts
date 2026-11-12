import { getMissions } from '../../api/missions'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** Loads the missions (to find assigned ones) and keeps them fresh. */
export function useMissions() {
  return usePolledResource(getMissions, POLL_INTERVALS_MS.fleet)
}
