import { describe, expect, it } from 'vitest'

import {
  CAMERA_LIMITS,
  CAMERA_TARGET,
  DEFAULT_CAMERA_POSITION,
  fitZoom,
  orbitPosition,
  zoomPosition,
  type Vec3,
} from './cameraMath'

const distance = (p: Vec3) =>
  Math.hypot(p[0] - CAMERA_TARGET[0], p[1] - CAMERA_TARGET[1], p[2] - CAMERA_TARGET[2])
const cosPolar = (p: Vec3) => (p[1] - CAMERA_TARGET[1]) / distance(p)

describe('camera maths', () => {
  it('orbits at a constant distance', () => {
    const moved = orbitPosition(DEFAULT_CAMERA_POSITION, CAMERA_TARGET, 0.8, -0.2)
    expect(distance(moved)).toBeCloseTo(distance(DEFAULT_CAMERA_POSITION))
    expect(moved[0]).not.toBeCloseTo(DEFAULT_CAMERA_POSITION[0])
  })

  it('clamps the tilt so the model is never lost over the poles', () => {
    const top = orbitPosition(DEFAULT_CAMERA_POSITION, CAMERA_TARGET, 0, -10)
    const bottom = orbitPosition(DEFAULT_CAMERA_POSITION, CAMERA_TARGET, 0, 10)
    expect(cosPolar(top)).toBeCloseTo(Math.cos(CAMERA_LIMITS.minPolar))
    expect(cosPolar(bottom)).toBeCloseTo(Math.cos(CAMERA_LIMITS.maxPolar))
  })

  it('keeps zoom within the distance limits', () => {
    expect(distance(zoomPosition(DEFAULT_CAMERA_POSITION, CAMERA_TARGET, 0.01))).toBeCloseTo(
      CAMERA_LIMITS.minDistance,
    )
    expect(distance(zoomPosition(DEFAULT_CAMERA_POSITION, CAMERA_TARGET, 100))).toBeCloseTo(
      CAMERA_LIMITS.maxDistance,
    )
  })

  it('zooms the projection out only on narrow viewports', () => {
    expect(fitZoom(2)).toBe(1)
    expect(fitZoom(0.5)).toBeLessThan(1)
    expect(fitZoom(0.01)).toBe(0.35)
  })
})
