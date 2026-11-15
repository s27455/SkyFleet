import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { startMission } from './api/missions'
import { AutoDispatchControl } from './features/dispatch/AutoDispatchControl'
import { ResourceStatusBanner } from './features/data/ResourceStatusBanner'
import { DroneDetailPanel } from './features/drones/DroneDetailPanel'
import { DroneInspector } from './features/drones/DroneInspector'
import { resolveInspectorData } from './features/drones/inspectorData'
import { useDrones } from './features/drones/useDrones'
import {
  droneEmergencies as deriveDroneEmergencies,
  emergencyPoints as deriveEmergencyPoints,
  interruptedOrderIds as deriveInterruptedOrderIds,
} from './features/flights/emergencyPoints'
import {
  canAnimateFlights,
  flightsByDrone,
  isActiveFlight,
  isFailable,
  isRecipientTargetable,
} from './features/flights/flightStatus'
import type { FlightVisual } from './features/flights/interpolation'
import { useLpr } from './features/lpr/useLpr'
import { RainWarningBanner } from './features/weather/RainWarningBanner'
import { TakeoffsSuspendedProvider } from './features/weather/TakeoffGate'
import { useRainWarning } from './features/weather/useRainWarning'
import { LiveDataNotices } from './features/flights/LiveDataNotices'
import { useFlights } from './features/flights/useFlights'
import { usePrefersReducedMotion } from './features/flights/usePrefersReducedMotion'
import { HubDetailPanel } from './features/hubs/HubDetailPanel'
import { useHubs } from './features/hubs/useHubs'
import { computeDroneOffsets } from './features/map/droneMarkers'
import { partitionFleet } from './features/map/fleetPlacement'
import { FocusNotice, type FocusNoticeData } from './features/map/FocusNotice'
import { type FocusKind, type FocusRequest, resolveFocusTarget } from './features/map/focusTarget'
import { OrderMarkerLegend } from './features/map/OrderMarkerLegend'
import { type LprView, MapView } from './features/map/MapView'
import { computeOrderOffsets } from './features/map/orderMarkers'
import { DronesManager } from './features/management/DronesManager'
import { ManagementPanel } from './features/management/ManagementPanel'
import { OrdersManager } from './features/management/OrdersManager'
import { useMissions } from './features/missions/useMissions'
import { ScenarioMenu } from './features/incidents/ScenarioMenu'
import { useRandomIncidents } from './features/incidents/useRandomIncidents'
import { OrderSimulationPanel } from './features/orderSimulation/OrderSimulationPanel'
import { OrderDetailPanel } from './features/orders/OrderDetailPanel'
import { OrdersList } from './features/orders/OrdersList'
import { OrderGenerationControl } from './features/orderSimulation/OrderGenerationControl'
import { useOrderSimulation } from './features/orderSimulation/useOrderSimulation'
import { DronesList } from './features/operations/DronesList'
import { CopilotTab } from './features/copilot/CopilotTab'
import { useCopilot } from './features/copilot/useCopilot'
import { EventsTab } from './features/operations/EventsTab'
import { HubsList } from './features/operations/HubsList'
import { buildNotices } from './features/operations/notices'
import { OperationsPanel } from './features/operations/OperationsPanel'
import type { OperationsTab } from './features/operations/tabs'
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
  // The inspector opens above the selected drone's panel; the selection itself is never touched.
  const [inspectedDroneId, setInspectedDroneId] = useState<string | null>(null)
  // The Operations panel follows the selection (even while it is closed); the operator can still
  // switch tabs by hand without touching the selection.
  const [operationsTab, setOperationsTab] = useState<OperationsTab>('orders')
  // Feature 026: the Copilot's state lives here, above the tabs, so switching tabs (or a map
  // selection that does) never loses a draft, an answer or a request still on its way.
  const copilot = useCopilot()
  const selectHub = useCallback((id: string) => {
    setSelection({ kind: 'hub', id })
    setOperationsTab('hubs')
  }, [])
  const selectDrone = useCallback((id: string) => {
    setSelection({ kind: 'drone', id })
    setOperationsTab('drones')
  }, [])
  const selectOrder = useCallback((id: string) => {
    setSelection({ kind: 'order', id })
    setOperationsTab('orders')
  }, [])
  const clearSelection = useCallback(() => {
    setInspectedDroneId(null)
    setSelection(null)
  }, [])
  const closeInspector = useCallback(() => setInspectedDroneId(null), [])

  // Feature 023: a click in an Operations list also moves the map camera there, once. A marker click
  // keeps the plain select above and never moves the camera. Every click gets a new `seq`, so
  // clicking the same row again flies again; a re-render or a data refresh keeps the same request
  // and moves nothing. An entity without a usable location leaves the camera alone and says so.
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null)
  const [focusNotice, setFocusNotice] = useState<FocusNoticeData | null>(null)
  const focusSeq = useRef(0)
  const dismissFocusNotice = useCallback(() => setFocusNotice(null), [])
  const locate = useCallback(
    (kind: FocusKind, id: string) => {
      const { label, position } = resolveFocusTarget(kind, id, { hubs, drones, orders })
      focusSeq.current += 1
      const seq = focusSeq.current
      if (position === null) {
        setFocusNotice({ seq, text: `The location of ${label} is not available.` })
        return
      }
      setFocusNotice(null)
      setFocusRequest({ kind, id, position, seq })
    },
    [hubs, drones, orders],
  )
  const focusHub = useCallback(
    (id: string) => {
      selectHub(id)
      locate('hub', id)
    },
    [selectHub, locate],
  )
  const focusDrone = useCallback(
    (id: string) => {
      selectDrone(id)
      locate('drone', id)
    },
    [selectDrone, locate],
  )
  const focusOrder = useCallback(
    (id: string) => {
      selectOrder(id)
      locate('order', id)
    },
    [selectOrder, locate],
  )

  const selectedHub =
    selection?.kind === 'hub' ? hubs.find((hub) => hub.id === selection.id) : undefined
  const selectedDrone =
    selection?.kind === 'drone' ? drones.find((drone) => drone.id === selection.id) : undefined
  const selectedOrder =
    selection?.kind === 'order' ? orders.find((order) => order.id === selection.id) : undefined
  // An order can leave the active list while selected (its delivered window ended). Drop the
  // selection then, once the orders are known, so no stale selection lingers. Adjusting state while
  // rendering is allowed.
  if (selection?.kind === 'order' && ordersResource.state.status === 'ready' && !selectedOrder) {
    setSelection(null)
  }
  // The inspector exists only for a drone that is still selected and still in the data.
  const inspectorOpen = selectedDrone !== undefined && inspectedDroneId === selectedDrone.id
  const inspectorData = useMemo(
    () =>
      selectedDrone
        ? resolveInspectorData({
            droneId: selectedDrone.id,
            flights,
            missions,
            orders,
            flightsStatus: flightsResource.state.status,
            missionsStatus: missionsResource.state.status,
            ordersStatus: ordersResource.state.status,
          })
        : null,
    [
      selectedDrone,
      flights,
      missions,
      orders,
      flightsResource.state.status,
      missionsResource.state.status,
      ordersResource.state.status,
    ],
  )
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
  // Drone failures (Feature 018C), all derived from the backend's flights and drones.
  const emergencyPoints = useMemo(() => deriveEmergencyPoints(flights, drones), [flights, drones])
  const droneEmergencies = useMemo(() => deriveDroneEmergencies(emergencyPoints), [emergencyPoints])
  const interruptedOrderIds = useMemo(() => deriveInterruptedOrderIds(flights), [flights])
  const canFailDrone = useMemo(() => flights.some(isFailable), [flights])
  const canMarkRecipient = useMemo(() => flights.some(isRecipientTargetable), [flights])
  // The LPR helicopter (Feature 018E): the backend's scenario and which drones wait for it.
  const lprResource = useLpr()
  const randomIncidents = useRandomIncidents() // one poll, read by the Scenarios menu
  const orderSimulation = useOrderSimulation() // one poll, shared by the header switch and Management
  const rainResource = useRainWarning()
  const rainWarningActive = rainResource.state.status === 'ready' && rainResource.state.data.active
  const refreshRainWarning = rainResource.refresh
  const lprScenario = lprResource.state.status === 'ready' ? lprResource.state.data.scenario : null
  const lprReceivedAt = lprResource.receivedAt
  const lprStale = lprResource.stale
  const lprView = useMemo<LprView | null>(
    () =>
      lprScenario === null || lprReceivedAt === null
        ? null
        : {
            scenario: lprScenario,
            receivedAt: lprReceivedAt,
            animate: canAnimateFlights({
              reducedMotion,
              workerStale: false, // the helicopter is computed from the clock, not by the worker
              refreshFailed: lprStale,
            }),
          },
    [lprScenario, lprReceivedAt, reducedMotion, lprStale],
  )
  const yieldingDroneIds = useMemo(
    () => new Set(flights.filter((flight) => flight.yieldingToLpr).map((flight) => flight.droneId)),
    [flights],
  )
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
    () =>
      new Map(
        assignedMissions.flatMap((mission) =>
          mission.orderId === null ? [] : [[mission.orderId, mission] as const],
        ),
      ),
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
  const refreshLpr = lprResource.refresh
  const refreshMissions = missionsResource.refresh
  const [activityTick, setActivityTick] = useState(0)
  const refreshAfterIncident = useCallback(() => {
    setActivityTick((tick) => tick + 1) // the Activity timeline re-reads at once
    // A cancellation can recall a flying drone and cancel an assigned mission.
    refreshOrders()
    refreshMissions()
    refreshDrones()
    refreshFlights()
    refreshLpr()
    refreshRainWarning()
  }, [
    refreshOrders,
    refreshMissions,
    refreshDrones,
    refreshFlights,
    refreshLpr,
    refreshRainWarning,
  ])
  // A relocation changes the drone, its flight and its Activity; read them at once (Feature 019A).
  const refreshAfterRelocation = useCallback(() => {
    setActivityTick((tick) => tick + 1)
    refreshMissions()
    refreshDrones()
    refreshFlights()
  }, [refreshMissions, refreshDrones, refreshFlights])
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

  const notices = useMemo(
    () =>
      buildNotices({
        emergencies: flights.filter((flight) => flight.emergency),
        rainWarningActive,
        lprActive: lprScenario !== null,
        flightsUnavailable: flightsResource.state.status === 'error',
        flightsStale: flightsResource.state.status === 'ready' && flightsResource.stale,
        fleetStale: dronesResource.stale || ordersResource.stale,
        workerStoppedWhileFlying: workerStale && flights.some(isActiveFlight),
      }),
    [
      flights,
      rainWarningActive,
      lprScenario,
      flightsResource.state.status,
      flightsResource.stale,
      dronesResource.stale,
      ordersResource.stale,
      workerStale,
    ],
  )

  return (
    <TakeoffsSuspendedProvider value={rainWarningActive}>
      <div className="flex h-dvh flex-col">
        <header
          inert={inspectorOpen}
          className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line bg-surface px-4 py-3 sm:px-6"
        >
          <div className="flex items-baseline gap-3">
            <h1 className="text-lg font-semibold tracking-tight">
              Sky<span className="text-accent">Fleet</span>
            </h1>
            <span className="hidden text-sm text-fg-muted sm:inline">Operations Center</span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
            <AutoDispatchControl />
            <OrderGenerationControl resource={orderSimulation} />
            <ScenarioMenu
              selectedOrder={selectedOrder ?? null}
              onOrderCancelled={refreshAfterIncident}
              canFailDrone={canFailDrone}
              onDroneFailed={refreshAfterIncident}
              canMarkRecipient={canMarkRecipient}
              onRecipientMarked={refreshAfterIncident}
              lprActive={lprScenario !== null}
              onLprTriggered={refreshAfterIncident}
              rainWarningActive={rainWarningActive}
              onRainWarningChanged={refreshAfterIncident}
              randomIncidents={randomIncidents}
            />
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
        <RainWarningBanner active={rainWarningActive} stale={rainResource.stale} />

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
            emergencyPoints={emergencyPoints}
            droneEmergencies={droneEmergencies}
            interruptedOrderIds={interruptedOrderIds}
            lpr={lprView}
            yieldingDroneIds={yieldingDroneIds}
            focusRequest={focusRequest}
          />
          <OrderMarkerLegend
            hideOnNarrow={selection !== null}
            showEmergency={emergencyPoints.length > 0}
            showLpr={lprScenario !== null}
          />
          <div className="pointer-events-none absolute inset-x-3 top-3 z-20 flex max-h-[calc(100%-1.5rem)] min-h-0 flex-col gap-2 sm:inset-x-auto sm:right-3 sm:w-80 [&>*]:pointer-events-auto">
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
            <FocusNotice notice={focusNotice} onDismiss={dismissFocusNotice} />
            <LiveDataNotices
              flights={flightsResource}
              missions={missionsResource}
              fleetStale={dronesResource.stale || ordersResource.stale}
              onRefreshFleet={() => {
                refreshDrones()
                refreshOrders()
              }}
            />
            <OperationsPanel
              tab={operationsTab}
              onTabChange={setOperationsTab}
              labels={{
                drones: `Drones (${drones.length})`,
                hubs: `Hubs (${hubs.length})`,
                orders: `Orders (${orders.length})`,
                events: 'Events',
                copilot: 'Copilot',
              }}
              hideOnNarrow={selection !== null}
            >
              {operationsTab === 'drones' && (
                <DronesList
                  drones={drones}
                  hubs={hubs}
                  selectedDroneId={selection?.kind === 'drone' ? selection.id : null}
                  onSelectDrone={focusDrone}
                />
              )}
              {operationsTab === 'hubs' && (
                <HubsList
                  hubs={hubs}
                  dockedCounts={dockedCounts}
                  selectedHubId={selection?.kind === 'hub' ? selection.id : null}
                  onSelectHub={focusHub}
                />
              )}
              {operationsTab === 'orders' && (
                <OrdersList
                  orders={orders}
                  hubs={hubs}
                  selectedOrderId={selection?.kind === 'order' ? selection.id : null}
                  onSelectOrder={focusOrder}
                />
              )}
              {operationsTab === 'copilot' && <CopilotTab copilot={copilot} />}
              {operationsTab === 'events' && (
                <EventsTab
                  notices={notices}
                  activity={
                    selectedDrone
                      ? { kind: 'drone', id: selectedDrone.id }
                      : selectedOrder
                        ? { kind: 'order', id: selectedOrder.id }
                        : null
                  }
                  activityRefreshKey={activityTick}
                />
              )}
            </OperationsPanel>
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
              onCancelled={refreshAfterIncident}
              flight={flights.find((candidate) => candidate.orderId === selectedOrder.id)}
              workerStale={workerStale}
              activityRefreshKey={activityTick}
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
                    <div className="flex flex-col gap-4">
                      <OrderSimulationPanel
                        onGenerated={refreshOrders}
                        resource={orderSimulation}
                      />
                      <OrdersManager
                        selectedOrderId={selection?.kind === 'order' ? selection.id : null}
                        onSelectOrder={selectOrder}
                        orders={orders}
                        hubs={hubs}
                        missions={missions}
                        onChanged={() => {
                          refreshOrders()
                          refreshMissions()
                        }}
                      />
                    </div>
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
              markerSpread={droneOffsets.has(selectedDrone.id)}
              onClose={clearSelection}
              hubs={hubs}
              flight={flightByDrone.get(selectedDrone.id)}
              workerStale={workerStale}
              assignedMission={assignedByDrone.get(selectedDrone.id)}
              onStartMission={startAssignedMission}
              onRelocationChanged={refreshAfterRelocation}
              activityRefreshKey={activityTick}
              onInspect={() => setInspectedDroneId(selectedDrone.id)}
              closeOnEscape={!inspectorOpen}
            />
          )}
          {selectedDrone && inspectorOpen && inspectorData && (
            <DroneInspector
              drone={selectedDrone}
              hubs={hubs}
              data={inspectorData}
              workerStale={workerStale}
              dataStale={
                dronesResource.stale ||
                flightsResource.stale ||
                missionsResource.stale ||
                ordersResource.stale
              }
              onClose={closeInspector}
            />
          )}
        </main>
      </div>
    </TakeoffsSuspendedProvider>
  )
}

export default App
