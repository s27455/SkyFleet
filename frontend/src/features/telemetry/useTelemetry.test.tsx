import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { annotationsFor } from './componentHealth'
import type { TelemetryInput } from './deriveTelemetry'
import { useTelemetry } from './useTelemetry'

const MODEL = {
  airframeType: 'quadcopter',
  emptyWeightKg: 9,
  maxPayloadKg: 3,
  nominalFlightTimeMin: 32,
  chargeTo80Minutes: 45,
  minBatteryReservePct: 20,
}

const IDLE: TelemetryInput = {
  droneId: 'DRN-002',
  status: 'IDLE',
  batteryPct: 80,
  model: MODEL,
  flight: null,
  parcelKg: null,
}
const FLYING: TelemetryInput = {
  ...IDLE,
  status: 'IN_FLIGHT',
  flight: { phase: 'OUTBOUND', progress: 0.6, batteryPct: 78 },
  parcelKg: 1.5,
}

describe('useTelemetry', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', () => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame'] })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('hands out the very same objects when a poll brings the same state in new objects', () => {
    const { result, rerender } = renderHook(({ input }) => useTelemetry(input), {
      initialProps: { input: FLYING },
    })
    const first = result.current

    rerender({ input: { ...FLYING, model: { ...MODEL }, flight: { ...FLYING.flight! } } })

    expect(result.current.readings).toBe(first.readings)
    expect(result.current.health).toBe(first.health)
    expect(result.current.statuses).toBe(first.statuses)
  })

  it('judges health and the components on the shown readings, which ease after landing', () => {
    const { result, rerender } = renderHook(({ input }) => useTelemetry(input), {
      initialProps: { input: FLYING },
    })
    const flyingTemperature = result.current.readings.motors![0].temperatureC

    rerender({ input: IDLE })
    act(() => void vi.advanceTimersByTime(1000))

    // Mid-way down: the shown temperature is between flying and standby, and the status text is
    // built from exactly that number.
    const shown = result.current.readings.motors![0].temperatureC
    expect(shown).toBeLessThan(flyingTemperature)
    expect(shown).toBeGreaterThan(30)
    expect(result.current.statuses['motor-1']!.findings[0].detail).toContain(shown.toFixed(1))
    expect(result.current.health.indicators.find((i) => i.id === 'motors')!.detail).toContain(
      result.current.readings
        .motors!.reduce((a, b) => (b.temperatureC > a.temperatureC ? b : a))
        .temperatureC.toFixed(1),
    )
  })

  it('drives the 3D annotations from the same statuses as the panel', () => {
    const { result } = renderHook(() => useTelemetry(FLYING))

    const annotations = annotationsFor(result.current.statuses)

    expect(annotations['motor-fl']).toEqual({
      label: 'M1',
      level: result.current.statuses['motor-1']!.level,
    })
    expect(annotations.battery).toEqual({
      label: 'Battery',
      level: result.current.statuses.battery!.level,
    })
  })
})
