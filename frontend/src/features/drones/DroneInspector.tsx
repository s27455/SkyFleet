import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'

import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { Drone3DViewer, type DronePartId } from '../drone3d'
import { FlightSection } from '../flights/FlightSection'
import { usePrefersReducedMotion } from '../flights/usePrefersReducedMotion'
import { ORDER_STATUS_DISPLAY } from '../orders/orderStatus'
import { nearestHubName } from '../hubs/nearestHub'
import { DRONE_STATUS_DISPLAY } from './droneStatus'
import type { InspectorData, Lookup } from './inspectorData'
import { useDialogFocus } from './useDialogFocus'
import { annotationsFor } from '../telemetry/componentHealth'
import { ComponentDetail } from '../telemetry/ComponentDetail'
import type { TelemetryInput } from '../telemetry/deriveTelemetry'
import { TelemetryPanel } from '../telemetry/TelemetryPanel'
import {
  MODEL_PART_FOR_COMPONENT,
  componentForPart,
  type SelectableComponentId,
} from '../telemetry/telemetryConfig'
import { useStableValue, useTelemetry } from '../telemetry/useTelemetry'

/** Length of the exit animation; the dialog unmounts when it ends. Keep in sync with index.css. */
const EXIT_MS = 150

const VIEWER_CLASS = 'h-[38dvh] min-h-64 w-full lg:h-[min(58dvh,34rem)]'

interface DroneInspectorProps {
  drone: Drone
  hubs: readonly Hub[]
  /** The drone's flight, mission and payload as far as the backend data allows. */
  data: InspectorData
  /** True when the simulation worker has stopped updating flights. */
  workerStale: boolean
  /** True when a refresh failed and older data is still shown. */
  dataStale: boolean
  onClose: () => void
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg border border-line bg-surface p-4">
      <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">{title}</h3>
      {children}
    </section>
  )
}

const UNAVAILABLE_TEXT = {
  loading: 'Loading…',
  error: 'Unavailable: this data could not be read.',
  missing: 'Unavailable: not found in the current data.',
} as const

/** Says what is known, "none" text when the backend confirmed nothing is there, or why it is unknown. */
function Unknown({ lookup, none }: { lookup: Lookup<unknown>; none: string }) {
  if (lookup.kind === 'found') return null
  return (
    <p className="mt-2 text-sm text-fg-muted">
      {lookup.kind === 'none' ? none : UNAVAILABLE_TEXT[lookup.reason]}
    </p>
  )
}

function BatteryBar({ percent }: { percent: number }) {
  return (
    <div
      role="progressbar"
      aria-label="Battery"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="h-1.5 w-24 overflow-hidden rounded-full bg-line"
    >
      <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
    </div>
  )
}

/**
 * The drone technical inspector: a large overlay above the map (which stays mounted underneath, so
 * polling and the simulation are unaffected) with the 3D model and the drone's real backend data.
 * It owns no data and fetches nothing; closing it hands control back to the selected drone's panel.
 */
export function DroneInspector({
  drone,
  hubs,
  data,
  workerStale,
  dataStale,
  onClose,
}: DroneInspectorProps) {
  const dialog = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const reducedMotion = usePrefersReducedMotion()
  const [closing, setClosing] = useState(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  // The selected component belongs to one drone: switching drones starts with nothing selected.
  const [selection, setSelection] = useState<{
    droneId: string
    component: SelectableComponentId
  } | null>(null)

  useDialogFocus(dialog)

  const requestClose = useCallback(() => {
    if (closeTimer.current !== undefined) return
    if (reducedMotion) {
      onClose()
      return
    }
    setClosing(true)
    closeTimer.current = setTimeout(onClose, EXIT_MS)
  }, [onClose, reducedMotion])

  useEffect(() => () => clearTimeout(closeTimer.current), [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        requestClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [requestClose])

  const status = DRONE_STATUS_DISPLAY[drone.status]
  const { model } = drone
  const [longitude, latitude] = drone.coordinates
  const hubName = (id: string) => hubs.find((candidate) => candidate.id === id)?.name ?? id
  const { flight, mission, payload } = data
  // The simulated telemetry is estimated from the real state shown on this page, nothing else.
  const telemetryInput: TelemetryInput = {
    droneId: drone.id,
    status: drone.status,
    batteryPct: drone.batteryPct,
    model,
    flight:
      flight.kind === 'found'
        ? {
            phase: flight.value.phase,
            progress: flight.value.progress,
            batteryPct: flight.value.batteryPct,
          }
        : null,
    parcelKg: payload.kind === 'found' ? payload.value.packageWeightKg : null,
  }
  const { readings, health, statuses } = useTelemetry(telemetryInput)
  // The model draws exactly the levels the telemetry panel states; the object only changes when a
  // label or level does, so live refreshes never touch the scene.
  const annotations = useStableValue(useMemo(() => annotationsFor(statuses), [statuses]))
  const selectedComponent =
    selection?.droneId === drone.id && statuses[selection.component] ? selection.component : null
  const selectedStatus = selectedComponent ? (statuses[selectedComponent] ?? null) : null
  const selectedPart = selectedComponent
    ? (MODEL_PART_FOR_COMPONENT[selectedComponent] ?? null)
    : null

  const selectComponent = useCallback(
    (component: SelectableComponentId | null) =>
      setSelection(component ? { droneId: drone.id, component } : null),
    [drone.id],
  )
  const selectPart = useCallback(
    (part: DronePartId | null) => {
      const component = part ? componentForPart(part) : undefined
      selectComponent(component ?? null)
    },
    [selectComponent],
  )

  return (
    <div
      ref={dialog}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      className={`absolute inset-0 z-40 flex flex-col overflow-hidden bg-canvas/95 backdrop-blur-sm focus:outline-none sm:inset-3 sm:rounded-lg sm:border sm:border-line ${
        closing ? 'inspector-exit' : 'inspector-enter'
      }`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3 sm:px-6">
        <div>
          <h2 id={titleId} className="text-lg font-semibold">
            {drone.id}
          </h2>
          <p className="text-sm text-fg-muted">{model.name}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 sm:gap-4">
          <span className="whitespace-nowrap">
            <StatusIndicator tone={status.tone} label={status.label} />
          </span>
          <button
            type="button"
            data-autofocus
            onClick={requestClose}
            aria-label="Close inspector"
            className="inline-flex min-h-10 items-center rounded-md border border-line px-3 text-sm hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
          >
            Close
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {dataStale && (
          <p
            role="status"
            className="mb-4 rounded-lg border border-line bg-surface p-3 text-sm text-fg-muted"
          >
            The latest refresh failed. The data below is the last known and may be outdated.
          </p>
        )}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_24rem] lg:grid-rows-[auto_1fr] lg:items-start">
          <div className="relative min-w-0 lg:col-start-1 lg:row-start-1">
            <Drone3DViewer
              className={VIEWER_CLASS}
              annotations={annotations}
              selectedPart={selectedPart}
              onPartSelect={selectPart}
            />
            <p className="pointer-events-none absolute top-2 left-3 text-xs text-fg-muted">
              Illustrative model; highlights show simulated telemetry
            </p>
            <ComponentDetail
              status={selectedStatus}
              readings={readings}
              onClear={() => selectComponent(null)}
              className="mt-4"
            />
          </div>

          <div className="flex min-w-0 flex-col gap-4 lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <Section title="Operational">
              <dl className="mt-2 space-y-2 text-sm">
                <Row label="Battery">
                  <span className="flex items-center justify-end gap-2">
                    <BatteryBar percent={drone.batteryPct} />
                    <span className="w-10 font-mono tabular-nums">{drone.batteryPct}%</span>
                  </span>
                </Row>
                <Row label="Hub">{nearestHubName(drone.coordinates, hubs)}</Row>
                <Row label="Stored position">
                  <span className="font-mono text-xs tabular-nums">
                    {latitude.toFixed(6)}, {longitude.toFixed(6)}
                  </span>
                </Row>
              </dl>
            </Section>

            {flight.kind === 'found' ? (
              // FlightSection brings its own heading; only its top spacing is dropped here.
              <div className="rounded-lg border border-line bg-surface px-4 pb-4 [&>section]:mt-0 [&>section]:border-t-0">
                <FlightSection flight={flight.value} hubs={hubs} workerStale={workerStale} />
              </div>
            ) : (
              <Section title="Flight">
                <Unknown lookup={flight} none="No active flight." />
              </Section>
            )}

            <Section title="Mission">
              {mission.kind === 'found' ? (
                <dl className="mt-2 space-y-2 text-sm">
                  <Row label="Mission">
                    <span className="font-mono">{mission.value.id}</span>
                  </Row>
                  <Row label="Status">{mission.value.status}</Row>
                  <Row label="Planned return Hub">
                    {mission.value.returnHubId ? hubName(mission.value.returnHubId) : '—'}
                  </Row>
                  <Row label="Route length">
                    {mission.value.totalKm === undefined ? '—' : `${mission.value.totalKm} km`}
                  </Row>
                </dl>
              ) : (
                <Unknown lookup={mission} none="No active mission." />
              )}
            </Section>

            <Section title="Payload">
              {payload.kind === 'found' ? (
                <dl className="mt-2 space-y-2 text-sm">
                  <Row label="Parcel weight">{payload.value.packageWeightKg} kg</Row>
                  <Row label="Order">
                    <span className="font-mono">{payload.value.id}</span>
                  </Row>
                  <Row label="Order status">{ORDER_STATUS_DISPLAY[payload.value.status].label}</Row>
                  <Row label="Destination">{payload.value.destinationAddress}</Row>
                </dl>
              ) : (
                <Unknown lookup={payload} none="No parcel assigned." />
              )}
            </Section>

            <Section title="Model specification">
              <dl className="mt-2 space-y-2 text-sm">
                <Row label="Airframe">{model.airframeType}</Row>
                <Row label="Empty weight">{model.emptyWeightKg} kg</Row>
                <Row label="Maximum payload">{model.maxPayloadKg} kg</Row>
                <Row label="Cruise / maximum speed">
                  {model.cruiseSpeedKmh} / {model.maxSpeedKmh} km/h
                </Row>
                <Row label="Maximum total flight distance">{model.maxRangeKm} km</Row>
                <Row label="Conservative mission distance">
                  {model.recommendedMissionRangeKm} km
                </Row>
                <Row label="Nominal flight time">{model.nominalFlightTimeMin} min</Row>
                <Row label="Minimum battery reserve">{model.minBatteryReservePct}%</Row>
                <Row label="Charge to 80%">{model.chargeTo80Minutes} min</Row>
                <Row label="Maximum wind">{model.maxWindMps} m/s</Row>
              </dl>
            </Section>
          </div>
          {/* Simulated telemetry (016C): estimates from the real state above, labelled as such. */}
          <TelemetryPanel
            input={telemetryInput}
            readings={readings}
            health={health}
            selected={selectedComponent}
            onSelect={selectComponent}
            className="lg:col-start-1 lg:row-start-2"
          />
        </div>
        <p className="mt-4 text-xs text-fg-muted">
          Backend snapshot, refreshed about every 2 seconds; flights are simulated. Specifications
          are simulation assumptions.
        </p>
      </div>
    </div>
  )
}
