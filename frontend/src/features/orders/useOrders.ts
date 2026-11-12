import { getOrders } from '../../api/orders'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** Loads the orders and keeps them fresh (statuses change at takeoff and at delivery). */
export function useOrders() {
  return usePolledResource(getOrders, POLL_INTERVALS_MS.fleet)
}
