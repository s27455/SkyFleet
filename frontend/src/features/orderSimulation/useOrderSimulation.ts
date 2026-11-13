import { getOrderSimulationStatus } from '../../api/orderSimulation'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The server-reported Order Simulation state, re-read regularly while the panel is mounted. */
export function useOrderSimulation() {
  return usePolledResource(getOrderSimulationStatus, POLL_INTERVALS_MS.fleet)
}
