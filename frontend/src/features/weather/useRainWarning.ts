import { getRainWarning } from '../../api/incidents'
import { POLL_INTERVALS_MS } from '../data/polling'
import { usePolledResource } from '../data/usePolledResource'

/** The global rain warning, polled with the other fleet data (no WebSockets). */
export function useRainWarning() {
  return usePolledResource(getRainWarning, POLL_INTERVALS_MS.fleet)
}
