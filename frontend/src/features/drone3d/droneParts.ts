/**
 * Identifiers of the separately addressable parts of the drone model. Each id is the `name` of a
 * Three.js group in the model, so later features (016D) can select or highlight a part without
 * rebuilding any geometry.
 */
export const MOTOR_IDS = ['motor-fl', 'motor-fr', 'motor-rl', 'motor-rr'] as const
export type MotorId = (typeof MOTOR_IDS)[number]

export const DRONE_PART_IDS = [
  'fuselage',
  'battery',
  'cargo-bay',
  'landing-gear',
  ...MOTOR_IDS,
] as const
export type DronePartId = (typeof DRONE_PART_IDS)[number]

export function isDronePartId(value: string): value is DronePartId {
  return (DRONE_PART_IDS as readonly string[]).includes(value)
}

/** Name of the propeller group that belongs to a motor, e.g. `propeller-fl`. */
export function propellerName(motor: MotorId): string {
  return `propeller-${motor.slice('motor-'.length)}`
}

/** Health level a part is drawn with. Same words as the telemetry's health levels. */
export type PartLevel = 'nominal' | 'attention' | 'critical'

/** What the viewer shows on one part: a label, and its level as a highlight and in words. */
export interface PartAnnotation {
  /** Short label shown on the model, e.g. `M1` or `Battery`. */
  label: string
  level: PartLevel
}

/** Level in words, for labels and accessible names (colour is never the only cue). */
export const PART_LEVEL_TEXT: Readonly<Record<PartLevel, string>> = {
  nominal: 'Nominal',
  attention: 'Attention',
  critical: 'Critical',
}
