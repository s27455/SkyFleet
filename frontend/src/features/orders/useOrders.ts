import { getOrders } from '../../api/orders'
import { useApiResource } from '../data/useApiResource'

/** Loads the order snapshot once, with a retry. No polling and no mock fallback. */
export function useOrders() {
  return useApiResource(getOrders)
}
