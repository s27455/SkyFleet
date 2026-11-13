import { useMemo, type ReactNode } from 'react'

import { StatusIndicator, type StatusTone } from '../../components/ui/StatusIndicator'
import {
  assessHealth,
  deriveTelemetry,
  motorTemperatureLevel,
  type HealthLevel,
  type OperatingMode,
  type TelemetryInput,
} from './deriveTelemetry'
import { REFERENCE } from './telemetryConfig'

const LEVEL_DISPLAY: Record<HealthLevel, { tone: StatusTone; label: string }> = {
  nominal: { tone: 'ok', label: 'Nominal' },
  attention: { tone: 'warning', label: 'Attention' },
  critical: { tone: 'critical', label: 'Critical' },
}

const MODE_TEXT: Record<OperatingMode, string> = {
  standby: 'Standby, motors off',
  flight: 'Flying',
  charging: 'Charging, motors off',
  maintenance: 'Maintenance, powered down',
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-fg-muted">
        {label}
        {hint && <span className="block text-xs">{hint}</span>}
      </dt>
      <dd className="text-right font-mono tabular-nums">{children}</dd>
    </div>
  )
}

const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const power = (watts: number) =>
  watts >= 100 ? `${integer.format(watts)} W` : `${watts.toFixed(1)} W`

interface TelemetryPanelProps {
  /** The drone's real state, from which every reading is estimated. */
  input: TelemetryInput
  className?: string
}

/**
 * Simulated component telemetry for the inspector. Everything here is an estimate derived from the
 * drone's real state (see `deriveTelemetry`); it is labelled as simulated and never read from or
 * written to the backend.
 */
export function TelemetryPanel({ input, className = '' }: TelemetryPanelProps) {
  const { readings, health } = useMemo(() => {
    const derived = deriveTelemetry(input)
    return { readings: derived, health: assessHealth(derived, input.model.minBatteryReservePct) }
  }, [input])

  const { battery, connectivity, motors } = readings
  const overall = LEVEL_DISPLAY[health.level]
  const direction = battery.currentDirection

  return (
    <section
      aria-label="Simulated telemetry"
      className={`min-w-0 rounded-lg border border-line bg-surface p-4 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">
          Simulated telemetry
        </h3>
        <span className="rounded border border-line px-1.5 py-0.5 text-xs font-medium tracking-wide text-accent uppercase">
          Simulated
        </span>
      </div>
      <p className="mt-2 text-xs text-fg-muted">
        Estimates derived from this drone&apos;s real status, battery, flight and parcel. They are
        not sensor data or certified measurements, and the reference ranges are estimates too.
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="text-fg-muted">Health</span>
          <StatusIndicator tone={overall.tone} label={overall.label} />
        </span>
        <span className="text-fg-muted">
          {MODE_TEXT[readings.mode]}
          {readings.carryingParcel && ', parcel on board'}
        </span>
      </div>
      {health.warnings.length > 0 && (
        <ul aria-label="Telemetry warnings" className="mt-2 space-y-1 text-sm">
          {health.warnings.map((warning) => (
            <li key={warning.id} className="rounded-md border border-line bg-canvas p-2">
              <span className="font-medium">{LEVEL_DISPLAY[warning.level].label}:</span>{' '}
              {warning.detail}
            </li>
          ))}
        </ul>
      )}
      {readings.notes.length > 0 && (
        <ul aria-label="Telemetry notes" className="mt-2 space-y-1 text-xs text-fg-muted">
          {readings.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      <h4 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">
        Motors{readings.rotorCount !== null && ` (${readings.rotorCount} rotors)`}
      </h4>
      {motors ? (
        <>
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">Simulated motor temperature and speed</caption>
            <thead>
              <tr className="text-left text-xs text-fg-muted">
                <th scope="col" className="pb-1 font-normal">
                  Motor
                </th>
                <th scope="col" className="pb-1 text-right font-normal">
                  Temperature
                </th>
                <th scope="col" className="pb-1 text-right font-normal">
                  Speed
                </th>
              </tr>
            </thead>
            <tbody>
              {motors.map((motor) => {
                const level = motorTemperatureLevel(motor.temperatureC)
                return (
                  <tr key={motor.id} data-component={motor.id} className="border-t border-line">
                    <th scope="row" className="py-1 text-left font-medium">
                      {motor.label}
                    </th>
                    <td className="py-1 text-right font-mono tabular-nums">
                      {motor.temperatureC.toFixed(1)} °C
                      {level !== 'nominal' && (
                        <span className="ml-1 font-sans text-xs">
                          ({LEVEL_DISPLAY[level].label})
                        </span>
                      )}
                    </td>
                    <td className="py-1 text-right font-mono tabular-nums">
                      {integer.format(motor.rpm)} RPM
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-fg-muted">
            Estimated reference: temperature up to {REFERENCE.motorTempC.attention} °C; speed{' '}
            {integer.format(REFERENCE.motorRpmInFlight.min)}–
            {integer.format(REFERENCE.motorRpmInFlight.max)} RPM in flight, 0 when off.
          </p>
        </>
      ) : (
        <p className="mt-2 text-sm text-fg-muted">Not available for this airframe.</p>
      )}

      <h4 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">Battery</h4>
      <dl data-component="battery" className="mt-2 space-y-2 text-sm">
        <Row
          label="Voltage"
          hint={`Reference ${REFERENCE.batteryVoltageV.min}–${REFERENCE.batteryVoltageV.max} V`}
        >
          {battery.voltageV.toFixed(1)} V
        </Row>
        <Row
          label={direction === 'charging' ? 'Charge current' : 'Current'}
          hint={`Reference up to ${REFERENCE.currentMaxA} A`}
        >
          {battery.currentA.toFixed(1)} A
          {direction === 'charging' && <span className="ml-1 font-sans text-xs">charging</span>}
          {direction === 'discharging' && (
            <span className="ml-1 font-sans text-xs">discharging</span>
          )}
        </Row>
        <Row label="Power" hint={`Reference up to ${integer.format(REFERENCE.powerMaxW)} W`}>
          {power(battery.powerW)}
        </Row>
        <Row
          label="Temperature"
          hint={`Reference ${REFERENCE.batteryTempC.min}–${REFERENCE.batteryTempC.attention} °C`}
        >
          {battery.temperatureC.toFixed(1)} °C
        </Row>
      </dl>

      <h4 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">
        Connectivity
      </h4>
      <dl data-component="connectivity" className="mt-2 space-y-2 text-sm">
        <Row
          label="Link quality"
          hint={`Reference ${REFERENCE.connectivityPct.attention}% or more`}
        >
          {connectivity.qualityPct}% {connectivity.label}
        </Row>
      </dl>
    </section>
  )
}
