import type { DronePartId } from '../drone3d/droneParts'

/**
 * Constants of the simulated telemetry (Feature 016C). Every number here is a demonstration
 * estimate chosen to look plausible for a ~9 kg delivery drone. None of it is sensor data or an
 * engineering specification.
 */

/**
 * Rotor count by the backend's `airframe_type`. The MVP fleet is quadcopters only; any other
 * airframe gets no motor telemetry rather than a guess.
 */
const AIRFRAME_ROTORS: Readonly<Record<string, number>> = { quadcopter: 4 }

/** The number of rotors of an airframe, or `null` when it is not known (nothing is guessed). */
export function rotorCountFor(airframeType: string): number | null {
  return AIRFRAME_ROTORS[airframeType.trim().toLowerCase()] ?? null
}

/** Stable ids of the telemetry components, for later selection (016D). Motors are M1..M4. */
export const MOTOR_COMPONENT_IDS = ['motor-1', 'motor-2', 'motor-3', 'motor-4'] as const
export type MotorComponentId = (typeof MOTOR_COMPONENT_IDS)[number]
export type TelemetryComponentId = MotorComponentId | 'battery' | 'connectivity'

/**
 * Which part of the 3D model a component belongs to: M1 front-left, M2 front-right, M3 rear-right,
 * M4 rear-left.
 */
export const MODEL_PART_FOR_COMPONENT: Readonly<
  Partial<Record<TelemetryComponentId, DronePartId>>
> = {
  'motor-1': 'motor-fl',
  'motor-2': 'motor-fr',
  'motor-3': 'motor-rr',
  'motor-4': 'motor-rl',
  battery: 'battery',
}

/** Fixed ambient temperature: there is no weather data in the API. */
export const AMBIENT_C = 22

// ---- Power and battery model -------------------------------------------------------------------
export const HOVER_W_PER_KG = 130
/** Headroom above hover at maximum take-off mass; 100% motor load. */
export const MAX_LOAD_MARGIN = 1.3
/** Extra power per flight phase (climb with a parcel, hover to deliver, ...). */
export const PHASE_POWER_FACTOR: Readonly<Record<string, number>> = {
  OUTBOUND: 1.1,
  DELIVERING: 1.15,
  RETURNING: 1.0,
  DIVERTING: 1.05,
}
export const DEFAULT_PHASE_FACTOR = 1.0
/** Phases in which the parcel is on board, as the flight section already words them. */
export const PARCEL_ON_BOARD_PHASES: readonly string[] = ['OUTBOUND', 'DELIVERING']
/** Phases after which the motors are off. */
export const MOTORS_OFF_PHASES: readonly string[] = ['LANDED', 'EMERGENCY']

export const NOMINAL_PACK_VOLTAGE_V = 22.2
/** Internal resistance of the pack (voltage sag under load, rise while charging). */
export const PACK_RESISTANCE_OHM = 0.018
/** Open-circuit voltage of an estimated 6-cell pack by charge level: [percent, volts]. */
export const OPEN_CIRCUIT_CURVE: readonly (readonly [number, number])[] = [
  [0, 19.8],
  [10, 20.9],
  [20, 21.5],
  [50, 22.6],
  [80, 24.0],
  [100, 25.2],
]
export const STANDBY_CURRENT_A = 0.4
export const MAINTENANCE_CURRENT_A = 0.2

// ---- Motors ------------------------------------------------------------------------------------
/** RPM of one rotor carrying 1.5 kg (a reference load). RPM scales with sqrt(thrust). */
export const REFERENCE_RPM = 4200
export const REFERENCE_THRUST_PER_ROTOR_KG = 1.5
export const MOTOR_TEMP_RISE_AT_FULL_LOAD_C = 40
export const BATTERY_TEMP_RISE_AT_FULL_LOAD_C = 18
/** Spread between motors: fixed per drone and motor, never changing over time. */
export const MOTOR_RPM_SPREAD = 0.04
export const MOTOR_TEMP_SPREAD_C = 6

/**
 * Roughly one drone in six has one motor that runs warmer under load, by 8 to 14 degrees. It is a
 * fixed property of the drone id, not a fault that appears or goes away.
 */
export const WARM_MOTOR_DRONE_FRACTION = 1 / 6
export const WARM_MOTOR_MIN_EXTRA_C = 8
export const WARM_MOTOR_EXTRA_RANGE_C = 6

// ---- Reference ranges and warning thresholds (all estimates) -----------------------------------
export const REFERENCE = {
  motorTempC: { attention: 70, critical: 85 },
  motorRpmInFlight: { min: 3000, max: 7000 },
  batteryTempC: { min: 15, attention: 45, critical: 55 },
  batteryVoltageV: { min: 19, max: 25.2 },
  currentMaxA: 110,
  powerMaxW: 2400,
  connectivityPct: { attention: 70, critical: 50 },
  /** Battery charge is judged against the model's real reserve; critical at or below this. */
  batteryCriticalPct: 10,
} as const

export const CONNECTIVITY_BANDS = [
  { min: 85, label: 'Excellent' },
  { min: 70, label: 'Good' },
  { min: 50, label: 'Weak' },
  { min: 0, label: 'Poor' },
] as const
