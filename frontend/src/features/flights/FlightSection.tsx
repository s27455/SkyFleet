import type { ReactNode } from 'react'

import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import { EMERGENCY_REASON_TEXT, FLIGHT_PHASE_DISPLAY, isRecipientPending } from './flightStatus'

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
  const failed = flight.failedAt !== null
  const recalled = flight.recalledAt !== null && !failed
  // Feature 018D: the handover failed and the drone brings the parcel back; or it is still on its
  // way and the failure is pending until it reaches the recipient.
  const handoverFailed = flight.handoverFailedAt !== null && !failed
  const pending = isRecipientPending(flight)
  // A recall is a return like any other to the flight model, and a failure ends in the generic
  // EMERGENCY phase, so both are said in words here.
  let phase = FLIGHT_PHASE_DISPLAY[flight.phase]
  if (failed && flight.phase === 'EMERGENCY') {
    phase = { tone: 'critical', label: 'Grounded after drone failure: requires service' }
  } else if (recalled && flight.phase !== 'LANDED' && flight.phase !== 'EMERGENCY') {
    phase = { tone: 'warning', label: 'Recalled: returning with the parcel' }
  } else if (handoverFailed && flight.phase !== 'LANDED' && flight.phase !== 'EMERGENCY') {
    phase = { tone: 'warning', label: 'Delivery failed: returning with the parcel' }
  }
  const hubName = (id: string) => hubs.find((hub) => hub.id === id)?.name ?? id
  const diverted = flight.landingTargetHubId !== flight.plannedReturnHubId
  const emergency = flight.emergency
  const approaching = failed && flight.phase === 'EMERGENCY_APPROACH'

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
        {approaching && flight.target && (
          <Row label="Emergency landing point">
            <span className="font-mono text-xs tabular-nums">
              {flight.target.position[1].toFixed(5)}, {flight.target.position[0].toFixed(5)}
            </span>
          </Row>
        )}
        {pending && (
          <Row label="Recipient">
            <span>Unavailable: the delivery fails on arrival</span>
          </Row>
        )}
        {!failed && !handoverFailed && (
          <Row label="Planned return Hub">{hubName(flight.plannedReturnHubId)}</Row>
        )}
        {handoverFailed && !emergency && (
          <Row label="Returning">
            <span>With the parcel to {hubName(flight.landingTargetHubId)}</span>
          </Row>
        )}
        {recalled && !emergency && (
          <Row label="Recalled">
            <span>Returning with the parcel to {hubName(flight.landingTargetHubId)}</span>
          </Row>
        )}
        {diverted && !recalled && !handoverFailed && !failed && !emergency && (
          <Row label="Now heading to">{hubName(flight.landingTargetHubId)}</Row>
        )}
      </dl>
      {workerStale && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          The simulation worker has stopped updating this flight; the figures above are the last
          known ones.
        </p>
      )}
      {pending && (
        <p role="status" className="mt-2 rounded-md border border-status-failed p-2 text-xs">
          The recipient was reported unavailable. The drone still flies to the destination; the
          delivery fails when it arrives and the drone then returns with the parcel.
        </p>
      )}
      {handoverFailed && !emergency && (
        <p role="status" className="mt-2 rounded-md border border-status-failed p-2 text-xs">
          The recipient was unavailable, so the parcel was not delivered. The drone is bringing it
          back to a Hub.
        </p>
      )}
      {approaching && (
        <p
          role="status"
          className="mt-2 rounded-md border border-status-critical p-2 text-xs text-status-critical"
        >
          A simulated drone failure interrupted this flight. The drone no longer follows its
          delivery or recall route and is making an emergency landing.
        </p>
      )}
      {emergency && failed && (
        <p className="mt-2 rounded-md border border-status-critical p-2 text-xs">
          Drone failure: the drone made an emergency landing at {emergency.position[1].toFixed(5)},{' '}
          {emergency.position[0].toFixed(5)} and is grounded, requiring service. Its mission does
          not resume. This is a simulation outcome, not a computed safe landing site.
        </p>
      )}
      {emergency && !failed && (
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
