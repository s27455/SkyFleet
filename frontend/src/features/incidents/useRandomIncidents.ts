import { getRandomIncidents } from '../../api/randomIncidents'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/**
 * The server-reported Random Incidents state, re-read regularly. Call it once (in `App`) and pass
 * the resource down, so the Scenarios menu never adds a second poll.
 */
export function useRandomIncidents() {
  return usePolledResource(getRandomIncidents, POLL_INTERVALS_MS.fleet)
}
