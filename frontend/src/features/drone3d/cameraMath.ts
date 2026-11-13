/** Pure orbit-camera maths for the keyboard and button controls (no Three.js needed). */

export type Vec3 = readonly [x: number, y: number, z: number]

export const CAMERA_LIMITS = {
  minDistance: 3.2,
  maxDistance: 9,
  minPolar: 0.25,
  maxPolar: Math.PI * 0.62,
} as const

export const DEFAULT_CAMERA_POSITION: Vec3 = [2.75, 1.75, 3.35]
export const CAMERA_TARGET: Vec3 = [0, -0.15, 0]

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

/** Rotates `position` around `target` by the given azimuth / polar deltas (radians), clamped. */
export function orbitPosition(
  position: Vec3,
  target: Vec3,
  deltaAzimuth: number,
  deltaPolar: number,
): Vec3 {
  const dx = position[0] - target[0]
  const dy = position[1] - target[1]
  const dz = position[2] - target[2]
  const radius = Math.hypot(dx, dy, dz)
  const azimuth = Math.atan2(dx, dz) + deltaAzimuth
  const polar = clamp(
    Math.acos(clamp(dy / radius, -1, 1)) + deltaPolar,
    CAMERA_LIMITS.minPolar,
    CAMERA_LIMITS.maxPolar,
  )
  const sinPolar = Math.sin(polar)
  return [
    target[0] + radius * sinPolar * Math.sin(azimuth),
    target[1] + radius * Math.cos(polar),
    target[2] + radius * sinPolar * Math.cos(azimuth),
  ]
}

/** Moves `position` along its line to `target` by `factor` (<1 zooms in), within the limits. */
export function zoomPosition(position: Vec3, target: Vec3, factor: number): Vec3 {
  const dx = position[0] - target[0]
  const dy = position[1] - target[1]
  const dz = position[2] - target[2]
  const radius = Math.hypot(dx, dy, dz)
  const next = clamp(radius * factor, CAMERA_LIMITS.minDistance, CAMERA_LIMITS.maxDistance)
  const scale = next / radius
  return [target[0] + dx * scale, target[1] + dy * scale, target[2] + dz * scale]
}

/** Camera zoom that keeps the whole drone horizontally in view on narrow (portrait) viewports. */
export function fitZoom(aspect: number): number {
  return clamp(aspect / 1.6, 0.35, 1)
}
