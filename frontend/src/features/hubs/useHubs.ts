import { getHubs } from '../../api/hubs'
import { useApiResource } from '../data/useApiResource'

/** Loads Hubs from the backend once, with a retry for failed requests. No mock fallback. */
export function useHubs() {
  return useApiResource(getHubs)
}
