import { afterEach, describe, expect, it, vi } from 'vitest'

import { assessHealth, deriveTelemetry, hash01, type TelemetryInput } from './deriveTelemetry'
import { AMBIENT_C, REFERENCE, rotorCountFor } from './telemetryConfig'

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
  batteryPct: 100,
  model: MODEL,
  flight: null,
  parcelKg: null,
}

const FLYING: TelemetryInput = {
  ...IDLE,
  status: 'IN_FLIGHT',
  batteryPct: 80,
  flight: { phase: 'OUTBOUND', progress: 0.4, batteryPct: 78 },
  parcelKg: 1.5,
}

const droneIds = Array.from({ length: 60 }, (_, i) => `DRN-${String(i + 1).padStart(3, '0')}`)

afterEach(() => vi.restoreAllMocks())

describe('rotorCountFor', () => {
  it('knows quadcopters, in any letter case, and nothing else', () => {
    expect(rotorCountFor('quadcopter')).toBe(4)
    expect(rotorCountFor(' Quadcopter ')).toBe(4)
    expect(rotorCountFor('hexacopter')).toBeNull()
    expect(rotorCountFor('octocopter')).toBeNull()
    expect(rotorCountFor('')).toBeNull()
  })
})

describe('deriveTelemetry determinism', () => {
  it('gives identical readings for identical input, with no randomness or clock', () => {
    const random = vi.spyOn(Math, 'random')
    const now = vi.spyOn(Date, 'now')

    const first = deriveTelemetry(FLYING)
    const second = deriveTelemetry({ ...FLYING, flight: { ...FLYING.flight! } })

    expect(second).toEqual(first)
    expect(random).not.toHaveBeenCalled()
    expect(now).not.toHaveBeenCalled()
  })

  it('differs a little between drones but stays in the same band', () => {
    const rpms = droneIds.map((id) => deriveTelemetry({ ...FLYING, droneId: id }).motors![0].rpm)

    expect(new Set(rpms).size).toBeGreaterThan(10)
    expect(Math.max(...rpms) / Math.min(...rpms)).toBeLessThan(1.05)
  })

  it('gives the motors of one drone slightly different, fixed readings', () => {
    for (const id of droneIds.slice(0, 10)) {
      const motors = deriveTelemetry({ ...FLYING, droneId: id }).motors!
      const rpms = motors.map((motor) => motor.rpm)

      expect(new Set(rpms).size).toBeGreaterThanOrEqual(4)
      expect(Math.max(...rpms) / Math.min(...rpms)).toBeLessThan(1.05)
      expect(deriveTelemetry({ ...FLYING, droneId: id }).motors).toEqual(motors)
    }
  })

  it('maps a key to a stable value in [0, 1)', () => {
    expect(hash01('DRN-001:warm')).toBe(hash01('DRN-001:warm'))
    for (const id of droneIds) {
      const value = hash01(id)
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThan(1)
    }
  })

  it('changes smoothly with the flight progress, never abruptly', () => {
    const quality = (progress: number) =>
      deriveTelemetry({ ...FLYING, flight: { phase: 'OUTBOUND', progress, batteryPct: 78 } })
        .connectivity.qualityPct
    expect(Math.abs(quality(0.5) - quality(0.51))).toBeLessThanOrEqual(1)
    expect(quality(0.5)).toBeLessThan(quality(0))
  })
})

describe('operating modes', () => {
  it('idle: motors off, near ambient, standby current only', () => {
    const readings = deriveTelemetry(IDLE)

    expect(readings.mode).toBe('standby')
    for (const motor of readings.motors!) {
      expect(motor.rpm).toBe(0)
      expect(motor.temperatureC).toBeGreaterThan(AMBIENT_C)
      expect(motor.temperatureC).toBeLessThan(AMBIENT_C + 6)
    }
    expect(readings.battery.currentDirection).toBe('standby')
    expect(readings.battery.currentA).toBeLessThan(1)
    expect(readings.battery.powerW).toBeLessThan(25)
  })

  it('in flight: motors spin, warm up and draw a large discharge current', () => {
    const readings = deriveTelemetry(FLYING)

    expect(readings.mode).toBe('flight')
    for (const motor of readings.motors!) {
      expect(motor.rpm).toBeGreaterThan(REFERENCE.motorRpmInFlight.min)
      expect(motor.rpm).toBeLessThan(REFERENCE.motorRpmInFlight.max)
      expect(motor.temperatureC).toBeGreaterThan(35)
    }
    expect(readings.battery.currentDirection).toBe('discharging')
    expect(readings.battery.currentA).toBeGreaterThan(30)
    expect(readings.battery.currentA).toBeLessThan(REFERENCE.currentMaxA)
    expect(readings.battery.powerW).toBeLessThan(REFERENCE.powerMaxW)
    expect(readings.battery.temperatureC).toBeGreaterThan(AMBIENT_C + 5)
  })

  it('charging: motors off, charge current from the model, tapering after 80%', () => {
    const at = (batteryPct: number) =>
      deriveTelemetry({ ...IDLE, status: 'CHARGING', batteryPct }).battery
    const bulk = at(50)

    expect(bulk.currentDirection).toBe('charging')
    expect(bulk.currentA).toBeGreaterThan(20)
    expect(at(90).currentA).toBeLessThan(bulk.currentA)
    expect(at(100).currentA).toBe(0)
    expect(bulk.temperatureC).toBeGreaterThan(deriveTelemetry(IDLE).battery.temperatureC)
    expect(deriveTelemetry({ ...IDLE, status: 'CHARGING', batteryPct: 50 }).motors![0].rpm).toBe(0)
  })

  it('charging current follows the model charge time', () => {
    const slow = deriveTelemetry({
      ...IDLE,
      status: 'CHARGING',
      batteryPct: 40,
      model: { ...MODEL, chargeTo80Minutes: 90 },
    })
    const fast = deriveTelemetry({ ...IDLE, status: 'CHARGING', batteryPct: 40 })

    expect(fast.battery.currentA / slow.battery.currentA).toBeCloseTo(2, 0)
  })

  it('maintenance: everything off with a lower standby draw than idle', () => {
    const readings = deriveTelemetry({ ...IDLE, status: 'MAINTENANCE' })

    expect(readings.mode).toBe('maintenance')
    expect(readings.motors!.every((motor) => motor.rpm === 0)).toBe(true)
    expect(readings.battery.currentA).toBeLessThan(deriveTelemetry(IDLE).battery.currentA)
  })

  it('treats a landed or emergency flight as motors off', () => {
    for (const phase of ['LANDED', 'EMERGENCY'] as const) {
      const readings = deriveTelemetry({
        ...FLYING,
        flight: { phase, progress: 1, batteryPct: 70 },
      })
      expect(readings.mode).toBe('standby')
      expect(readings.motors!.every((motor) => motor.rpm === 0)).toBe(true)
    }
  })
})

describe('internal consistency', () => {
  it('power equals the displayed voltage times current in every mode', () => {
    const inputs: TelemetryInput[] = [
      IDLE,
      FLYING,
      { ...IDLE, status: 'CHARGING', batteryPct: 35 },
      { ...IDLE, status: 'MAINTENANCE' },
    ]
    for (const input of inputs) {
      const { voltageV, currentA, powerW } = deriveTelemetry(input).battery
      expect(Math.abs(powerW - voltageV * currentA)).toBeLessThanOrEqual(0.06)
    }
  })

  it('lower charge means lower voltage, and the voltage stays within the pack range', () => {
    const voltageAt = (pct: number) =>
      deriveTelemetry({ ...IDLE, batteryPct: pct }).battery.voltageV
    expect(voltageAt(100)).toBeGreaterThan(voltageAt(60))
    expect(voltageAt(60)).toBeGreaterThan(voltageAt(10))
    expect(voltageAt(100)).toBeLessThanOrEqual(REFERENCE.batteryVoltageV.max)
    expect(voltageAt(0)).toBeGreaterThanOrEqual(REFERENCE.batteryVoltageV.min - 0.1)
  })

  it('voltage sags under load', () => {
    const idleV = deriveTelemetry({ ...IDLE, batteryPct: 80 }).battery.voltageV
    const flyingV = deriveTelemetry({
      ...FLYING,
      batteryPct: 80,
      flight: { phase: 'OUTBOUND', progress: 0.4, batteryPct: 80 },
    }).battery.voltageV
    expect(flyingV).toBeLessThan(idleV)
  })

  it('a heavier parcel means more current, higher RPM and warmer motors', () => {
    const withParcel = (kg: number) =>
      deriveTelemetry({ ...FLYING, droneId: 'DRN-002', parcelKg: kg })
    const light = withParcel(0.2)
    const heavy = withParcel(3)

    expect(heavy.battery.currentA).toBeGreaterThan(light.battery.currentA)
    expect(heavy.motors![0].rpm).toBeGreaterThan(light.motors![0].rpm)
    expect(heavy.motors![0].temperatureC).toBeGreaterThan(light.motors![0].temperatureC)
  })

  it('carries the parcel only while outbound or delivering', () => {
    const phaseOf = (phase: 'OUTBOUND' | 'DELIVERING' | 'RETURNING' | 'DIVERTING') =>
      deriveTelemetry({ ...FLYING, flight: { phase, progress: 0.5, batteryPct: 78 }, parcelKg: 3 })
    expect(phaseOf('OUTBOUND').carryingParcel).toBe(true)
    expect(phaseOf('DELIVERING').carryingParcel).toBe(true)
    expect(phaseOf('RETURNING').carryingParcel).toBe(false)
    expect(phaseOf('RETURNING').battery.currentA).toBeLessThan(phaseOf('OUTBOUND').battery.currentA)
  })

  it('splits the total power over four rotors', () => {
    const readings = deriveTelemetry(FLYING)

    expect(readings.motors!.length).toBe(4)
    expect(readings.motors![0].rpm).toBeGreaterThan(3000)
    expect(readings.motors![0].rpm).toBeLessThan(7000)
  })
})

describe('airframes and missing inputs', () => {
  it('numbers the motors M1..M4 with stable component ids', () => {
    const quad = deriveTelemetry(IDLE)

    expect(quad.motors!.map((m) => [m.id, m.label])).toEqual([
      ['motor-1', 'M1'],
      ['motor-2', 'M2'],
      ['motor-3', 'M3'],
      ['motor-4', 'M4'],
    ])
  })

  it('gives no motor readings for a six-rotor airframe: the MVP fleet is quadcopters only', () => {
    const readings = deriveTelemetry({ ...IDLE, model: { ...MODEL, airframeType: 'hexacopter' } })

    expect(readings.motors).toBeNull()
    expect(readings.rotorCount).toBeNull()
  })

  it('gives no motor readings for an unknown airframe and says so', () => {
    const readings = deriveTelemetry({ ...FLYING, model: { ...MODEL, airframeType: 'octocopter' } })

    expect(readings.motors).toBeNull()
    expect(readings.rotorCount).toBeNull()
    expect(readings.notes.join(' ')).toMatch(/octocopter/)
    expect(readings.battery.currentA).toBeGreaterThan(0)
  })

  it('notes a flying drone without flight data and a parcel without a weight', () => {
    expect(deriveTelemetry({ ...FLYING, flight: null }).notes.join(' ')).toMatch(
      /Flight data is not available/,
    )
    expect(deriveTelemetry({ ...FLYING, parcelKg: null }).notes.join(' ')).toMatch(
      /Parcel weight is not available/,
    )
    expect(deriveTelemetry(FLYING).notes).toEqual([])
  })

  it('uses the live flight battery while flying, the drone record otherwise', () => {
    expect(deriveTelemetry(FLYING).battery.chargePct).toBe(78)
    expect(deriveTelemetry({ ...IDLE, batteryPct: 64 }).battery.chargePct).toBe(64)
  })
})

describe('the fleet stays nominal unless a threshold is crossed', () => {
  const worstCase = (id: string, airframeType: string): TelemetryInput => ({
    ...FLYING,
    droneId: id,
    model: { ...MODEL, airframeType },
    flight: { phase: 'DELIVERING', progress: 0.5, batteryPct: 80 },
    parcelKg: 3,
  })

  it('most drones are nominal even at maximum payload; none is critical', () => {
    const levels = droneIds.map((id) => {
      const readings = deriveTelemetry(worstCase(id, 'quadcopter'))
      return assessHealth(readings, 20).level
    })

    expect(levels.filter((level) => level === 'nominal').length / levels.length).toBeGreaterThan(
      0.8,
    )
    expect(levels).not.toContain('critical')
  })

  it('some drones have a distinctly warmer motor, but only some', () => {
    const spread = droneIds.map((id) => {
      const temps = deriveTelemetry(worstCase(id, 'quadcopter')).motors!.map((m) => m.temperatureC)
      return Math.max(...temps) - Math.min(...temps)
    })
    const warm = spread.filter((value) => value > 8).length

    expect(warm).toBeGreaterThan(0)
    expect(warm / droneIds.length).toBeLessThan(0.3)
  })

  it('idle, charging and maintenance drones are nominal', () => {
    for (const id of droneIds) {
      for (const status of ['IDLE', 'CHARGING', 'MAINTENANCE'] as const) {
        const readings = deriveTelemetry({ ...IDLE, droneId: id, status, batteryPct: 60 })
        expect(assessHealth(readings, 20).level).toBe('nominal')
      }
    }
  })
})

describe('assessHealth', () => {
  const base = deriveTelemetry({ ...IDLE, batteryPct: 60 })
  const withMotorTemp = (temperatureC: number) => ({
    ...base,
    motors: base.motors!.map((m, i) => (i === 2 ? { ...m, temperatureC } : m)),
  })
  const levelOf = (readings: typeof base, id: string, reserve = 20) =>
    assessHealth(readings, reserve).indicators.find((i) => i.id === id)!.level

  it('is nominal for ordinary readings, with an indicator per area', () => {
    const health = assessHealth(base, 20)

    expect(health.level).toBe('nominal')
    expect(health.warnings).toEqual([])
    expect(health.indicators.map((i) => i.id)).toEqual([
      'motors',
      'battery-charge',
      'battery-temperature',
      'connectivity',
    ])
  })

  it.each([
    [70, 'nominal'],
    [70.1, 'attention'],
    [85, 'attention'],
    [85.1, 'critical'],
  ])('motor at %s °C is %s', (temperature, level) => {
    expect(levelOf(withMotorTemp(temperature), 'motors')).toBe(level)
  })

  it('names the hottest motor in the warning', () => {
    const health = assessHealth(withMotorTemp(88), 20)

    expect(health.warnings).toHaveLength(1)
    expect(health.warnings[0]).toMatchObject({ componentId: 'motor-3', level: 'critical' })
    expect(health.warnings[0].detail).toContain('M3 at 88.0 °C')
  })

  it.each([
    [21, 'nominal'],
    [20, 'attention'],
    [11, 'attention'],
    [10, 'critical'],
    [3, 'critical'],
  ])('battery charge %s%% against a 20%% reserve is %s', (chargePct, level) => {
    const readings = { ...base, battery: { ...base.battery, chargePct } }
    expect(levelOf(readings, 'battery-charge')).toBe(level)
  })

  it('judges the charge against the real reserve of the model', () => {
    const readings = { ...base, battery: { ...base.battery, chargePct: 28 } }

    expect(levelOf(readings, 'battery-charge', 20)).toBe('nominal')
    expect(levelOf(readings, 'battery-charge', 30)).toBe('attention')
  })

  it.each([
    [45, 'nominal'],
    [45.1, 'attention'],
    [55.1, 'critical'],
  ])('battery at %s °C is %s', (temperatureC, level) => {
    const readings = { ...base, battery: { ...base.battery, temperatureC } }
    expect(levelOf(readings, 'battery-temperature')).toBe(level)
  })

  it.each([
    [70, 'nominal'],
    [69, 'attention'],
    [50, 'attention'],
    [49, 'critical'],
  ])('connectivity at %s%% is %s', (qualityPct, level) => {
    const readings = { ...base, connectivity: { qualityPct, label: '' } }
    expect(levelOf(readings, 'connectivity')).toBe(level)
  })

  it('the overall level is the worst indicator and every warning is explained', () => {
    const readings = {
      ...withMotorTemp(72),
      battery: { ...base.battery, chargePct: 5 },
    }
    const health = assessHealth(readings, 20)

    expect(health.level).toBe('critical')
    expect(health.warnings.map((w) => w.id)).toEqual(['motors', 'battery-charge'])
    expect(health.warnings.every((w) => w.detail.length > 0)).toBe(true)
  })

  it('has no motor indicator when the airframe is unknown', () => {
    const health = assessHealth({ ...base, motors: null }, 20)

    expect(health.indicators.map((i) => i.id)).not.toContain('motors')
  })
})
