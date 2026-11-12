import { describe, expect, it } from 'vitest'

import { type FlightMotion, interpolatePosition } from './interpolation'

const motion = (overrides: Partial<FlightMotion> = {}): FlightMotion => ({
  position: [18.0, 54.0],
  target: { position: [18.1, 54.2], etaS: 10 },
  snapshotAgeS: 0,
  ...overrides,
})

describe('interpolatePosition', () => {
  it('starts at the snapshot position', () => {
    expect(interpolatePosition(motion(), 0)).toEqual([18.0, 54.0])
  })

  it('moves in a straight line toward the target over the backend eta', () => {
    const [lng, lat] = interpolatePosition(motion(), 5)

    expect(lng).toBeCloseTo(18.05)
    expect(lat).toBeCloseTo(54.1)
  })

  it('arrives at the target after the eta and never goes past it', () => {
    expect(interpolatePosition(motion(), 10)).toEqual([18.1, 54.2])
    expect(interpolatePosition(motion(), 500)).toEqual([18.1, 54.2])
  })

  it('counts the time between the snapshot and the response (the backend clock)', () => {
    // The snapshot is already 4 s old when it arrives: 4 s of the 10 s are flown.
    const [lng] = interpolatePosition(motion({ snapshotAgeS: 4 }), 0)

    expect(lng).toBeCloseTo(18.04)
  })

  it('stays put without a target or with no time left', () => {
    expect(interpolatePosition(motion({ target: null }), 5)).toEqual([18.0, 54.0])
    expect(interpolatePosition(motion({ target: { position: [19, 55], etaS: 0 } }), 5)).toEqual([
      18.0, 54.0,
    ])
  })

  it('treats a negative elapsed time as zero', () => {
    expect(interpolatePosition(motion(), -3)).toEqual([18.0, 54.0])
  })

  it('never changes the snapshot it is given', () => {
    const m = motion()
    const before = JSON.stringify(m)

    interpolatePosition(m, 5)

    expect(JSON.stringify(m)).toBe(before)
  })
})
