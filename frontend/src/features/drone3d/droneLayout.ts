import { MOTOR_IDS, type MotorId } from './droneParts'

/**
 * Layout constants of the model, in scene units (about one unit per metre-ish; only proportions
 * matter). The drone's nose points to +Z, up is +Y. Kept free of Three.js so it is unit-testable.
 */
export const ARM_REACH = 1.02 // motor offset along X and Z from the centre
export const MOTOR_HEIGHT = 0.1
export const PROPELLER_RADIUS = 0.62
export const PROPELLER_LIFT = 0.2 // propeller plane above the motor origin
export const FUSELAGE_HALF_LENGTH = 0.98
export const SKID_Y = -0.82

export interface MotorLayout {
  id: MotorId
  position: readonly [x: number, y: number, z: number]
  /** +1 / -1: neighbouring propellers counter-rotate, as on a real quadcopter. */
  spin: 1 | -1
}

const SIGNS: Record<MotorId, readonly [x: 1 | -1, z: 1 | -1]> = {
  'motor-fl': [-1, 1],
  'motor-fr': [1, 1],
  'motor-rl': [-1, -1],
  'motor-rr': [1, -1],
}

export const MOTOR_LAYOUT: readonly MotorLayout[] = MOTOR_IDS.map((id) => {
  const [sx, sz] = SIGNS[id]
  return {
    id,
    position: [sx * ARM_REACH, MOTOR_HEIGHT, sz * ARM_REACH],
    spin: (sx * sz) as 1 | -1,
  }
})
