import { useCallback, useMemo, useState } from 'react'

import { ResourceStatusBanner } from './features/data/ResourceStatusBanner'
import { DroneDetailPanel } from './features/drones/DroneDetailPanel'
import { useDrones } from './features/drones/useDrones'
import { HubDetailPanel } from './features/hubs/HubDetailPanel'
import { useHubs } from './features/hubs/useHubs'
import { computeDroneOffsets } from './features/map/droneMarkers'
import { partitionFleet } from './features/map/fleetPlacement'
import { MapView } from './features/map/MapView'
import { BackendStatus } from './features/system-status/BackendStatus'
import type { Drone } from './types/drone'
import type { Hub } from './types/hub'

const NO_HUBS: readonly Hub[] = []
const NO_DRONES: readonly Drone[] = []

/** Only one Hub or drone is selected at a time, so only one detail panel can be open. */
type Selection = { kind: 'hub'; id: string } | { kind: 'drone'; id: string }

function App() {
  const hubsResource = useHubs()
  const dronesResource = useDrones()
  const hubs = hubsResource.state.status === 'ready' ? hubsResource.state.data : NO_HUBS
  const drones = dronesResource.state.status === 'ready' ? dronesResource.state.data : NO_DRONES

  const [selection, setSelection] = useState<Selection | null>(null)
  const selectHub = useCallback((id: string) => setSelection({ kind: 'hub', id }), [])
  const selectDrone = useCallback((id: string) => setSelection({ kind: 'drone', id }), [])
  const clearSelection = useCallback(() => setSelection(null), [])

  const selectedHub =
    selection?.kind === 'hub' ? hubs.find((hub) => hub.id === selection.id) : undefined
  const selectedDrone =
    selection?.kind === 'drone' ? drones.find((drone) => drone.id === selection.id) : undefined
  // Docked drones are shown as a count on their Hub; only the rest get individual markers.
  // Docking can only be judged against known Hubs. Until they are loaded (or if they failed) only
  // drones that are in flight are drawn; claiming "not at a Hub" would be wrong, not just unknown.
  const hubsReady = hubsResource.state.status === 'ready'
  const { dockedByHub, markerDrones } = useMemo(
    () =>
      hubsReady
        ? partitionFleet(drones, hubs)
        : {
            dockedByHub: new Map<string, readonly Drone[]>(),
            markerDrones: drones.filter((drone) => drone.status === 'IN_FLIGHT'),
          },
    [drones, hubs, hubsReady],
  )
  const dockedCounts = useMemo(
    () => new Map([...dockedByHub].map(([hubId, group]) => [hubId, group.length])),
    [dockedByHub],
  )
  const droneOffsets = useMemo(() => computeDroneOffsets(markerDrones, hubs), [markerDrones, hubs])

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">
            Sky<span className="text-accent">Fleet</span>
          </h1>
          <span className="hidden text-sm text-fg-muted sm:inline">Operations Center</span>
        </div>
        <BackendStatus />
      </header>

      <main className="relative min-h-0 flex-1">
        <MapView
          hubs={hubs}
          selectedHubId={selection?.kind === 'hub' ? selection.id : null}
          onSelectHub={selectHub}
          drones={markerDrones}
          dockedCounts={dockedCounts}
          selectedDroneId={selection?.kind === 'drone' ? selection.id : null}
          onSelectDrone={selectDrone}
          droneOffsets={droneOffsets}
        />
        <div className="absolute inset-x-3 top-3 z-20 flex flex-col gap-2 sm:inset-x-auto sm:right-3 sm:w-80">
          <ResourceStatusBanner
            resource="hub"
            state={hubsResource.state}
            onRetry={hubsResource.retry}
          />
          <ResourceStatusBanner
            resource="drone"
            state={dronesResource.state}
            onRetry={dronesResource.retry}
          />
        </div>
        {selectedHub && (
          <HubDetailPanel
            hub={selectedHub}
            dockedDrones={dockedByHub.get(selectedHub.id)}
            onSelectDrone={selectDrone}
            onClose={clearSelection}
          />
        )}
        {selectedDrone && (
          <DroneDetailPanel
            drone={selectedDrone}
            hub={hubs.find((hub) => hub.id === selectedDrone.hubId)}
            markerSpread={droneOffsets.has(selectedDrone.id)}
            onClose={clearSelection}
          />
        )}
      </main>
    </div>
  )
}

export default App
