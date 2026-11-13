import type { DroneModel, DroneStatus } from '../../types/drone'
import type { FlightPhase } from '../../types/flight'
import {
  AMBIENT_C,
  BATTERY_TEMP_RISE_AT_FULL_LOAD_C,
  BATTERY_TEMP_WOBBLE_C,
  BATTERY_WARM_UP_PROGRESS,
  CONNECTIVITY_BANDS,
  COOL_DOWN_FRACTION,
  COOL_DOWN_START_PROGRESS,
  DEFAULT_PHASE_FACTOR,
  HOVER_W_PER_KG,
  LINK_WOBBLE_PCT,
  MAINTENANCE_CURRENT_A,
  MAX_LOAD_MARGIN,
  MOTORS_OFF_PHASES,
  MOTOR_COMPONENT_IDS,
  MOTOR_RPM_SPREAD,
  MOTOR_RPM_WAVE,
  MOTOR_TEMP_RISE_AT_FULL_LOAD_C,
  MOTOR_TEMP_SPREAD_C,
  MOTOR_TEMP_WOBBLE_C,
  MOTOR_WARM_UP_PROGRESS,
  NOMINAL_PACK_VOLTAGE_V,
  OPEN_CIRCUIT_CURVE,
  PACK_RESISTANCE_OHM,
  PARCEL_ON_BOARD_PHASES,
  PHASE_POWER_FACTOR,
  POWER_VARIATION,
  REFERENCE,
  REFERENCE_RPM,
  REFERENCE_THRUST_PER_ROTOR_KG,
  STANDBY_CURRENT_A,
  WARM_MOTOR_DRONE_FRACTION,
  WARM_MOTOR_EXTRA_RANGE_C,
  WARM_MOTOR_MIN_EXTRA_C,
  rotorCountFor,
  type MotorComponentId,
  type TelemetryComponentId,
} from './telemetryConfig'

/**
 * Simulated telemetry (Feature 016C): a pure, deterministic estimate of component readings from the
 * drone's real state. There are no random numbers, clocks or stored state, so the same input always
 * gives the same readings. The values are demonstration estimates, not sensor data.
 */

export type OperatingMode = 'standby' | 'flight' | 'charging' | 'maintenance'

export interface TelemetryInput {
  droneId: string
  status: DroneStatus
  /** The drone record's battery (real). */
  batteryPct: number
  model: Pick<
    DroneModel,
    | 'airframeType'
    | 'emptyWeightKg'
    | 'maxPayloadKg'
    | 'nominalFlightTimeMin'
    | 'chargeTo80Minutes'
    | 'minBatteryReservePct'
  >
  /** The drone's reported flight (real), if it has one. Its battery is fresher than the record's. */
  flight: { phase: FlightPhase; progress: number; batteryPct: number } | null
  /** Weight of the parcel on board (real order), or null when it is not known. */
  parcelKg: number | null
}

export interface MotorReading {
  id: MotorComponentId
  /** `M1`..`M4`. */
  label: string
  temperatureC: number
  rpm: number
}

export type CurrentDirection = 'discharging' | 'charging' | 'standby'

export interface TelemetryReadings {
  mode: OperatingMode
  carryingParcel: boolean
  rotorCount: number | null
  /** One reading per rotor, or null when the airframe's rotor count is not known. */
  motors: MotorReading[] | null
  battery: {
    /** The charge level the estimate used (real). */
    chargePct: number
    voltageV: number
    currentA: number
    currentDirection: CurrentDirection
    powerW: number
    temperatureC: number
  }
  connectivity: { qualityPct: number; label: string }
  /** Limits of the estimate, to be shown next to it (missing inputs, unknown airframe). */
  notes: string[]
}

// ---- Deterministic helpers ---------------------------------------------------------------------

/** FNV-1a hash of a string mapped to [0, 1): a stable "random" value per key. */
export function hash01(key: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  // Final avalanche (murmur3 finalizer): keys that differ in one character must not give close values.
  hash ^= hash >>> 16
  hash = Math.imul(hash, 0x85ebca6b)
  hash ^= hash >>> 13
  hash = Math.imul(hash, 0xc2b2ae35)
  hash ^= hash >>> 16
  return (hash >>> 0) / 0x100000000
}

const round = (value: number, decimals: number) => {
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
const smoothstep = (edge0: number, edge1: number, x: number) => {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

function openCircuitVoltage(chargePct: number): number {
  const charge = clamp(chargePct, 0, 100)
  const curve = OPEN_CIRCUIT_CURVE
  for (let i = 1; i < curve.length; i += 1) {
    const [x1, y1] = curve[i]
    if (charge <= x1) {
      const [x0, y0] = curve[i - 1]
      return y0 + ((y1 - y0) * (charge - x0)) / (x1 - x0)
    }
  }
  return curve[curve.length - 1][1]
}

export function connectivityLabel(qualityPct: number): string {
  return CONNECTIVITY_BANDS.find((band) => qualityPct >= band.min)?.label ?? 'Poor'
}

// ---- Derivation --------------------------------------------------------------------------------

export function deriveTelemetry(input: TelemetryInput): TelemetryReadings {
  const { droneId, status, model, flight } = input
  const notes: string[] = []
  const rotorCount = rotorCountFor(model.airframeType)
  if (rotorCount === null) {
    notes.push(`Motor telemetry is not available for the airframe "${model.airframeType}".`)
  }

  const motorsRunning =
    status === 'IN_FLIGHT' && !(flight && MOTORS_OFF_PHASES.includes(flight.phase))
  const mode: OperatingMode = motorsRunning
    ? 'flight'
    : status === 'CHARGING'
      ? 'charging'
      : status === 'MAINTENANCE'
        ? 'maintenance'
        : 'standby'
  if (status === 'IN_FLIGHT' && !flight) {
    notes.push('Flight data is not available: estimated as level flight without a parcel.')
  }

  const carryingParcel =
    motorsRunning && flight !== null && PARCEL_ON_BOARD_PHASES.includes(flight.phase)
  if (carryingParcel && input.parcelKg === null) {
    notes.push('Parcel weight is not available: estimated without a parcel.')
  }
  const parcelKg = carryingParcel ? clamp(input.parcelKg ?? 0, 0, model.maxPayloadKg) : 0
  const massKg = model.emptyWeightKg + parcelKg
  const phaseFactor = flight
    ? (PHASE_POWER_FACTOR[flight.phase] ?? DEFAULT_PHASE_FACTOR)
    : DEFAULT_PHASE_FACTOR

  // How far along the flight is (0 to 1). Everything that varies in flight is a smooth function of
  // it plus a fixed per-drone, per-component phase: the same flight state always reads the same.
  const progress = flight ? clamp(flight.progress, 0, 1) : 0.5
  const wave = (key: string, cycles: number) =>
    Math.sin(2 * Math.PI * (cycles * progress + hash01(`${droneId}:${key}`)))
  // Shared power demand: it moves the power, current and (through thrust) every motor's RPM together.
  const dynamics = 1 + POWER_VARIATION * wave('dynamics', 2.2)

  // Power in flight. The motor load, as a share of the maximum (0 to 1), uses the steady demand
  // without the swing: heat builds up slowly and does not follow every gust.
  const steadyPowerW = HOVER_W_PER_KG * massKg * phaseFactor
  const flightPowerW = motorsRunning ? steadyPowerW * dynamics : 0
  const maxPowerW = HOVER_W_PER_KG * (model.emptyWeightKg + model.maxPayloadKg) * MAX_LOAD_MARGIN
  const heatLoad = motorsRunning ? clamp(steadyPowerW / maxPowerW, 0, 1) : 0
  // Warming up from the standby temperature, and easing off during the descent.
  const coolDown = 1 - COOL_DOWN_FRACTION * smoothstep(COOL_DOWN_START_PROGRESS, 1, progress)
  const motorWarm = 1 - Math.exp(-progress / MOTOR_WARM_UP_PROGRESS)
  const batteryWarm = 1 - Math.exp(-progress / BATTERY_WARM_UP_PROGRESS)

  // ---- Battery
  const chargePct = clamp(motorsRunning && flight ? flight.batteryPct : input.batteryPct, 0, 100)
  const openCircuitV = openCircuitVoltage(chargePct)
  const packEnergyWh = (HOVER_W_PER_KG * model.emptyWeightKg * model.nominalFlightTimeMin) / 60
  const packCapacityAh = packEnergyWh / NOMINAL_PACK_VOLTAGE_V
  const maxChargeA = (0.8 * packCapacityAh) / (model.chargeTo80Minutes / 60)

  let voltageV: number
  let currentA: number
  let currentDirection: CurrentDirection
  if (mode === 'flight') {
    const firstGuessA = flightPowerW / openCircuitV
    voltageV = openCircuitV - firstGuessA * PACK_RESISTANCE_OHM
    currentA = flightPowerW / voltageV
    currentDirection = 'discharging'
  } else if (mode === 'charging') {
    // Constant current up to 80%, then tapering to zero at 100%.
    const taper = chargePct >= 80 ? clamp((100 - chargePct) / 20, 0, 1) : 1
    currentA = maxChargeA * taper
    voltageV = openCircuitV + currentA * PACK_RESISTANCE_OHM
    currentDirection = 'charging'
  } else {
    currentA = mode === 'maintenance' ? MAINTENANCE_CURRENT_A : STANDBY_CURRENT_A
    voltageV = openCircuitV - currentA * PACK_RESISTANCE_OHM
    currentDirection = 'standby'
  }
  const shownVoltage = round(voltageV, 1)
  const shownCurrent = round(currentA, 1)

  const batteryOffsetC = (hash01(`${droneId}:battery-temp`) - 0.5) * 3
  const batteryTempC =
    mode === 'flight'
      ? AMBIENT_C +
        2 +
        (BATTERY_TEMP_RISE_AT_FULL_LOAD_C * heatLoad * coolDown +
          BATTERY_TEMP_WOBBLE_C * wave('battery-wobble', 1.3)) *
          batteryWarm
      : mode === 'charging'
        ? AMBIENT_C + 4 + 14 * (maxChargeA > 0 ? currentA / maxChargeA : 0)
        : AMBIENT_C + 2

  // ---- Motors
  let motors: MotorReading[] | null = null
  if (rotorCount !== null) {
    const warmDrone = hash01(`${droneId}:warm`) < WARM_MOTOR_DRONE_FRACTION
    const warmIndex = Math.floor(hash01(`${droneId}:warm-motor`) * rotorCount)
    const warmExtraC =
      WARM_MOTOR_MIN_EXTRA_C + hash01(`${droneId}:warm-delta`) * WARM_MOTOR_EXTRA_RANGE_C
    motors = MOTOR_COMPONENT_IDS.slice(0, rotorCount).map((id, index) => {
      const rpmUnit = hash01(`${droneId}:rpm:${index}`) - 0.5
      const tempUnit = hash01(`${droneId}:temp:${index}`) - 0.5
      let rpm = 0
      // The standby temperature is where a flight starts from (no jump when the drone takes off).
      const standbyC = AMBIENT_C + 3 + tempUnit * 2
      let temperatureC = standbyC
      if (motorsRunning) {
        const thrustPerRotorKg = massKg / rotorCount
        // Each motor has its own wave, of its own amplitude and pace, on top of its fixed offset.
        const rpmWave =
          (MOTOR_RPM_WAVE.min + hash01(`${droneId}:rpm-amp:${index}`) * MOTOR_RPM_WAVE.range) *
          wave(`rpm-wave:${index}`, 3 + 2 * hash01(`${droneId}:rpm-pace:${index}`))
        rpm =
          REFERENCE_RPM *
          Math.sqrt(thrustPerRotorKg / REFERENCE_THRUST_PER_ROTOR_KG) *
          Math.sqrt(phaseFactor * dynamics) *
          (1 + rpmUnit * MOTOR_RPM_SPREAD) *
          (1 + rpmWave)
        const steadyC =
          AMBIENT_C +
          MOTOR_TEMP_RISE_AT_FULL_LOAD_C * heatLoad * coolDown +
          tempUnit * MOTOR_TEMP_SPREAD_C +
          (warmDrone && index === warmIndex ? warmExtraC : 0)
        const wobbleC =
          (MOTOR_TEMP_WOBBLE_C.min +
            hash01(`${droneId}:temp-amp:${index}`) * MOTOR_TEMP_WOBBLE_C.range) *
          wave(`temp-wobble:${index}`, 1 + hash01(`${droneId}:temp-pace:${index}`))
        temperatureC = standbyC + (steadyC - standbyC + wobbleC) * motorWarm
      }
      return {
        id,
        label: `M${index + 1}`,
        rpm: Math.round(rpm / 10) * 10,
        temperatureC: round(temperatureC, 1),
      }
    })
  }

  // ---- Connectivity: a smooth, stable function of the flight progress (never of time).
  const linkOffset = hash01(`${droneId}:link`) * 4
  const qualityPct = round(
    mode === 'flight'
      ? 92 -
          14 * Math.sin(Math.PI * progress) -
          linkOffset +
          LINK_WOBBLE_PCT * wave('link-wobble', 3)
      : 97 - linkOffset,
    0,
  )

  return {
    mode,
    carryingParcel,
    rotorCount,
    motors,
    battery: {
      chargePct,
      voltageV: shownVoltage,
      currentA: shownCurrent,
      currentDirection,
      // Power follows the displayed voltage and current, so the three always agree.
      powerW: round(shownVoltage * shownCurrent, 1),
      temperatureC: round(batteryTempC + batteryOffsetC, 1),
    },
    connectivity: { qualityPct, label: connectivityLabel(qualityPct) },
    notes,
  }
}

// ---- Health ------------------------------------------------------------------------------------

export type HealthLevel = 'nominal' | 'attention' | 'critical'

export interface HealthIndicator {
  id: 'motors' | 'battery-charge' | 'battery-temperature' | 'connectivity'
  /** The telemetry component this indicator is about (the worst motor for `motors`). */
  componentId: TelemetryComponentId
  label: string
  level: HealthLevel
  /** What was read and which threshold applies, in words. */
  detail: string
}

export interface HealthAssessment {
  level: HealthLevel
  indicators: HealthIndicator[]
  /** The indicators that are not nominal. */
  warnings: HealthIndicator[]
}

const LEVEL_ORDER: Record<HealthLevel, number> = { nominal: 0, attention: 1, critical: 2 }
export const worstLevel = (levels: readonly HealthLevel[]): HealthLevel =>
  levels.reduce<HealthLevel>(
    (current, level) => (LEVEL_ORDER[level] > LEVEL_ORDER[current] ? level : current),
    'nominal',
  )

/** Level for a value that is bad when high: above `attention` is attention, above `critical` critical. */
function highIsBad(value: number, attention: number, critical: number): HealthLevel {
  return value > critical ? 'critical' : value > attention ? 'attention' : 'nominal'
}
/** Level for a value that is bad when low: below `attention` / `critical`. */
function lowIsBelow(value: number, attention: number, critical: number): HealthLevel {
  return value < critical ? 'critical' : value < attention ? 'attention' : 'nominal'
}
/** Level for a value that is bad when low: at or below `attention` / `critical`. */
function lowIsBad(value: number, attention: number, critical: number): HealthLevel {
  return value <= critical ? 'critical' : value <= attention ? 'attention' : 'nominal'
}

/** Level of one motor temperature against the reference thresholds. */
export function motorTemperatureLevel(temperatureC: number): HealthLevel {
  return highIsBad(temperatureC, REFERENCE.motorTempC.attention, REFERENCE.motorTempC.critical)
}

/**
 * Health indicators from the displayed readings, by explicit thresholds only. A warning appears
 * exactly when a reading crosses its threshold; nothing is generated on top of the readings.
 * Battery charge is judged against the model's real reserve.
 */
export function assessHealth(
  readings: TelemetryReadings,
  minBatteryReservePct: number,
): HealthAssessment {
  const indicators: HealthIndicator[] = []
  const { motorTempC, batteryTempC, connectivityPct, batteryCriticalPct } = REFERENCE

  if (readings.motors && readings.motors.length > 0) {
    const hottest = readings.motors.reduce((a, b) => (b.temperatureC > a.temperatureC ? b : a))
    const level = highIsBad(hottest.temperatureC, motorTempC.attention, motorTempC.critical)
    indicators.push({
      id: 'motors',
      componentId: hottest.id,
      label: 'Motors',
      level,
      detail:
        level === 'nominal'
          ? `Hottest motor ${hottest.label} at ${hottest.temperatureC.toFixed(1)} °C, within the ${motorTempC.attention} °C reference.`
          : `${hottest.label} at ${hottest.temperatureC.toFixed(1)} °C is above the ${
              level === 'critical' ? motorTempC.critical : motorTempC.attention
            } °C ${level} threshold.`,
    })
  }

  const criticalCharge = Math.min(batteryCriticalPct, minBatteryReservePct)
  const chargeLevel = lowIsBad(readings.battery.chargePct, minBatteryReservePct, criticalCharge)
  indicators.push({
    id: 'battery-charge',
    componentId: 'battery',
    label: 'Battery charge',
    level: chargeLevel,
    detail:
      chargeLevel === 'nominal'
        ? `Charge ${readings.battery.chargePct}% is above the ${minBatteryReservePct}% reserve.`
        : `Charge ${readings.battery.chargePct}% is at or below the ${
            chargeLevel === 'critical' ? criticalCharge : minBatteryReservePct
          }% ${chargeLevel} threshold.`,
  })

  const tempLevel = highIsBad(
    readings.battery.temperatureC,
    batteryTempC.attention,
    batteryTempC.critical,
  )
  indicators.push({
    id: 'battery-temperature',
    componentId: 'battery',
    label: 'Battery temperature',
    level: tempLevel,
    detail:
      tempLevel === 'nominal'
        ? `Battery at ${readings.battery.temperatureC.toFixed(1)} °C, within the ${batteryTempC.attention} °C reference.`
        : `Battery at ${readings.battery.temperatureC.toFixed(1)} °C is above the ${
            tempLevel === 'critical' ? batteryTempC.critical : batteryTempC.attention
          } °C ${tempLevel} threshold.`,
  })

  const linkLevel = lowIsBelow(
    readings.connectivity.qualityPct,
    connectivityPct.attention,
    connectivityPct.critical,
  )
  indicators.push({
    id: 'connectivity',
    componentId: 'connectivity',
    label: 'Connectivity',
    level: linkLevel,
    detail:
      linkLevel === 'nominal'
        ? `Link quality ${readings.connectivity.qualityPct}% is at or above ${connectivityPct.attention}%.`
        : `Link quality ${readings.connectivity.qualityPct}% is below the ${
            linkLevel === 'critical' ? connectivityPct.critical : connectivityPct.attention
          }% ${linkLevel} threshold.`,
  })

  return {
    level: worstLevel(indicators.map((indicator) => indicator.level)),
    indicators,
    warnings: indicators.filter((indicator) => indicator.level !== 'nominal'),
  }
}
