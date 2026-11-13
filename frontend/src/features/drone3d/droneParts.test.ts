import { describe, expect, it } from 'vitest'

import { LABEL_ANCHORS, MOTOR_LAYOUT, PROPELLER_RADIUS } from './droneLayout'
import { DRONE_PART_IDS, MOTOR_IDS, isDronePartId, propellerName } from './droneParts'

describe('drone parts', () => {
  it('has unique ids including four motors, a battery and a cargo bay', () => {
    expect(new Set(DRONE_PART_IDS).size).toBe(DRONE_PART_IDS.length)
    expect(MOTOR_IDS).toHaveLength(4)
    expect(DRONE_PART_IDS).toEqual(expect.arrayContaining(['battery', 'cargo-bay', 'landing-gear']))
  })

  it('recognises part ids and names propellers after their motor', () => {
    expect(isDronePartId('motor-fl')).toBe(true)
    expect(isDronePartId('wing')).toBe(false)
    expect(propellerName('motor-rr')).toBe('propeller-rr')
  })
})

describe('motor layout', () => {
  it('places four distinct motors at the corners', () => {
    const corners = new Set(
      MOTOR_LAYOUT.map((m) => `${Math.sign(m.position[0])}${Math.sign(m.position[2])}`),
    )
    expect(MOTOR_LAYOUT.map((m) => m.id)).toEqual([...MOTOR_IDS])
    expect(corners.size).toBe(4)
  })

  it('counter-rotates neighbouring propellers', () => {
    const spin = Object.fromEntries(MOTOR_LAYOUT.map((m) => [m.id, m.spin]))
    expect(spin['motor-fl']).toBe(spin['motor-rr'])
    expect(spin['motor-fr']).toBe(spin['motor-rl'])
    expect(spin['motor-fl']).not.toBe(spin['motor-fr'])
  })

  it('keeps neighbouring propeller discs from overlapping', () => {
    const [a, b] = [MOTOR_LAYOUT[0].position, MOTOR_LAYOUT[1].position]
    expect(Math.abs(a[0] - b[0])).toBeGreaterThan(2 * PROPELLER_RADIUS)
  })
})

describe('label anchors', () => {
  it('has an anchor above every motor and the battery, and none for other parts', () => {
    expect(Object.keys(LABEL_ANCHORS).sort()).toEqual([...MOTOR_IDS, 'battery'].sort())
    for (const layout of MOTOR_LAYOUT) {
      const [x, y, z] = LABEL_ANCHORS[layout.id]!
      // Outside the motor, on the same side of the airframe, and above the propeller plane.
      expect(Math.sign(x)).toBe(Math.sign(layout.position[0]))
      expect(Math.sign(z)).toBe(Math.sign(layout.position[2]))
      expect(Math.abs(x)).toBeGreaterThan(Math.abs(layout.position[0]))
      expect(Math.abs(z)).toBeGreaterThan(Math.abs(layout.position[2]))
      expect(y).toBeGreaterThan(layout.position[1])
    }
  })
})
