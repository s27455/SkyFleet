import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { DRONE_STATUS_DISPLAY } from '../drones/droneStatus'

interface DronesListProps {
  drones: readonly Drone[]
  hubs: readonly Hub[]
  selectedDroneId: string | null
  onSelectDrone: (droneId: string) => void
}

/** Every drone as a selectable row (the Drones tab). Selecting opens the usual drone details. */
export function DronesList({ drones, hubs, selectedDroneId, onSelectDrone }: DronesListProps) {
  const hubNames = new Map(hubs.map((hub) => [hub.id, hub.name]))
  if (drones.length === 0) return <p className="p-3 text-xs text-fg-muted">No drones.</p>

  return (
    <ul aria-label="Drones">
      {drones.map((drone) => {
        const selected = drone.id === selectedDroneId
        return (
          <li key={drone.id}>
            <button
              type="button"
              aria-pressed={selected}
              onClick={() => onSelectDrone(drone.id)}
              className={`flex min-h-10 w-full flex-col gap-0.5 border-l-4 px-3 py-2 text-left hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent ${
                selected ? 'border-accent bg-surface-raised' : 'border-transparent'
              }`}
            >
              <span className="flex items-center justify-between gap-3">
                <span className="font-mono">{drone.id}</span>
                <span className="text-fg-muted">
                  {DRONE_STATUS_DISPLAY[drone.status].label} · {drone.batteryPct}%
                </span>
              </span>
              <span className="text-xs text-fg-muted">
                {hubNames.get(drone.hubId) ?? drone.hubId}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
