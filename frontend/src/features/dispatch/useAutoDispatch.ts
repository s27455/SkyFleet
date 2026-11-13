import { getAutoDispatchStatus } from '../../api/dispatch'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The server-reported automatic dispatch mode, re-read regularly so a page refresh is not needed. */
export function useAutoDispatch() {
  return usePolledResource(getAutoDispatchStatus, POLL_INTERVALS_MS.fleet)
}
