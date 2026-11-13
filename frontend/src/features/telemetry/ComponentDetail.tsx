import type { ReactNode } from 'react'

import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { ComponentStatus } from './componentHealth'
import type { OperatingMode, TelemetryReadings } from './deriveTelemetry'
import { LEVEL_DISPLAY, integer, power } from './format'
import { REFERENCE } from './telemetryConfig'

const MOTORS_OFF_TEXT: Partial<Record<OperatingMode, string>> = {
  standby: 'Motors are off in standby.',
  charging: 'Motors are off while charging.',
  maintenance: 'Motors are off in maintenance.',
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

interface ComponentDetailProps {
  /** The selected component, or null when nothing (or nothing that exists) is selected. */
  status: ComponentStatus | null
  readings: TelemetryReadings
  onClear: () => void
  className?: string
}

/**
 * Details of the component selected on the 3D model or in the telemetry list: its simulated
 * readings, its level in words, and what was checked. Every value is an estimate.
 */
export function ComponentDetail({
  status,
  readings,
  onClear,
  className = '',
}: ComponentDetailProps) {
  const motor = status && readings.motors?.find((candidate) => candidate.id === status.id)
  const { battery } = readings

  return (
    <section
      aria-label="Component details"
      aria-live="polite"
      className={`min-w-0 rounded-lg border border-line bg-surface p-4 ${className}`}
    >
      {!status ? (
        <p className="text-sm text-fg-muted">
          Select a motor or the battery on the model, or in the telemetry list, to see its simulated
          details.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{status.name}</h3>
            <span className="flex items-center gap-3">
              <StatusIndicator
                tone={LEVEL_DISPLAY[status.level].tone}
                label={LEVEL_DISPLAY[status.level].label}
              />
              <button
                type="button"
                onClick={onClear}
                className="inline-flex min-h-9 items-center rounded-md border border-line px-3 text-xs hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
              >
                Clear selection
              </button>
            </span>
          </div>
          <p className="mt-1 text-xs text-fg-muted">
            Simulated estimates, not measurements; reference ranges are estimates too.
          </p>

          <dl className="mt-3 space-y-2 text-sm">
            {motor ? (
              <>
                <Row
                  label="Temperature"
                  hint={`Estimated reference up to ${REFERENCE.motorTempC.attention} °C`}
                >
                  {motor.temperatureC.toFixed(1)} °C
                </Row>
                <Row
                  label="Speed"
                  hint={`Estimated reference ${integer.format(REFERENCE.motorRpmInFlight.min)}–${integer.format(REFERENCE.motorRpmInFlight.max)} RPM in flight`}
                >
                  {integer.format(motor.rpm)} RPM
                </Row>
              </>
            ) : (
              <>
                <Row label="Charge" hint="Real battery level of this drone">
                  {battery.chargePct}%
                </Row>
                <Row
                  label="Voltage"
                  hint={`Estimated reference ${REFERENCE.batteryVoltageV.min}–${REFERENCE.batteryVoltageV.max} V`}
                >
                  {battery.voltageV.toFixed(1)} V
                </Row>
                <Row
                  label={battery.currentDirection === 'charging' ? 'Charge current' : 'Current'}
                  hint={`Estimated reference up to ${REFERENCE.currentMaxA} A`}
                >
                  {battery.currentA.toFixed(1)} A
                </Row>
                <Row
                  label="Power"
                  hint={`Estimated reference up to ${integer.format(REFERENCE.powerMaxW)} W`}
                >
                  {power(battery.powerW)}
                </Row>
                <Row
                  label="Temperature"
                  hint={`Estimated reference ${REFERENCE.batteryTempC.min}–${REFERENCE.batteryTempC.attention} °C`}
                >
                  {battery.temperatureC.toFixed(1)} °C
                </Row>
              </>
            )}
          </dl>
          {motor && MOTORS_OFF_TEXT[readings.mode] && (
            <p className="mt-2 text-xs text-fg-muted">{MOTORS_OFF_TEXT[readings.mode]}</p>
          )}

          <h4 className="mt-3 text-xs font-semibold tracking-wide text-fg-muted uppercase">
            What was checked
          </h4>
          <ul aria-label="Component findings" className="mt-1 space-y-1 text-sm">
            {status.findings.map((finding) => (
              <li key={finding.id} className="rounded-md border border-line bg-canvas p-2">
                <span className="font-medium">{LEVEL_DISPLAY[finding.level].label}:</span>{' '}
                {finding.detail}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
