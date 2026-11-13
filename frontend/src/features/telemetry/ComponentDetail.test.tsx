import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { componentStatuses } from './componentHealth'
import { ComponentDetail } from './ComponentDetail'
import {
  assessHealth,
  deriveTelemetry,
  type TelemetryInput,
  type TelemetryReadings,
} from './deriveTelemetry'

const MODEL = {
  airframeType: 'quadcopter',
  emptyWeightKg: 9,
  maxPayloadKg: 3,
  nominalFlightTimeMin: 32,
  chargeTo80Minutes: 45,
  minBatteryReservePct: 20,
}

const FLYING: TelemetryInput = {
  droneId: 'DRN-002',
  status: 'IN_FLIGHT',
  batteryPct: 76,
  model: MODEL,
  flight: { phase: 'OUTBOUND', progress: 0.4, batteryPct: 74 },
  parcelKg: 1.5,
}

function setup(
  select: 'motor-1' | 'motor-2' | 'battery' | null,
  input: TelemetryInput = FLYING,
  tweak: (readings: TelemetryReadings) => TelemetryReadings = (readings) => readings,
) {
  const readings = tweak(deriveTelemetry(input))
  const statuses = componentStatuses(readings, assessHealth(readings, MODEL.minBatteryReservePct))
  const onClear = vi.fn()
  render(
    <ComponentDetail
      status={select ? (statuses[select] ?? null) : null}
      readings={readings}
      onClear={onClear}
    />,
  )
  return { readings, onClear }
}

const region = () => screen.getByRole('region', { name: 'Component details' })

describe('ComponentDetail', () => {
  it('invites a selection when nothing is selected', () => {
    setup(null)

    expect(within(region()).getByText(/Select a motor or the battery/)).toBeInTheDocument()
    expect(within(region()).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows a motor with its position, readings, estimates labelling and findings', () => {
    const { readings } = setup('motor-2')
    const motor = readings.motors![1]

    expect(within(region()).getByRole('heading', { name: 'Motor M2 (front right)' })).toBeVisible()
    expect(within(region()).getByText(`${motor.temperatureC.toFixed(1)} °C`)).toBeInTheDocument()
    expect(within(region()).getByText(/[\d,]+ RPM$/)).toBeInTheDocument()
    expect(within(region()).getByText(/Simulated estimates, not measurements/)).toBeInTheDocument()
    expect(within(region()).getByText(/Estimated reference up to 70 °C/)).toBeInTheDocument()
    expect(within(region()).getByText('Nominal')).toBeInTheDocument()
    const findings = within(region()).getByRole('list', { name: 'Component findings' })
    expect(within(findings).getByText(/within the 70 °C reference/)).toBeInTheDocument()
  })

  it('states a warning in words, with the reading and the threshold', () => {
    setup('motor-1', FLYING, (readings) => ({
      ...readings,
      motors: readings.motors!.map((m, i) => (i === 0 ? { ...m, temperatureC: 91.2 } : m)),
    }))

    expect(within(region()).getByText('Critical', { selector: 'span' })).toBeInTheDocument()
    expect(
      within(region()).getByText(/M1 at 91.2 °C is above the 85 °C critical threshold/),
    ).toBeInTheDocument()
  })

  it('says motors are off when the drone is not flying', () => {
    setup('motor-1', { ...FLYING, status: 'CHARGING', flight: null, parcelKg: null })

    expect(within(region()).getByText('Motors are off while charging.')).toBeInTheDocument()
    expect(within(region()).getByText('0 RPM')).toBeInTheDocument()
  })

  it('shows the battery, with its real charge and both findings', () => {
    setup('battery', {
      ...FLYING,
      flight: { ...FLYING.flight!, batteryPct: 8 },
    })

    expect(within(region()).getByRole('heading', { name: 'Battery' })).toBeVisible()
    expect(within(region()).getByText('8%')).toBeInTheDocument()
    expect(within(region()).getByText(/^\d+\.\d V$/)).toBeInTheDocument()
    expect(within(region()).getByText('Critical', { selector: 'span' })).toBeInTheDocument()
    const findings = within(region()).getByRole('list', { name: 'Component findings' })
    expect(within(findings).getAllByRole('listitem')).toHaveLength(2)
    expect(
      within(findings).getByText(/Charge 8% is at or below the 10% critical threshold/),
    ).toBeInTheDocument()
  })

  it('clears the selection with its own button', () => {
    const { onClear } = setup('battery')

    fireEvent.click(within(region()).getByRole('button', { name: 'Clear selection' }))

    expect(onClear).toHaveBeenCalledTimes(1)
  })
})
