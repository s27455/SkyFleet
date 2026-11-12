import { getFlights } from '../../api/flights'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The active and emergency flights with the worker's status, polled about once a second. */
export function useFlights() {
  // The arrival time is what lets the map glide between snapshots.
  return usePolledResource(getFlights, POLL_INTERVALS_MS.flights, { trackReceivedAt: true })
}
