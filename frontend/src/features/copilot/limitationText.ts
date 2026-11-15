/**
 * Plain words for the fixed limitation codes of a fleet snapshot.
 *
 * Only the code (the part before a colon) selects the text; a trailing detail (a Hub id, a count)
 * is shown as text after it. An unknown code gets a generic line and its code is shown as text, so
 * nothing the server sends can change what the operator reads beyond that.
 */
const TEXTS: Record<string, string> = {
  WORKER_NOT_RUNNING:
    'The simulation worker is not running, so positions and battery levels are not updating.',
  HUB_OVER_CAPACITY: 'More drones are counted at this Hub than its capacity allows',
  FLIGHT_STATUS_MISMATCH: 'The drones in flight do not match the active flights.',
  UNKNOWN_DRONE_STATUS: 'A drone has a status this view does not know; it is counted as "other".',
  UNKNOWN_ORDER_STATUS: 'An order has a status this view does not know; it is counted as "other".',
  TEXT_SANITIZED: 'A name or id contained unsafe characters and was cleaned.',
  DRONES_OMITTED: 'Drones are not in the snapshot (the count follows)',
  HUBS_OMITTED: 'Hubs are not in the snapshot (the count follows)',
  ACTIVE_INCIDENTS_OMITTED: 'Active incidents are not in the snapshot (the count follows)',
  RECOVERED_ALERTS_OMITTED: 'Recovered alerts are not in the snapshot (the count follows)',
}

export function describeLimitation(code: string): string {
  const [name, ...rest] = code.split(':')
  const detail = rest.join(':')
  const text = TEXTS[name]
  if (text === undefined) return `Unrecognised limitation: ${code}`
  return detail === '' ? text : `${text}: ${detail}`
}
