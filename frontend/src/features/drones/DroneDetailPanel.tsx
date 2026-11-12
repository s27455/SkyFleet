import { type ReactNode, useEffect } from 'react'

import { DETAIL_PANEL_CLASS } from '../../components/ui/detailPanel'
import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import { FlightSection } from '../flights/FlightSection'
import { StartMissionControl } from '../missions/StartMissionControl'
import { DRONE_STATUS_DISPLAY } from './droneStatus'

interface DroneDetailPanelProps {
  drone: Drone
  /** The assigned Hub if the Hub data is available; otherwise the Hub id is shown as is. */
  hub?: Hub
  /** True when the map marker is spread on screen because drones share this location. */
  markerSpread: boolean
  onClose: () => void
  /** All Hubs, to name the Hubs of a flight. */
  hubs?: readonly Hub[]
  /** The drone's backend-reported flight (active, or ended in an emergency), if any. */
  flight?: Flight
  /** True when the simulation worker has stopped updating flights. */
  workerStale?: boolean
  /** An `ASSIGNED` mission of this drone, which can be started from here. */
  assignedMission?: Mission
  onStartMission?: (missionId: string) => Promise<void>
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

const NO_HUBS: readonly Hub[] = []

export function DroneDetailPanel({
  drone,
  hub,
  markerSpread,
  onClose,
  hubs = NO_HUBS,
  flight,
  workerStale = false,
  assignedMission,
  onStartMission,
}: DroneDetailPanelProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const status = DRONE_STATUS_DISPLAY[drone.status]
  const { model } = drone
  const [longitude, latitude] = drone.coordinates

  return (
    <aside aria-label={`Drone details: ${drone.id}`} className={DETAIL_PANEL_CLASS}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{drone.id}</h2>
          <p className="text-sm text-fg-muted">{model.name}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close drone details"
          className="-mt-1 -mr-1 inline-flex size-10 items-center justify-center rounded-md text-fg-muted hover:bg-surface-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <Row label="Status">
          <StatusIndicator tone={status.tone} label={status.label} />
        </Row>
        <Row label="Battery">
          <span className="font-mono tabular-nums">{drone.batteryPct}%</span>
        </Row>
        <Row label="Assigned Hub">{hub ? hub.name : drone.hubId}</Row>
        <Row label="Stored position">
          <span className="font-mono text-xs tabular-nums">
            {latitude.toFixed(6)}, {longitude.toFixed(6)}
          </span>
        </Row>
      </dl>

      {flight && <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />}
      {assignedMission && onStartMission && (
        <StartMissionControl
          mission={assignedMission}
          returnHubName={
            hubs.find((candidate) => candidate.id === assignedMission.returnHubId)?.name
          }
          onStart={onStartMission}
        />
      )}

      <h3 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">
        Model capabilities
      </h3>
      <dl className="mt-2 space-y-2 text-sm">
        <Row label="Maximum payload">{model.maxPayloadKg} kg</Row>
        <Row label="Maximum total flight distance">{model.maxRangeKm} km</Row>
        <Row label="Conservative mission distance">{model.recommendedMissionRangeKm} km</Row>
        <Row label="Cruise speed">{model.cruiseSpeedKmh} km/h</Row>
        <Row label="Nominal flight time">{model.nominalFlightTimeMin} min</Row>
        <Row label="Minimum battery reserve">{model.minBatteryReservePct}%</Row>
      </dl>

      <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
        Backend snapshot, refreshed about every 2 seconds; flights are simulated. Distances are
        totals for the whole route including the return to a Hub. Capabilities are simulation
        assumptions.
        {markerSpread &&
          ' Markers at the same location are spread slightly on screen; the position above is the real stored one.'}
      </p>
    </aside>
  )
}
