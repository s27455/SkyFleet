import { describe, expect, it } from 'vitest'

import { annotationsFor, componentStatuses } from './componentHealth'
import {
  assessHealth,
  deriveTelemetry,
  type TelemetryInput,
  type TelemetryReadings,
} from './deriveTelemetry'
import { componentForPart, MODEL_PART_FOR_COMPONENT } from './telemetryConfig'

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

function statusesOf(readings: TelemetryReadings, reserve = 20) {
  return componentStatuses(readings, assessHealth(readings, reserve))
}

function withMotorTemperature(readings: TelemetryReadings, index: number, temperatureC: number) {
  return {
    ...readings,
    motors: readings.motors!.map((m, i) => (i === index ? { ...m, temperatureC } : m)),
  }
}

describe('componentStatuses', () => {
  it('has one status per motor of the airframe, with stable ids, and the battery', () => {
    const statuses = statusesOf(deriveTelemetry(FLYING))

    expect(Object.keys(statuses)).toEqual(['motor-1', 'motor-2', 'motor-3', 'motor-4', 'battery'])
    expect(statuses['motor-3']).toMatchObject({ label: 'M3', name: 'Motor M3 (rear right)' })
    expect(statuses.battery).toMatchObject({ label: 'Battery', name: 'Battery' })
  })

  it('has only the battery when the airframe has no motor telemetry', () => {
    const readings = deriveTelemetry({ ...FLYING, model: { ...MODEL, airframeType: 'octocopter' } })

    expect(Object.keys(statusesOf(readings))).toEqual(['battery'])
  })

  it('judges every motor by its own temperature, at exactly the explicit thresholds', () => {
    const base = deriveTelemetry(FLYING)
    const level = (temperatureC: number) =>
      statusesOf(withMotorTemperature(base, 1, temperatureC))['motor-2']!.level

    expect(level(70)).toBe('nominal') // above, not at
    expect(level(70.1)).toBe('attention')
    expect(level(85)).toBe('attention')
    expect(level(85.1)).toBe('critical')
  })

  it('flags only the motor that crossed a threshold, and says why in words', () => {
    const readings = withMotorTemperature(deriveTelemetry(FLYING), 1, 78.4)
    const statuses = statusesOf(readings)

    expect(statuses['motor-1']!.level).toBe('nominal')
    expect(statuses['motor-2']!.level).toBe('attention')
    expect(statuses['motor-2']!.findings[0].detail).toBe(
      'M2 at 78.4 °C is above the 70 °C attention threshold.',
    )
    expect(statuses['motor-3']!.level).toBe('nominal')
  })

  it('always has a finding per judged reading, nominal ones included', () => {
    const statuses = statusesOf(deriveTelemetry(FLYING))

    expect(statuses['motor-1']!.findings).toHaveLength(1)
    expect(statuses['motor-1']!.findings[0].detail).toMatch(/within the 70 °C reference/)
    expect(statuses.battery!.findings.map((finding) => finding.id)).toEqual([
      'battery-charge',
      'battery-temperature',
    ])
  })

  it('judges the battery by the worse of its charge and temperature', () => {
    const critical = statusesOf(
      deriveTelemetry({ ...FLYING, flight: { ...FLYING.flight!, batteryPct: 8 } }),
    )
    expect(critical.battery!.level).toBe('critical')

    const attention = statusesOf(
      deriveTelemetry({ ...FLYING, flight: { ...FLYING.flight!, batteryPct: 18 } }),
    )
    expect(attention.battery!.level).toBe('attention')

    const hotBattery = deriveTelemetry(FLYING)
    const overheated = statusesOf({
      ...hotBattery,
      battery: { ...hotBattery.battery, temperatureC: 56 },
    })
    expect(overheated.battery!.level).toBe('critical')
  })

  it('is deterministic: the same readings give the same statuses', () => {
    expect(statusesOf(deriveTelemetry(FLYING))).toEqual(statusesOf(deriveTelemetry(FLYING)))
  })
})

describe('annotationsFor', () => {
  it('maps statuses onto the model parts that exist, with labels and levels', () => {
    const readings = withMotorTemperature(deriveTelemetry(FLYING), 0, 90)
    const annotations = annotationsFor(statusesOf(readings))

    expect(Object.keys(annotations).sort()).toEqual(
      ['battery', 'motor-fl', 'motor-fr', 'motor-rl', 'motor-rr'].sort(),
    )
    expect(annotations['motor-fl']).toEqual({ label: 'M1', level: 'critical' })
    expect(annotations['motor-fr']).toEqual({ label: 'M2', level: 'nominal' })
    expect(annotations.battery).toEqual({ label: 'Battery', level: 'nominal' })
  })

  it('draws no motors for an airframe without motor telemetry', () => {
    const readings = deriveTelemetry({ ...FLYING, model: { ...MODEL, airframeType: 'octocopter' } })

    expect(Object.keys(annotationsFor(statusesOf(readings)))).toEqual(['battery'])
  })
})

describe('part mapping', () => {
  it('maps model parts back to the components they stand for', () => {
    expect(componentForPart('motor-fl')).toBe('motor-1')
    expect(componentForPart('motor-fr')).toBe('motor-2')
    expect(componentForPart('motor-rr')).toBe('motor-3')
    expect(componentForPart('motor-rl')).toBe('motor-4')
    expect(componentForPart('battery')).toBe('battery')
  })

  it('has no component for the parts that are not diagnosed', () => {
    expect(componentForPart('fuselage')).toBeUndefined()
    expect(componentForPart('cargo-bay')).toBeUndefined()
    expect(componentForPart('landing-gear')).toBeUndefined()
  })

  it('round-trips every mapped component', () => {
    for (const [component, part] of Object.entries(MODEL_PART_FOR_COMPONENT)) {
      expect(componentForPart(part)).toBe(component)
    }
  })
})
