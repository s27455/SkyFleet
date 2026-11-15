import { useMemo, useState } from 'react'

import { AutoDispatchControl } from './features/dispatch/AutoDispatchControl'
import { ResourceStatusBanner } from './features/data/ResourceStatusBanner'
import { DroneDetailPanel } from './features/drones/DroneDetailPanel'
import { DroneInspector } from './features/drones/DroneInspector'
import { resolveInspectorData } from './features/drones/inspectorData'
import { useDrones } from './features/drones/useDrones'
import { isActiveFlight } from './features/flights/flightStatus'
import { useLpr } from './features/lpr/useLpr'
import { RainWarningBanner } from './features/weather/RainWarningBanner'
import { TakeoffsSuspendedProvider } from './features/weather/TakeoffGate'
import { useRainWarning } from './features/weather/useRainWarning'
import { LiveDataNotices } from './features/flights/LiveDataNotices'
import { useFlights } from './features/flights/useFlights'
import { useFlightView } from './features/flights/useFlightView'
import { HubDetailPanel } from './features/hubs/HubDetailPanel'
import { useHubs } from './features/hubs/useHubs'
import { computeDroneOffsets } from './features/map/droneMarkers'
import { partitionFleet } from './features/map/fleetPlacement'
import { FocusNotice } from './features/map/FocusNotice'
import { OrderMarkerLegend } from './features/map/OrderMarkerLegend'
import { MapView } from './features/map/MapView'
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
import { useRefreshActions } from './features/operations/useRefreshActions'
import { useSelection } from './features/operations/useSelection'
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

function App() {
  const hubsResource = useHubs()
  const dronesResource = useDrones()
  const ordersResource = useOrders()
  const flightsResource = useFlights()
  const missionsResource = useMissions()
  const hubs = hubsResource.state.status === 'ready' ? hubsResource.state.data : NO_HUBS
  const drones = dronesResource.state.status === 'ready' ? dronesResource.state.data : NO_DRONES
  const orders = ordersResource.state.status === 'ready' ? ordersResource.state.data : NO_ORDERS
  const flightsSnapshot =
    flightsResource.state.status === 'ready' ? flightsResource.state.data : null
  const flights = flightsSnapshot?.flights ?? NO_FLIGHTS
  const workerStale = flightsSnapshot?.workerStale ?? true
  const missions =
    missionsResource.state.status === 'ready' ? missionsResource.state.data : NO_MISSIONS

  const [managementOpen, setManagementOpen] = useState(false)
  // Feature 026: the Copilot's state lives here, above the tabs, so switching tabs (or a map
  // selection that does) never loses a draft, an answer or a request still on its way.
  const copilot = useCopilot()
  // Selection, drone inspector, Operations tab and map focus (Feature 023): see useSelection.
  const {
    hasSelection,
    selectedHub,
    selectedDrone,
    selectedOrder,
    selectedHubId,
    selectedDroneId,
    selectedOrderId,
    selectHub,
    selectDrone,
    selectOrder,
    clearSelection,
    inspectorOpen,
    inspectDrone,
    closeInspector,
    operationsTab,
    setOperationsTab,
    focusRequest,
    focusNotice,
    dismissFocusNotice,
    focusHub,
    focusDrone,
    focusOrder,
  } = useSelection({
    hubs,
    drones,
    orders,
    ordersReady: ordersResource.state.status === 'ready',
  })
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

  const lprResource = useLpr()
  const randomIncidents = useRandomIncidents() // one poll, read by the Scenarios menu
  const orderSimulation = useOrderSimulation() // one poll, shared by the header switch and Management
  const rainResource = useRainWarning()
  const rainWarningActive = rainResource.state.status === 'ready' && rainResource.state.data.active
  const lprScenario = lprResource.state.status === 'ready' ? lprResource.state.data.scenario : null
  const {
    flightByDrone,
    emergencyPoints,
    droneEmergencies,
    interruptedOrderIds,
    canFailDrone,
    canMarkRecipient,
    lprView,
    yieldingDroneIds,
    flightVisuals,
  } = useFlightView({
    drones,
    flights,
    workerStale,
    flightsReceivedAt: flightsResource.receivedAt,
    flightsStale: flightsResource.stale,
    lpr: { scenario: lprScenario, receivedAt: lprResource.receivedAt, stale: lprResource.stale },
  })

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
  const refreshMissions = missionsResource.refresh
  const { activityTick, refreshAfterIncident, refreshAfterRelocation, startAssignedMission } =
    useRefreshActions({
      flights,
      refresh: {
        drones: refreshDrones,
        orders: refreshOrders,
        flights: flightsResource.refresh,
        lpr: lprResource.refresh,
        missions: refreshMissions,
        rainWarning: rainResource.refresh,
      },
    })

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
            selectedHubId={selectedHubId}
            onSelectHub={selectHub}
            drones={markerDrones}
            dockedCounts={dockedCounts}
            selectedDroneId={selectedDroneId}
            onSelectDrone={selectDrone}
            droneOffsets={droneOffsets}
            flights={flightVisuals}
            orders={orders}
            selectedOrderId={selectedOrderId}
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
            hideOnNarrow={hasSelection}
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
              hideOnNarrow={hasSelection}
            >
              {operationsTab === 'drones' && (
                <DronesList
                  drones={drones}
                  hubs={hubs}
                  selectedDroneId={selectedDroneId}
                  onSelectDrone={focusDrone}
                />
              )}
              {operationsTab === 'hubs' && (
                <HubsList
                  hubs={hubs}
                  dockedCounts={dockedCounts}
                  selectedHubId={selectedHubId}
                  onSelectHub={focusHub}
                />
              )}
              {operationsTab === 'orders' && (
                <OrdersList
                  orders={orders}
                  hubs={hubs}
                  selectedOrderId={selectedOrderId}
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
                        selectedOrderId={selectedOrderId}
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
              onInspect={() => inspectDrone(selectedDrone.id)}
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
