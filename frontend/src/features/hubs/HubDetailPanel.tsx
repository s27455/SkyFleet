import { useEffect } from 'react'

import { DETAIL_PANEL_CLASS } from '../../components/ui/detailPanel'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { DRONE_STATUS_DISPLAY } from '../drones/droneStatus'

interface HubDetailPanelProps {
  hub: Hub
  /** Drones physically docked at this Hub (see fleetPlacement). */
  dockedDrones?: readonly Drone[]
  onSelectDrone?: (droneId: string) => void
  onClose: () => void
}

const NO_DRONES: readonly Drone[] = []

export function HubDetailPanel({
  hub,
  dockedDrones = NO_DRONES,
  onSelectDrone = () => {},
  onClose,
}: HubDetailPanelProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <aside aria-label={`Hub details: ${hub.name}`} className={DETAIL_PANEL_CLASS}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{hub.name}</h2>
          <p className="text-sm text-fg-muted">{hub.address}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close hub details"
          className="-mt-1 -mr-1 inline-flex size-10 items-center justify-center rounded-md text-fg-muted hover:bg-surface-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-fg-muted">Maximum drone capacity</dt>
          <dd className="font-mono tabular-nums">{hub.droneCapacity}</dd>
        </div>
      </dl>

      <section aria-labelledby="hub-docked-drones" className="mt-3 border-t border-line pt-3">
        <h3 id="hub-docked-drones" className="text-sm font-medium">
          Drones at this Hub ({dockedDrones.length})
        </h3>
        {dockedDrones.length === 0 ? (
          <p className="mt-1 text-sm text-fg-muted">No drones are docked here.</p>
        ) : (
          <ul className="mt-1 max-h-40 overflow-y-auto">
            {dockedDrones.map((drone) => (
              <li key={drone.id}>
                <button
                  type="button"
                  onClick={() => onSelectDrone(drone.id)}
                  className="flex min-h-10 w-full items-center justify-between gap-3 rounded-md px-2 text-left text-sm hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <span className="font-mono">{drone.id}</span>
                  <span className="text-fg-muted">
                    {DRONE_STATUS_DISPLAY[drone.status].label} · {drone.batteryPct}%
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
        Illustrative mall location, not a real SkyFleet facility.
      </p>
    </aside>
  )
}
