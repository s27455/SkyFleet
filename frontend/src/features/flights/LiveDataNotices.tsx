import { useId, useState, useSyncExternalStore } from 'react'

import type { PolledResource } from '../data/usePolledResource'
import type { Flight, FlightsSnapshot } from '../../types/flight'
import type { Mission } from '../../types/mission'
import { EMERGENCY_REASON_TEXT, isActiveFlight } from './flightStatus'

const NOTICE_CLASS =
  'rounded-lg border border-line bg-surface p-2 text-xs text-fg-muted shadow-lg sm:p-3 sm:text-sm'
const RETRY_CLASS =
  'mt-2 inline-flex min-h-10 items-center rounded-md border border-line px-3 text-fg hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent'

/** Emergency alerts stay until a later feature resolves them, so only a few rows are listed. */
export const MAX_EMERGENCY_ALERTS = 3
/** Fewer rows on a phone, where an alert stack would cover much of the map. */
export const MAX_EMERGENCY_ALERTS_NARROW = 2

const NARROW_QUERY = '(max-width: 639px)'
const subscribeNarrow = (notify: () => void) => {
  if (typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia(NARROW_QUERY)
  query.addEventListener('change', notify)
  return () => query.removeEventListener('change', notify)
}
const isNarrow = () =>
  typeof window.matchMedia === 'function' && window.matchMedia(NARROW_QUERY).matches

/** One compact emergency: a single line, with the details behind a keyboard-reachable toggle. */
function EmergencyRow({ flight }: { flight: Flight }) {
  const [open, setOpen] = useState(false)
  const detailsId = useId()
  return (
    <div
      role="alert"
      className="rounded-lg border border-line bg-surface px-3 py-1.5 text-xs shadow-lg sm:text-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate font-medium text-fg">
          Simulated emergency: {flight.droneId} ({flight.missionId})
        </p>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={detailsId}
          aria-label={`${open ? 'Hide' : 'Show'} details for ${flight.droneId}`}
          onClick={() => setOpen((value) => !value)}
          className="inline-flex min-h-10 shrink-0 items-center rounded-md px-2 text-fg-muted hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
        >
          {open ? 'Hide' : 'Details'}
        </button>
      </div>
      {open && (
        <p id={detailsId} className="pb-1 text-fg-muted">
          {flight.emergency ? EMERGENCY_REASON_TEXT[flight.emergency.reason] : ''}. The drone is out
          of service (maintenance) at {flight.position[1].toFixed(5)},{' '}
          {flight.position[0].toFixed(5)}; the parcel was already delivered. This is a simulation
          outcome and needs an operator.
        </p>
      )}
    </div>
  )
}

interface LiveDataNoticesProps {
  flights: PolledResource<FlightsSnapshot>
  missions: PolledResource<Mission[]>
  /** True when drones or orders could not be refreshed and older data is still shown. */
  fleetStale?: boolean
  onRefreshFleet?: () => void
}

/**
 * Operator notices for the live simulation: simulated emergencies, a worker that stopped updating
 * flights, flight or mission data that cannot be read. Nothing is shown while all is well, and
 * flight positions are never invented: markers stay at the last known point.
 */
export function LiveDataNotices({
  flights,
  missions,
  fleetStale = false,
  onRefreshFleet,
}: LiveDataNoticesProps) {
  const snapshot = flights.state.status === 'ready' ? flights.state.data : null
  const emergencies = snapshot?.flights.filter((flight) => flight.emergency) ?? []
  const flying = snapshot?.flights.some(isActiveFlight) ?? false
  const narrow = useSyncExternalStore(subscribeNarrow, isNarrow, () => false)
  const shown = narrow ? MAX_EMERGENCY_ALERTS_NARROW : MAX_EMERGENCY_ALERTS

  return (
    <>
      {emergencies.slice(0, shown).map((flight) => (
        <EmergencyRow key={flight.missionId} flight={flight} />
      ))}

      {emergencies.length > shown && (
        <div role="alert" className={NOTICE_CLASS}>
          {emergencies.length - shown} more simulated emergencies are not listed here; each affected
          drone is out of service and shows its alert in its panel.
        </div>
      )}

      {flights.state.status === 'error' && (
        <div role="alert" className={NOTICE_CLASS}>
          <p className="font-medium text-fg">Live flight data is unavailable</p>
          <p className="mt-1">The backend could not be reached or returned invalid flight data.</p>
          <button
            type="button"
            onClick={flights.retry}
            aria-label="Retry loading flights"
            className={RETRY_CLASS}
          >
            Retry
          </button>
        </div>
      )}

      {flights.state.status === 'ready' && flights.stale && (
        <div role="status" className={NOTICE_CLASS}>
          Live flight data could not be refreshed; drones stay at their last known positions.
          <button
            type="button"
            onClick={flights.refresh}
            aria-label="Refresh flights"
            className={`${RETRY_CLASS} ml-2`}
          >
            Refresh
          </button>
        </div>
      )}

      {fleetStale && (
        <div role="status" className={NOTICE_CLASS}>
          Drone or order data could not be refreshed; the last known data is shown.
          {onRefreshFleet && (
            <button
              type="button"
              onClick={onRefreshFleet}
              aria-label="Refresh fleet data"
              className={`${RETRY_CLASS} ml-2`}
            >
              Refresh
            </button>
          )}
        </div>
      )}

      {snapshot?.workerStale && flying && !flights.stale && (
        <div role="status" className={NOTICE_CLASS}>
          The simulation worker has stopped updating flights; positions shown are the last known
          ones.
        </div>
      )}

      {missions.state.status === 'error' && (
        <div role="status" className={NOTICE_CLASS}>
          Mission data is unavailable, so assigned missions cannot be started from here.
          <button
            type="button"
            onClick={missions.retry}
            aria-label="Retry loading missions"
            className={`${RETRY_CLASS} ml-2`}
          >
            Retry
          </button>
        </div>
      )}
    </>
  )
}
