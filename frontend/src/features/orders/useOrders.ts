import { getActiveOrders, getRecentOrders } from '../../api/orders'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/**
 * Loads the orders of the active operational views and keeps them fresh (statuses change at
 * takeoff and at delivery; a delivered order drops out when its visibility window ends).
 */
export function useOrders() {
  return usePolledResource(getActiveOrders, POLL_INTERVALS_MS.fleet)
}

/** The most recent orders of the history; only mounted while the operator asks for all orders. */
export function useAllOrders() {
  return usePolledResource(getRecentOrders, POLL_INTERVALS_MS.fleet)
}
