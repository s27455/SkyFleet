import { getLiveMissions } from '../../api/missions'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/**
 * Loads the live missions (assigned, flying, or ended in an emergency) and keeps them fresh. The
 * completed and cancelled history is not part of it, so the poll stays small.
 */
export function useMissions() {
  return usePolledResource(getLiveMissions, POLL_INTERVALS_MS.fleet)
}
