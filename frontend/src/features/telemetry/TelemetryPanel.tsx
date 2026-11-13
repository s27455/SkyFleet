import { useMemo, type ReactNode } from 'react'

import { StatusIndicator } from '../../components/ui/StatusIndicator'
import {
  assessHealth,
  deriveTelemetry,
  motorTemperatureLevel,
  type HealthAssessment,
  type OperatingMode,
  type TelemetryInput,
  type TelemetryReadings,
} from './deriveTelemetry'
import { LEVEL_DISPLAY, integer, power } from './format'
import { REFERENCE, type SelectableComponentId } from './telemetryConfig'

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

const SELECT_BUTTON_CLASS =
  'inline-flex min-h-10 items-center rounded-md px-2 -mx-2 text-left hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent aria-pressed:bg-surface-raised aria-pressed:text-accent'

interface TelemetryPanelProps {
  /** The drone's real state, from which every reading is estimated. */
  input: TelemetryInput
  /**
   * The readings and health to show, when the parent already derived (and eased) them, so that the
   * numbers, the details and the 3D highlights come from one source. Without them the panel derives
   * its own from `input`.
   */
  readings?: TelemetryReadings
  health?: HealthAssessment
  /** The selected component. Selection is shared with the 3D model by the parent. */
  selected?: SelectableComponentId | null
  /** When given, motors and the battery can be selected (again to clear). */
  onSelect?: (component: SelectableComponentId | null) => void
  className?: string
}

/**
 * Simulated component telemetry for the inspector. Everything here is an estimate derived from the
 * drone's real state (see `deriveTelemetry`); it is labelled as simulated and never read from or
 * written to the backend.
 */
export function TelemetryPanel({
  input,
  readings: shownReadings,
  health: shownHealth,
  selected = null,
  onSelect,
  className = '',
}: TelemetryPanelProps) {
  const toggle = (component: SelectableComponentId) =>
    onSelect?.(selected === component ? null : component)
  const { readings, health } = useMemo(() => {
    if (shownReadings && shownHealth) return { readings: shownReadings, health: shownHealth }
    const derived = deriveTelemetry(input)
    return { readings: derived, health: assessHealth(derived, input.model.minBatteryReservePct) }
  }, [input, shownReadings, shownHealth])

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
                  <tr
                    key={motor.id}
                    data-component={motor.id}
                    className={`border-t border-line ${selected === motor.id ? 'bg-surface-raised' : ''}`}
                  >
                    <th scope="row" className="py-1 text-left font-medium">
                      {onSelect ? (
                        <button
                          type="button"
                          aria-pressed={selected === motor.id}
                          aria-label={`Select motor ${motor.label}`}
                          onClick={() => toggle(motor.id)}
                          className={SELECT_BUTTON_CLASS}
                        >
                          {motor.label}
                        </button>
                      ) : (
                        motor.label
                      )}
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

      <h4 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">
        {onSelect ? (
          <button
            type="button"
            aria-pressed={selected === 'battery'}
            aria-label="Select battery"
            onClick={() => toggle('battery')}
            className={`${SELECT_BUTTON_CLASS} uppercase`}
          >
            Battery
          </button>
        ) : (
          'Battery'
        )}
      </h4>
      <dl
        data-component="battery"
        className={`mt-2 space-y-2 rounded-md text-sm ${selected === 'battery' ? 'bg-surface-raised' : ''}`}
      >
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
