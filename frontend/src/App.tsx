import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { startMission } from './api/missions'
import { ResourceStatusBanner } from './features/data/ResourceStatusBanner'
import { DroneDetailPanel } from './features/drones/DroneDetailPanel'
import { useDrones } from './features/drones/useDrones'
import { canAnimateFlights, flightsByDrone, isActiveFlight } from './features/flights/flightStatus'
import type { FlightVisual } from './features/flights/interpolation'
import { LiveDataNotices } from './features/flights/LiveDataNotices'
import { useFlights } from './features/flights/useFlights'
import { usePrefersReducedMotion } from './features/flights/usePrefersReducedMotion'
import { HubDetailPanel } from './features/hubs/HubDetailPanel'
import { useHubs } from './features/hubs/useHubs'
import { computeDroneOffsets } from './features/map/droneMarkers'
import { partitionFleet } from './features/map/fleetPlacement'
import { MapView } from './features/map/MapView'
import { computeOrderOffsets } from './features/map/orderMarkers'
import { DronesManager } from './features/management/DronesManager'
import { ManagementPanel } from './features/management/ManagementPanel'
import { OrdersManager } from './features/management/OrdersManager'
import { useMissions } from './features/missions/useMissions'
import { OrderDetailPanel } from './features/orders/OrderDetailPanel'
import { OrdersList } from './features/orders/OrdersList'
import { useOrders } from './features/orders/useOrders'
import { BackendStatus } from './features/system-status/BackendStatus'
import type { Drone } from './types/drone'
import type { Flight } from './types/flight'
import type { Hub } from './types/hub'
import type { Mission } from './types/mission'
import type { Order } from './types/order'

const NO_HUBS: readonly Hub[] = []
const NO_DRONES: readonly Drone[] = []
const NO_ORDERS: readonly Order[] = []
const NO_FLIGHTS: readonly Flight[] = []
const NO_MISSIONS: readonly Mission[] = []

/** Only one Hub, drone or order is selected at a time, so only one detail panel can be open. */
type Selection =
  { kind: 'hub'; id: string } | { kind: 'drone'; id: string } | { kind: 'order'; id: string }

function App() {
  const hubsResource = useHubs()
  const dronesResource = useDrones()
  const ordersResource = useOrders()
  const flightsResource = useFlights()
  const missionsResource = useMissions()
  const reducedMotion = usePrefersReducedMotion()
  const hubs = hubsResource.state.status === 'ready' ? hubsResource.state.data : NO_HUBS
  const drones = dronesResource.state.status === 'ready' ? dronesResource.state.data : NO_DRONES
  const orders = ordersResource.state.status === 'ready' ? ordersResource.state.data : NO_ORDERS
  const flightsSnapshot =
    flightsResource.state.status === 'ready' ? flightsResource.state.data : null
  const flights = flightsSnapshot?.flights ?? NO_FLIGHTS
  const workerStale = flightsSnapshot?.workerStale ?? true
  const missions =
    missionsResource.state.status === 'ready' ? missionsResource.state.data : NO_MISSIONS

  const [selection, setSelection] = useState<Selection | null>(null)
  const [managementOpen, setManagementOpen] = useState(false)
  const selectHub = useCallback((id: string) => setSelection({ kind: 'hub', id }), [])
  const selectDrone = useCallback((id: string) => setSelection({ kind: 'drone', id }), [])
  const selectOrder = useCallback((id: string) => setSelection({ kind: 'order', id }), [])
  const clearSelection = useCallback(() => setSelection(null), [])

  const selectedHub =
    selection?.kind === 'hub' ? hubs.find((hub) => hub.id === selection.id) : undefined
  const selectedDrone =
    selection?.kind === 'drone' ? drones.find((drone) => drone.id === selection.id) : undefined
  const selectedOrder =
    selection?.kind === 'order' ? orders.find((order) => order.id === selection.id) : undefined
  const orderOffsets = useMemo(() => computeOrderOffsets(orders, hubs), [orders, hubs])

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

  // Flights: the backend's snapshots. The map only glides between them (and not at all for reduced
  // motion or a worker that stopped updating); phase, battery and landing come from the backend.
  const flightByDrone = useMemo(() => flightsByDrone(flights), [flights])
  const receivedAt = flightsResource.receivedAt
  const flightsStale = flightsResource.stale
  const flightVisuals = useMemo<FlightVisual[]>(
    () =>
      receivedAt === null
        ? []
        : flights.filter(isActiveFlight).map((flight) => ({
            droneId: flight.droneId,
            motion: {
              position: flight.position,
              target: flight.target,
              snapshotAgeS: flight.snapshotAgeS,
            },
            receivedAt,
            animate: canAnimateFlights({
              reducedMotion,
              workerStale,
              refreshFailed: flightsStale,
            }),
          })),
    [flights, receivedAt, reducedMotion, workerStale, flightsStale],
  )

  // The temporary Start Mission control: only missions that are already assigned.
  const assignedMissions = useMemo(
    () => missions.filter((mission) => mission.status === 'ASSIGNED'),
    [missions],
  )
  const assignedByOrder = useMemo(
    () => new Map(assignedMissions.map((mission) => [mission.orderId, mission])),
    [assignedMissions],
  )
  const assignedByDrone = useMemo(
    () => new Map(assignedMissions.map((mission) => [mission.droneId, mission])),
    [assignedMissions],
  )
  const assignedMissionDroneIds = useMemo(
    () => new Set(assignedMissions.map((mission) => mission.droneId)),
    [assignedMissions],
  )

  const refreshDrones = dronesResource.refresh
  const refreshOrders = ordersResource.refresh
  const refreshFlights = flightsResource.refresh
  const refreshMissions = missionsResource.refresh
  const startAssignedMission = useCallback(
    async (missionId: string) => {
      try {
        await startMission(missionId)
      } finally {
        // Show the outcome now instead of waiting for the next poll, whatever it was: a refused
        // or unreadable answer may still mean the state changed.
        refreshMissions()
        refreshDrones()
        refreshOrders()
        refreshFlights()
      }
    },
    [refreshMissions, refreshDrones, refreshOrders, refreshFlights],
  )

  // A takeoff or a landing changes drones, orders and missions together. When the set of flying
  // missions changes, read them at once so markers, Hub counts and statuses agree with the flights.
  const flyingKey = flights
    .filter(isActiveFlight)
    .map((flight) => flight.missionId)
    .sort()
    .join('|')
  const previousFlyingKey = useRef<string | null>(null)
  useEffect(() => {
    if (previousFlyingKey.current !== null && previousFlyingKey.current !== flyingKey) {
      refreshDrones()
      refreshOrders()
      refreshMissions()
    }
    previousFlyingKey.current = flyingKey
  }, [flyingKey, refreshDrones, refreshOrders, refreshMissions])

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">
            Sky<span className="text-accent">Fleet</span>
          </h1>
          <span className="hidden text-sm text-fg-muted sm:inline">Operations Center</span>
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            aria-expanded={managementOpen}
            className="rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-raised"
            onClick={() => setManagementOpen((open) => !open)}
          >
            Management
          </button>
          <BackendStatus />
        </div>
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
          flights={flightVisuals}
          orders={orders}
          selectedOrderId={selection?.kind === 'order' ? selection.id : null}
          onSelectOrder={selectOrder}
          orderOffsets={orderOffsets}
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
          <ResourceStatusBanner
            resource="order"
            state={ordersResource.state}
            onRetry={ordersResource.retry}
          />
          <LiveDataNotices
            flights={flightsResource}
            missions={missionsResource}
            fleetStale={dronesResource.stale || ordersResource.stale}
            onRefreshFleet={() => {
              refreshDrones()
              refreshOrders()
            }}
          />
          <OrdersList
            orders={orders}
            hubs={hubs}
            selectedOrderId={selection?.kind === 'order' ? selection.id : null}
            onSelectOrder={selectOrder}
            hideOnNarrow={selection !== null}
          />
        </div>
        {selectedHub && (
          <HubDetailPanel
            hub={selectedHub}
            dockedDrones={dockedByHub.get(selectedHub.id)}
            onSelectDrone={selectDrone}
            assignedMissionDroneIds={assignedMissionDroneIds}
            onClose={clearSelection}
          />
        )}
        {selectedOrder && (
          <OrderDetailPanel
            order={selectedOrder}
            hub={hubs.find((hub) => hub.id === selectedOrder.originHubId)}
            markerSpread={orderOffsets.has(selectedOrder.id)}
            onClose={clearSelection}
            hubs={hubs}
            assignedMission={assignedByOrder.get(selectedOrder.id)}
            onStartMission={startAssignedMission}
          />
        )}
        {managementOpen && (
          <ManagementPanel
            onClose={() => setManagementOpen(false)}
            tabs={[
              {
                id: 'orders',
                label: 'Orders',
                content: (
                  <OrdersManager
                    orders={orders}
                    hubs={hubs}
                    missions={missions}
                    onChanged={() => {
                      refreshOrders()
                      refreshMissions()
                    }}
                  />
                ),
              },
              {
                id: 'drones',
                label: 'Drones',
                content: (
                  <DronesManager
                    drones={drones}
                    hubs={hubs}
                    missions={missions}
                    onChanged={() => {
                      refreshDrones()
                      refreshMissions()
                    }}
                  />
                ),
              },
            ]}
          />
        )}
        {selectedDrone && (
          <DroneDetailPanel
            drone={selectedDrone}
            hub={hubs.find((hub) => hub.id === selectedDrone.hubId)}
            markerSpread={droneOffsets.has(selectedDrone.id)}
            onClose={clearSelection}
            hubs={hubs}
            flight={flightByDrone.get(selectedDrone.id)}
            workerStale={workerStale}
            assignedMission={assignedByDrone.get(selectedDrone.id)}
            onStartMission={startAssignedMission}
          />
        )}
      </main>
    </div>
  )
}

export default App
