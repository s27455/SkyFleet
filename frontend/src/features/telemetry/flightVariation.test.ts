import { describe, expect, it } from 'vitest'

import { assessHealth, deriveTelemetry, type TelemetryInput } from './deriveTelemetry'
import { REFERENCE } from './telemetryConfig'

// Feature 016E: motor RPM, temperatures, power and link quality move smoothly over a flight.

const MODEL = {
  airframeType: 'quadcopter',
  emptyWeightKg: 9,
  maxPayloadKg: 3,
  nominalFlightTimeMin: 32,
  chargeTo80Minutes: 45,
  minBatteryReservePct: 20,
}

type Phase = 'OUTBOUND' | 'DELIVERING' | 'RETURNING'

const flightAt = (
  droneId: string,
  progress: number,
  phase: Phase = 'OUTBOUND',
  parcelKg = 1.5,
): TelemetryInput => ({
  droneId,
  status: 'IN_FLIGHT',
  batteryPct: 80,
  model: MODEL,
  flight: { phase, progress, batteryPct: 78 },
  parcelKg,
})

const idleOf = (droneId: string): TelemetryInput => ({
  droneId,
  status: 'IDLE',
  batteryPct: 80,
  model: MODEL,
  flight: null,
  parcelKg: null,
})

const droneIds = Array.from({ length: 60 }, (_, i) => `DRN-${String(i + 1).padStart(3, '0')}`)
/** Flight progress from 0 to 1 in steps of 0.5%: about what consecutive polls are apart. */
const STEP = 0.005
const progresses = Array.from({ length: 201 }, (_, i) => Math.round(i * STEP * 1000) / 1000)

const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length
const peakToPeak = (values: number[]) => Math.max(...values) - Math.min(...values)
const maxStep = (values: number[]) =>
  Math.max(...values.slice(1).map((value, i) => Math.abs(value - values[i])))
const correlation = (a: number[], b: number[]) => {
  const ma = mean(a)
  const mb = mean(b)
  let sab = 0
  let saa = 0
  let sbb = 0
  a.forEach((value, i) => {
    sab += (value - ma) * (b[i] - mb)
    saa += (value - ma) ** 2
    sbb += (b[i] - mb) ** 2
  })
  return sab / Math.sqrt(saa * sbb)
}

/** One series per motor over the flight, for a reading of the motor. */
const motorSeries = (
  droneId: string,
  read: (motor: { rpm: number; temperatureC: number }) => number,
  phase: Phase = 'OUTBOUND',
) => {
  const series: number[][] = [[], [], [], []]
  for (const progress of progresses) {
    deriveTelemetry(flightAt(droneId, progress, phase)).motors!.forEach((motor, index) => {
      series[index].push(read(motor))
    })
  }
  return series
}

describe('RPM over a flight', () => {
  it('varies gently: 2 to 5 percent peak to peak, for every motor of every drone', () => {
    for (const id of droneIds) {
      for (const series of motorSeries(id, (motor) => motor.rpm)) {
        const spread = peakToPeak(series) / mean(series)
        expect(spread).toBeGreaterThanOrEqual(0.02)
        expect(spread).toBeLessThanOrEqual(0.05)
      }
    }
  })

  it('moves smoothly: no step above half a percent between polls half a percent of the flight apart', () => {
    for (const id of droneIds) {
      for (const series of motorSeries(id, (motor) => motor.rpm)) {
        expect(maxStep(series) / mean(series)).toBeLessThan(0.005)
      }
    }
  })

  it('is not constant: it differs between the start, the middle and the end of a flight', () => {
    const rpmAt = (progress: number) =>
      deriveTelemetry(flightAt('DRN-002', progress)).motors!.map((motor) => motor.rpm)

    expect(rpmAt(0.1)).not.toEqual(rpmAt(0.4))
    expect(rpmAt(0.4)).not.toEqual(rpmAt(0.8))
  })

  it('gives each motor its own pattern, not the same wave with an offset', () => {
    for (const id of droneIds.slice(0, 20)) {
      const series = motorSeries(id, (motor) => motor.rpm)
      for (let a = 0; a < series.length; a += 1) {
        for (let b = a + 1; b < series.length; b += 1) {
          const ratio = series[a].map((value, i) => value / series[b][i])
          // If two motors followed one pattern, their ratio would be constant.
          expect(peakToPeak(ratio)).toBeGreaterThan(0.004)
        }
      }
    }
  })
})

describe('temperatures over a flight', () => {
  it('start from the standby temperature, so take-off does not jump', () => {
    for (const id of droneIds) {
      const idle = deriveTelemetry(idleOf(id))
      const takingOff = deriveTelemetry(flightAt(id, 0))

      expect(takingOff.motors!.map((m) => m.temperatureC)).toEqual(
        idle.motors!.map((m) => m.temperatureC),
      )
      expect(takingOff.battery.temperatureC).toBe(idle.battery.temperatureC)
    }
  })

  it('warm up over the flight, quickly at first and then more slowly', () => {
    for (const id of droneIds.slice(0, 20)) {
      const motorMean = (progress: number) =>
        mean(deriveTelemetry(flightAt(id, progress)).motors!.map((m) => m.temperatureC))
      const batteryAt = (progress: number) =>
        deriveTelemetry(flightAt(id, progress)).battery.temperatureC

      expect(motorMean(0.1)).toBeGreaterThan(motorMean(0) + 3)
      expect(motorMean(0.3)).toBeGreaterThan(motorMean(0.1))
      expect(motorMean(0.6)).toBeGreaterThan(motorMean(0.3))
      // The second half of the warm-up is slower than the first.
      expect(motorMean(0.6) - motorMean(0.3)).toBeLessThan(motorMean(0.3) - motorMean(0))
      expect(batteryAt(0.5)).toBeGreaterThan(batteryAt(0.1))
    }
  })

  it('ease off during the descent, at the end of a flight', () => {
    for (const id of droneIds.slice(0, 20)) {
      const motorMean = (progress: number) =>
        mean(deriveTelemetry(flightAt(id, progress)).motors!.map((m) => m.temperatureC))

      expect(motorMean(1)).toBeLessThan(motorMean(0.85))
    }
  })

  it('evolve more slowly than RPM: small steps, with no jump between polls', () => {
    for (const id of droneIds) {
      for (const series of motorSeries(id, (motor) => motor.temperatureC)) {
        expect(maxStep(series)).toBeLessThanOrEqual(1)
      }
      const battery = progresses.map(
        (progress) => deriveTelemetry(flightAt(id, progress)).battery.temperatureC,
      )
      expect(maxStep(battery)).toBeLessThanOrEqual(0.4)
    }
  })

  it('differ between the motors of a drone in how they evolve, not only by an offset', () => {
    for (const id of droneIds.slice(0, 20)) {
      const series = motorSeries(id, (motor) => motor.temperatureC)
      for (let a = 0; a < series.length; a += 1) {
        for (let b = a + 1; b < series.length; b += 1) {
          const difference = series[a].map((value, i) => value - series[b][i])
          expect(peakToPeak(difference)).toBeGreaterThan(0.5)
        }
      }
    }
  })
})

describe('power, current and link quality over a flight', () => {
  const sampleOf = (id: string, progress: number) => deriveTelemetry(flightAt(id, progress))

  it('vary subtly: a few percent', () => {
    for (const id of droneIds) {
      const power = progresses.map((progress) => sampleOf(id, progress).battery.powerW)
      const current = progresses.map((progress) => sampleOf(id, progress).battery.currentA)

      expect(peakToPeak(power) / mean(power)).toBeGreaterThan(0.015)
      expect(peakToPeak(power) / mean(power)).toBeLessThan(0.1)
      expect(peakToPeak(current) / mean(current)).toBeGreaterThan(0.015)
    }
  })

  it('stay coherent: power is the shown voltage times the shown current, and RPM follows power', () => {
    for (const id of droneIds.slice(0, 20)) {
      const samples = progresses.map((progress) => sampleOf(id, progress))
      for (const { battery } of samples) {
        expect(battery.powerW).toBeCloseTo(battery.voltageV * battery.currentA, 1)
      }
      const power = samples.map((sample) => sample.battery.powerW)
      const meanRpm = samples.map((sample) => mean(sample.motors!.map((motor) => motor.rpm)))
      expect(correlation(power, meanRpm)).toBeGreaterThan(0.5)
    }
  })

  it('keeps the link quality moving smoothly, and never poor', () => {
    for (const id of droneIds) {
      const link = progresses.map((progress) => sampleOf(id, progress).connectivity.qualityPct)

      expect(maxStep(link)).toBeLessThanOrEqual(1)
      expect(Math.min(...link)).toBeGreaterThanOrEqual(REFERENCE.connectivityPct.attention)
    }
  })
})

describe('repeatability', () => {
  it('gives the same readings for the same flight state, from any new input object', () => {
    for (const id of droneIds.slice(0, 10)) {
      for (const progress of progresses) {
        expect(deriveTelemetry(flightAt(id, progress))).toEqual(
          deriveTelemetry(flightAt(id, progress)),
        )
      }
    }
  })

  it('does not depend on the order of the polls: the readings are a function of the state only', () => {
    const forward = progresses.map((progress) => deriveTelemetry(flightAt('DRN-007', progress)))
    const backward = [...progresses]
      .reverse()
      .map((progress) => deriveTelemetry(flightAt('DRN-007', progress)))
      .reverse()

    expect(backward).toEqual(forward)
  })
})

describe('bounds: ordinary fluctuations never cause warnings', () => {
  const phases: Phase[] = ['OUTBOUND', 'DELIVERING', 'RETURNING']

  it('keeps every reading in its plausible range, even at maximum payload', () => {
    // Track the extremes over the whole fleet and assert once: thousands of expects are slow.
    const low = { rpm: Infinity, motorC: Infinity, volts: Infinity }
    const high = { rpm: 0, motorC: 0, batteryC: 0, amps: 0, watts: 0, volts: 0 }
    for (const id of droneIds) {
      for (const phase of phases) {
        for (const progress of progresses) {
          const readings = deriveTelemetry(flightAt(id, progress, phase, MODEL.maxPayloadKg))
          for (const motor of readings.motors!) {
            low.rpm = Math.min(low.rpm, motor.rpm)
            high.rpm = Math.max(high.rpm, motor.rpm)
            low.motorC = Math.min(low.motorC, motor.temperatureC)
            high.motorC = Math.max(high.motorC, motor.temperatureC)
          }
          const { battery } = readings
          high.batteryC = Math.max(high.batteryC, battery.temperatureC)
          high.amps = Math.max(high.amps, battery.currentA)
          high.watts = Math.max(high.watts, battery.powerW)
          low.volts = Math.min(low.volts, battery.voltageV)
          high.volts = Math.max(high.volts, battery.voltageV)
        }
      }
    }

    expect(low.rpm).toBeGreaterThanOrEqual(REFERENCE.motorRpmInFlight.min)
    expect(high.rpm).toBeLessThanOrEqual(REFERENCE.motorRpmInFlight.max)
    expect(low.motorC).toBeGreaterThan(20)
    expect(high.motorC).toBeLessThan(REFERENCE.motorTempC.critical)
    expect(high.batteryC).toBeLessThan(REFERENCE.batteryTempC.attention)
    expect(high.amps).toBeLessThan(REFERENCE.currentMaxA)
    expect(high.watts).toBeLessThan(REFERENCE.powerMaxW)
    expect(low.volts).toBeGreaterThanOrEqual(REFERENCE.batteryVoltageV.min)
    expect(high.volts).toBeLessThanOrEqual(REFERENCE.batteryVoltageV.max)
  })

  it('never reports a critical level, and attention only rarely, from the fluctuations', () => {
    let samples = 0
    let attention = 0
    let critical = 0
    for (const id of droneIds) {
      for (const phase of phases) {
        for (const progress of progresses) {
          const readings = deriveTelemetry(flightAt(id, progress, phase, MODEL.maxPayloadKg))
          const { level } = assessHealth(readings, MODEL.minBatteryReservePct)
          samples += 1
          if (level === 'attention') attention += 1
          if (level === 'critical') critical += 1
        }
      }
    }
    expect(critical).toBe(0)
    expect(attention / samples).toBeLessThan(0.05)
  })

  it('has no warnings at all for an ordinary parcel', () => {
    let warnings = 0
    for (const id of droneIds) {
      for (const progress of progresses) {
        const readings = deriveTelemetry(flightAt(id, progress, 'OUTBOUND', 1.5))
        warnings += assessHealth(readings, MODEL.minBatteryReservePct).warnings.length
      }
    }
    expect(warnings).toBe(0)
  })
})
