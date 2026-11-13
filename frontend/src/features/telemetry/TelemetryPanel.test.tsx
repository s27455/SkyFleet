import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { TelemetryInput } from './deriveTelemetry'
import { TelemetryPanel } from './TelemetryPanel'

const MODEL = {
  airframeType: 'quadcopter',
  emptyWeightKg: 9,
  maxPayloadKg: 3,
  nominalFlightTimeMin: 32,
  chargeTo80Minutes: 45,
  minBatteryReservePct: 20,
}

const IDLE: TelemetryInput = {
  droneId: 'DRN-001',
  status: 'IDLE',
  batteryPct: 90,
  model: MODEL,
  flight: null,
  parcelKg: null,
}

const FLYING: TelemetryInput = {
  ...IDLE,
  droneId: 'DRN-002',
  status: 'IN_FLIGHT',
  flight: { phase: 'OUTBOUND', progress: 0.4, batteryPct: 74 },
  parcelKg: 1.5,
}

const panel = () => screen.getByRole('region', { name: 'Simulated telemetry' })
const motorRows = () => within(panel()).getAllByRole('row').slice(1) // without the header row

describe('TelemetryPanel', () => {
  it('is labelled as simulated and says the values are estimates', () => {
    render(<TelemetryPanel input={IDLE} />)

    expect(
      within(panel()).getByRole('heading', { name: 'Simulated telemetry' }),
    ).toBeInTheDocument()
    expect(within(panel()).getByText('Simulated')).toBeInTheDocument()
    expect(
      within(panel()).getByText(/not sensor data or certified measurements/),
    ).toBeInTheDocument()
    expect(within(panel()).getByText(/reference ranges are estimates too/)).toBeInTheDocument()
    expect(
      within(panel()).getByText(/Estimated reference: temperature up to 70 °C/),
    ).toBeInTheDocument()
  })

  it('shows four motors M1..M4 with stable ids', () => {
    render(<TelemetryPanel input={IDLE} />)

    expect(motorRows().map((row) => row.getAttribute('data-component'))).toEqual([
      'motor-1',
      'motor-2',
      'motor-3',
      'motor-4',
    ])
    expect(motorRows().map((row) => within(row).getByRole('rowheader').textContent)).toEqual([
      'M1',
      'M2',
      'M3',
      'M4',
    ])
    expect(within(panel()).getByText('Motors (4 rotors)')).toBeInTheDocument()
  })

  it('shows every reading with its unit', () => {
    render(<TelemetryPanel input={FLYING} />)

    const firstMotor = motorRows()[0]
    expect(within(firstMotor).getByText(/\d+\.\d °C/)).toBeInTheDocument()
    expect(within(firstMotor).getByText(/[\d,]+ RPM/)).toBeInTheDocument()
    expect(within(panel()).getByText(/^\d+\.\d V$/)).toBeInTheDocument()
    expect(within(panel()).getByText(/^\d+\.\d A/)).toBeInTheDocument()
    expect(within(panel()).getByText(/^[\d,.]+ W$/)).toBeInTheDocument()
    expect(within(panel()).getByText(/^\d+% (Excellent|Good|Weak|Poor)$/)).toBeInTheDocument()
  })

  it('describes the operating mode', () => {
    const { rerender } = render(<TelemetryPanel input={IDLE} />)
    expect(within(panel()).getByText('Standby, motors off')).toBeInTheDocument()
    expect(within(motorRows()[0]).getByText('0 RPM')).toBeInTheDocument()

    rerender(<TelemetryPanel input={FLYING} />)
    expect(within(panel()).getByText('Flying, parcel on board')).toBeInTheDocument()
    expect(within(panel()).getByText('discharging')).toBeInTheDocument()

    rerender(<TelemetryPanel input={{ ...IDLE, status: 'CHARGING' }} />)
    expect(within(panel()).getByText('Charging, motors off')).toBeInTheDocument()
    expect(within(panel()).getByText('Charge current')).toBeInTheDocument()

    rerender(<TelemetryPanel input={{ ...IDLE, status: 'MAINTENANCE' }} />)
    expect(within(panel()).getByText('Maintenance, powered down')).toBeInTheDocument()
  })

  it('reports nominal health without warnings for ordinary readings', () => {
    render(<TelemetryPanel input={FLYING} />)

    expect(within(panel()).getByText('Nominal')).toBeInTheDocument()
    expect(
      within(panel()).queryByRole('list', { name: 'Telemetry warnings' }),
    ).not.toBeInTheDocument()
  })

  it('warns from the real battery level against the real reserve', () => {
    render(
      <TelemetryPanel
        input={{ ...FLYING, flight: { phase: 'RETURNING', progress: 0.8, batteryPct: 8 } }}
      />,
    )

    expect(within(panel()).getByText('Critical')).toBeInTheDocument()
    const warnings = within(panel()).getByRole('list', { name: 'Telemetry warnings' })
    expect(
      within(warnings).getByText(/Charge 8% is at or below the 10% critical threshold/),
    ).toBeInTheDocument()
  })

  it('an attention level is stated in words, not only by colour', () => {
    render(<TelemetryPanel input={{ ...IDLE, batteryPct: 18 }} />)

    expect(within(panel()).getByText('Attention')).toBeInTheDocument()
    expect(
      within(panel()).getByText(/Charge 18% is at or below the 20% attention threshold/),
    ).toBeInTheDocument()
  })

  it('says motor telemetry is unavailable for an unknown airframe instead of inventing motors', () => {
    render(<TelemetryPanel input={{ ...IDLE, model: { ...MODEL, airframeType: 'octocopter' } }} />)

    expect(within(panel()).getByText('Not available for this airframe.')).toBeInTheDocument()
    expect(within(panel()).queryByRole('table')).not.toBeInTheDocument()
    expect(within(panel()).getByText(/"octocopter"/)).toBeInTheDocument()
    // The battery and connectivity estimates do not depend on the rotor count.
    expect(within(panel()).getByText('Battery')).toBeInTheDocument()
  })

  it('states the limits of an estimate made without flight data', () => {
    render(<TelemetryPanel input={{ ...FLYING, flight: null }} />)

    expect(within(panel()).getByText(/Flight data is not available/)).toBeInTheDocument()
  })

  it('shows exactly the same values after a re-render with the same drone state', () => {
    const { rerender } = render(<TelemetryPanel input={FLYING} />)
    const before = panel().textContent

    rerender(<TelemetryPanel input={{ ...FLYING, flight: { ...FLYING.flight! } }} />)

    expect(panel().textContent).toBe(before)
  })

  it('changes the readings when the real state changes', () => {
    const { rerender } = render(<TelemetryPanel input={FLYING} />)
    const before = panel().textContent

    rerender(<TelemetryPanel input={{ ...FLYING, parcelKg: 3 }} />)

    expect(panel().textContent).not.toBe(before)
  })
})

describe('TelemetryPanel selection', () => {
  it('is read-only without a selection handler', () => {
    render(<TelemetryPanel input={FLYING} />)

    expect(within(panel()).queryByRole('button')).not.toBeInTheDocument()
  })

  it('selects a motor or the battery from the list, and the same control clears it', () => {
    const onSelect = vi.fn()
    const { rerender } = render(<TelemetryPanel input={FLYING} onSelect={onSelect} />)

    fireEvent.click(within(panel()).getByRole('button', { name: 'Select motor M3' }))
    expect(onSelect).toHaveBeenLastCalledWith('motor-3')
    fireEvent.click(within(panel()).getByRole('button', { name: 'Select battery' }))
    expect(onSelect).toHaveBeenLastCalledWith('battery')

    rerender(<TelemetryPanel input={FLYING} selected="motor-3" onSelect={onSelect} />)
    fireEvent.click(within(panel()).getByRole('button', { name: 'Select motor M3' }))
    expect(onSelect).toHaveBeenLastCalledWith(null)
  })

  it('shows which component is selected, in the accessibility tree and visually', () => {
    render(<TelemetryPanel input={FLYING} selected="motor-2" onSelect={() => {}} />)

    expect(within(panel()).getByRole('button', { name: 'Select motor M2' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(within(panel()).getByRole('button', { name: 'Select motor M1' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(within(panel()).getByRole('button', { name: 'Select battery' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(motorRows()[1]).toHaveClass('bg-surface-raised')
  })

  it('has a button per motor of the airframe and none when motor telemetry is unavailable', () => {
    const { rerender } = render(<TelemetryPanel input={IDLE} onSelect={() => {}} />)
    expect(within(panel()).getAllByRole('button', { name: /Select motor/ })).toHaveLength(4)

    rerender(
      <TelemetryPanel
        input={{ ...IDLE, model: { ...MODEL, airframeType: 'octocopter' } }}
        onSelect={() => {}}
      />,
    )
    expect(within(panel()).queryByRole('button', { name: /Select motor/ })).not.toBeInTheDocument()
    expect(within(panel()).getByRole('button', { name: 'Select battery' })).toBeInTheDocument()
  })
})
