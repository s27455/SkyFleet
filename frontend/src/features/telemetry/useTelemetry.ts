import { useMemo, useState } from 'react'

import { componentStatuses } from './componentHealth'
import { assessHealth, deriveTelemetry, type TelemetryInput } from './deriveTelemetry'
import { useSmoothedReadings } from './useSmoothedReadings'

/**
 * The telemetry of a drone for display. The derivation is recomputed only when one of the input
 * values changes (a live refresh that brings the same state hands out the same objects); the shown
 * temperatures ease toward it, and the health and per-component statuses are judged on the shown
 * readings, so the panel, the details and the 3D highlights always agree.
 */
export function useTelemetry(input: TelemetryInput) {
  const { droneId, status, batteryPct, model, flight, parcelKg } = input
  const { airframeType, emptyWeightKg, maxPayloadKg, nominalFlightTimeMin } = model
  const { chargeTo80Minutes, minBatteryReservePct } = model
  const phase = flight?.phase
  const progress = flight?.progress
  const flightBatteryPct = flight?.batteryPct

  const derived = useMemo(
    () =>
      deriveTelemetry({
        droneId,
        status,
        batteryPct,
        model: {
          airframeType,
          emptyWeightKg,
          maxPayloadKg,
          nominalFlightTimeMin,
          chargeTo80Minutes,
          minBatteryReservePct,
        },
        flight:
          phase !== undefined && progress !== undefined && flightBatteryPct !== undefined
            ? { phase, progress, batteryPct: flightBatteryPct }
            : null,
        parcelKg,
      }),
    [
      droneId,
      status,
      batteryPct,
      airframeType,
      emptyWeightKg,
      maxPayloadKg,
      nominalFlightTimeMin,
      chargeTo80Minutes,
      minBatteryReservePct,
      phase,
      progress,
      flightBatteryPct,
      parcelKg,
    ],
  )

  const readings = useSmoothedReadings(derived)
  return useMemo(() => {
    const health = assessHealth(readings, minBatteryReservePct)
    return { readings, health, statuses: componentStatuses(readings, health) }
  }, [readings, minBatteryReservePct])
}

/** Keeps the previous reference while the value stays deeply equal (JSON-comparable values only). */
export function useStableValue<T>(value: T): T {
  const [stable, setStable] = useState(value)
  if (JSON.stringify(stable) !== JSON.stringify(value)) setStable(value)
  return stable
}
