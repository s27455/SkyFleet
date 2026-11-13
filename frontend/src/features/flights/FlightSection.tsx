import type { ReactNode } from 'react'

import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import { EMERGENCY_REASON_TEXT, FLIGHT_PHASE_DISPLAY } from './flightStatus'

interface FlightSectionProps {
  flight: Flight
  hubs: readonly Hub[]
  /** True when the worker has stopped updating: the figures below are the last known ones. */
  workerStale: boolean
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

function Bar({ value, label }: { value: number; label: string }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 100))
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="h-1.5 w-24 overflow-hidden rounded-full bg-line"
    >
      <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
    </div>
  )
}

/** The backend-reported flight of a drone: phase, progress, battery and the Hub it is heading to. */
export function FlightSection({ flight, hubs, workerStale }: FlightSectionProps) {
  const recalled = flight.recalledAt !== null
  // A recall is a return like any other to the flight model, so say so in words.
  const phase =
    recalled && flight.phase !== 'LANDED' && flight.phase !== 'EMERGENCY'
      ? { tone: 'warning' as const, label: 'Recalled: returning with the parcel' }
      : FLIGHT_PHASE_DISPLAY[flight.phase]
  const hubName = (id: string) => hubs.find((hub) => hub.id === id)?.name ?? id
  const diverted = flight.landingTargetHubId !== flight.plannedReturnHubId
  const emergency = flight.emergency

  return (
    <section aria-label="Flight" className="mt-4 border-t border-line pt-3">
      <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">Flight</h3>
      <dl className="mt-2 space-y-2 text-sm">
        <Row label="Phase">
          <StatusIndicator tone={phase.tone} label={phase.label} />
        </Row>
        <Row label="Mission">
          <span className="font-mono">{flight.missionId}</span> ({flight.missionStatus})
        </Row>
        <Row label="Progress">
          <span className="flex items-center justify-end gap-2">
            <Bar value={flight.progress * 100} label="Flight progress" />
            <span className="w-10 font-mono tabular-nums">
              {Math.round(flight.progress * 100)}%
            </span>
          </span>
        </Row>
        <Row label="Flight battery">
          <span className="flex items-center justify-end gap-2">
            <Bar value={flight.batteryPct} label="Flight battery" />
            <span className="w-10 font-mono tabular-nums">{flight.batteryPct}%</span>
          </span>
        </Row>
        {flight.target && !emergency && (
          <Row label="Next point in">
            <span className="font-mono tabular-nums">
              about {Math.max(Math.ceil(flight.target.etaS - flight.snapshotAgeS), 0)} s
            </span>
          </Row>
        )}
        <Row label="Planned return Hub">{hubName(flight.plannedReturnHubId)}</Row>
        {recalled && !emergency && (
          <Row label="Recalled">
            <span>Returning with the parcel to {hubName(flight.landingTargetHubId)}</span>
          </Row>
        )}
        {diverted && !recalled && !emergency && (
          <Row label="Now heading to">{hubName(flight.landingTargetHubId)}</Row>
        )}
      </dl>
      {workerStale && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          The simulation worker has stopped updating this flight; the figures above are the last
          known ones.
        </p>
      )}
      {emergency && (
        <p className="mt-2 rounded-md border border-line bg-canvas p-2 text-xs">
          Simulated emergency: {EMERGENCY_REASON_TEXT[emergency.reason]}. The flight ended at{' '}
          {emergency.position[1].toFixed(5)}, {emergency.position[0].toFixed(5)} and the drone is
          out of service (maintenance). This is a simulation outcome, not a computed safe landing
          site.
        </p>
      )}
    </section>
  )
}
