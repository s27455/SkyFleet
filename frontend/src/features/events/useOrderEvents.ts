import { useCallback } from 'react'

import { getDroneEvents, getOrderEvents } from '../../api/events'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The events of one order, re-read with the other operational data while the panel is open. */
export function useOrderEvents(orderId: string) {
  const load = useCallback((signal: AbortSignal) => getOrderEvents(orderId, signal), [orderId])
  return usePolledResource(load, POLL_INTERVALS_MS.fleet)
}

/** The events of one drone (Feature 019A), re-read like the order's. */
export function useDroneEvents(droneId: string) {
  const load = useCallback((signal: AbortSignal) => getDroneEvents(droneId, signal), [droneId])
  return usePolledResource(load, POLL_INTERVALS_MS.fleet)
}
