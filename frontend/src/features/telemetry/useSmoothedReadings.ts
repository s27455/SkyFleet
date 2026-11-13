import { useEffect, useMemo, useRef, useState } from 'react'

import { usePrefersReducedMotion } from '../flights/usePrefersReducedMotion'
import type { TelemetryReadings } from './deriveTelemetry'

/** Time constants of the display easing, in milliseconds: how fast a shown temperature follows. */
export const MOTOR_TEMP_EASE_MS = 7000
export const BATTERY_TEMP_EASE_MS = 9000
/** A shown temperature this close to its target (degrees) is considered arrived. */
const SETTLED_C = 0.05

interface Temperatures {
  motors: number[]
  battery: number
}

const temperaturesOf = (readings: TelemetryReadings): Temperatures => ({
  motors: (readings.motors ?? []).map((motor) => motor.temperatureC),
  battery: readings.battery.temperatureC,
})

const tenths = (value: number) => Math.round(value * 10)
const approach = (from: number, to: number, share: number) => from + (to - from) * share

function sameDisplay(a: Temperatures, b: Temperatures): boolean {
  return (
    tenths(a.battery) === tenths(b.battery) &&
    a.motors.length === b.motors.length &&
    a.motors.every((value, index) => tenths(value) === tenths(b.motors[index]))
  )
}

function isSettled(shown: Temperatures, goal: Temperatures): boolean {
  return (
    Math.abs(shown.battery - goal.battery) < SETTLED_C &&
    shown.motors.every((value, index) => Math.abs(value - goal.motors[index]) < SETTLED_C)
  )
}

/**
 * Display smoothing for the temperatures only. The derivation (`deriveTelemetry`) stays pure; a
 * temperature, though, cannot jump the moment a drone lands or a flight begins, so the shown value
 * eases toward the derived one with a slow time constant. Everything else (RPM, power, link
 * quality) passes through unchanged. The first render shows the derived values at once, and with
 * reduced motion preferred every change is shown at once. Health and the 3D highlights are computed
 * from what this returns, so they always agree with the numbers on screen.
 */
export function useSmoothedReadings(target: TelemetryReadings): TelemetryReadings {
  const reducedMotion = usePrefersReducedMotion()
  const [shown, setShown] = useState<Temperatures>(() => temperaturesOf(target))
  const shownRef = useRef(shown)

  useEffect(() => {
    const goal = temperaturesOf(target)
    const commit = (next: Temperatures) => {
      shownRef.current = next
      setShown((previous) => (sameDisplay(previous, next) ? previous : next))
    }
    // A different airframe (motor count) or reduced motion: no easing.
    if (reducedMotion || shownRef.current.motors.length !== goal.motors.length) {
      commit(goal)
      return
    }
    if (isSettled(shownRef.current, goal)) {
      commit(goal)
      return
    }

    let frame = 0
    let last: number | null = null
    const step = (now: number) => {
      // The first frame only fixes the clock; a long gap (hidden tab) is capped.
      const elapsed = last === null ? 0 : Math.min(now - last, 250)
      last = now
      const current = shownRef.current
      const motorShare = 1 - Math.exp(-elapsed / MOTOR_TEMP_EASE_MS)
      const batteryShare = 1 - Math.exp(-elapsed / BATTERY_TEMP_EASE_MS)
      const eased: Temperatures = {
        motors: current.motors.map((value, index) =>
          approach(value, goal.motors[index], motorShare),
        ),
        battery: approach(current.battery, goal.battery, batteryShare),
      }
      if (isSettled(eased, goal)) {
        commit(goal)
        return
      }
      commit(eased)
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, reducedMotion])

  return useMemo(
    () => ({
      ...target,
      motors:
        target.motors?.map((motor, index) => ({
          ...motor,
          temperatureC: Math.round((shown.motors[index] ?? motor.temperatureC) * 10) / 10,
        })) ?? null,
      battery: { ...target.battery, temperatureC: Math.round(shown.battery * 10) / 10 },
    }),
    [target, shown],
  )
}
