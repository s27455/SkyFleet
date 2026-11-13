import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { deriveTelemetry, type TelemetryInput, type TelemetryReadings } from './deriveTelemetry'
import { useSmoothedReadings } from './useSmoothedReadings'

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

const idle = deriveTelemetry(IDLE)
const flying = deriveTelemetry(FLYING)
const temperatures = (readings: TelemetryReadings) => [
  ...readings.motors!.map((motor) => motor.temperatureC),
  readings.battery.temperatureC,
]

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('reduce'),
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms))

function setup(initial: TelemetryReadings) {
  return renderHook(({ target }) => useSmoothedReadings(target), {
    initialProps: { target: initial },
  })
}

describe('useSmoothedReadings', () => {
  beforeEach(() => {
    stubReducedMotion(false)
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame'] })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows the derived readings at once on the first render', () => {
    const { result } = setup(flying)

    expect(result.current).toEqual(flying)
  })

  it('cools down smoothly after landing instead of jumping to the standby temperature', () => {
    const { result, rerender } = setup(flying)
    const start = temperatures(flying)
    const goal = temperatures(idle)

    rerender({ target: idle })
    // No frame has run yet: the temperatures are still the flying ones.
    expect(temperatures(result.current)).toEqual(start)

    advance(1000)
    const early = temperatures(result.current)
    early.forEach((value, i) => {
      expect(value).toBeLessThan(start[i])
      expect(value).toBeGreaterThan(goal[i])
    })

    // Monotonic, never below the target, and arrived exactly at it.
    let previous = early
    for (let seconds = 0; seconds < 60; seconds += 1) {
      advance(1000)
      const current = temperatures(result.current)
      current.forEach((value, i) => {
        expect(value).toBeLessThanOrEqual(previous[i])
        expect(value).toBeGreaterThanOrEqual(goal[i])
      })
      previous = current
    }
    expect(temperatures(result.current)).toEqual(goal)
  })

  it('warms up smoothly when a flight starts', () => {
    const { result, rerender } = setup(idle)

    rerender({ target: flying })
    advance(2000)

    const shown = temperatures(result.current)
    shown.forEach((value, i) => {
      expect(value).toBeGreaterThan(temperatures(idle)[i])
      expect(value).toBeLessThan(temperatures(flying)[i])
    })
    advance(120_000)
    expect(temperatures(result.current)).toEqual(temperatures(flying))
  })

  it('eases only temperatures: RPM, power, current and link quality change at once', () => {
    const { result, rerender } = setup(flying)

    rerender({ target: idle })

    expect(result.current.motors!.map((motor) => motor.rpm)).toEqual([0, 0, 0, 0])
    expect(result.current.battery.powerW).toBe(idle.battery.powerW)
    expect(result.current.battery.currentA).toBe(idle.battery.currentA)
    expect(result.current.connectivity).toEqual(idle.connectivity)
    expect(result.current.mode).toBe('standby')
  })

  it('does not schedule any frame while the readings stay the same', () => {
    const request = vi.spyOn(globalThis, 'requestAnimationFrame')
    const { rerender } = setup(flying)

    rerender({ target: { ...flying } })
    rerender({ target: { ...flying } })

    expect(request).not.toHaveBeenCalled()
  })

  it('keeps following a target that keeps moving, without ever jumping to it', () => {
    const { result, rerender } = setup(idle)
    const at = (progress: number) =>
      deriveTelemetry({ ...FLYING, flight: { ...FLYING.flight!, progress } })

    // A poll every two seconds, the flight moving on a little each time.
    let last = temperatures(result.current)
    for (let poll = 1; poll <= 15; poll += 1) {
      rerender({ target: at(0.02 * poll) })
      advance(2000)
      const shown = temperatures(result.current)
      shown.forEach((value, i) => {
        expect(value).toBeGreaterThanOrEqual(last[i])
        expect(value - last[i]).toBeLessThan(3)
      })
      last = shown
    }
  })

  it('shows every change at once when reduced motion is preferred', () => {
    stubReducedMotion(true)
    const { result, rerender } = setup(flying)

    rerender({ target: idle })

    expect(temperatures(result.current)).toEqual(temperatures(idle))
  })

  it('shows a different airframe at once (the motors are not the same ones)', () => {
    const { result, rerender } = setup(flying)
    const unknown = deriveTelemetry({ ...IDLE, model: { ...MODEL, airframeType: 'octocopter' } })

    rerender({ target: unknown })

    expect(result.current.motors).toBeNull()
    expect(result.current.battery.temperatureC).toBe(unknown.battery.temperatureC)
  })

  it('stops its animation frame when it unmounts', () => {
    const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame')
    const { rerender, unmount } = setup(flying)
    rerender({ target: idle })

    unmount()

    expect(cancel).toHaveBeenCalled()
  })
})
