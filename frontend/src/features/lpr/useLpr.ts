import { getLprStatus } from '../../api/incidents'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The running LPR helicopter scenario (or none), polled with the flights so it moves smoothly. */
export function useLpr() {
  return usePolledResource(getLprStatus, POLL_INTERVALS_MS.flights, { trackReceivedAt: true })
}
