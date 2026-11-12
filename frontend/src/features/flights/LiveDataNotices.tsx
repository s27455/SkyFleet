import type { PolledResource } from '../data/usePolledResource'
import type { FlightsSnapshot } from '../../types/flight'
import type { Mission } from '../../types/mission'
import { EMERGENCY_REASON_TEXT, isActiveFlight } from './flightStatus'

const NOTICE_CLASS = 'rounded-lg border border-line bg-surface p-3 text-sm text-fg-muted shadow-lg'
const RETRY_CLASS =
  'mt-2 inline-flex min-h-10 items-center rounded-md border border-line px-3 text-fg hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent'

/** Emergency alerts stay until a later feature resolves them, so only a few are listed in full. */
export const MAX_EMERGENCY_ALERTS = 3

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

  return (
    <>
      {emergencies.slice(0, MAX_EMERGENCY_ALERTS).map((flight) => (
        <div
          key={flight.missionId}
          role="alert"
          className="rounded-lg border border-line bg-surface p-3 text-sm shadow-lg"
        >
          <p className="font-medium text-fg">
            Simulated emergency: {flight.droneId} ({flight.missionId})
          </p>
          <p className="mt-1 text-fg-muted">
            {flight.emergency ? EMERGENCY_REASON_TEXT[flight.emergency.reason] : ''}. The drone is
            out of service (maintenance) at {flight.position[1].toFixed(5)},{' '}
            {flight.position[0].toFixed(5)}; the parcel was already delivered. This is a simulation
            outcome and needs an operator.
          </p>
        </div>
      ))}

      {emergencies.length > MAX_EMERGENCY_ALERTS && (
        <div role="alert" className={NOTICE_CLASS}>
          {emergencies.length - MAX_EMERGENCY_ALERTS} more simulated emergencies are not listed
          here; each affected drone is out of service and shows its alert in its panel.
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
