import { getDrones } from '../../api/drones'
import { useApiResource } from '../data/useApiResource'

/** Loads the drone fleet snapshot once, with a retry. No polling and no mock fallback. */
export function useDrones() {
  return useApiResource(getDrones)
}
