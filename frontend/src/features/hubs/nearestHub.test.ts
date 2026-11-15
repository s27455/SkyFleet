import { describe, expect, it } from 'vitest'

import type { Hub } from '../../types/hub'
import { describeNearestHub, nearestHub } from './nearestHub'

const hub = (id: string, lng: number, lat: number): Hub => ({
  id,
  name: id.toUpperCase(),
  address: 'x',
  coordinates: [lng, lat],
  droneCapacity: 6,
})
const GALERIA = hub('galeria', 18.6, 54.38)
const FORUM = hub('forum', 18.65, 54.35)

describe('nearestHub', () => {
  it('is the geographically closest Hub and changes as the drone moves', () => {
    expect(nearestHub([18.601, 54.379], [GALERIA, FORUM])?.hub.id).toBe('galeria')
    expect(nearestHub([18.63, 54.36], [GALERIA, FORUM])?.hub.id).toBe('forum')
  })

  it('reports the distance in metres', () => {
    const result = nearestHub([18.6, 54.38], [GALERIA, FORUM])
    expect(result?.distanceM).toBe(0)
  })

  it('breaks an exact tie with the lower Hub id, whatever the order', () => {
    const a = hub('a', 18.6, 54.38)
    const b = hub('b', 18.6, 54.38)
    expect(nearestHub([18.7, 54.4], [b, a])?.hub.id).toBe('a')
  })

  it('has no answer without Hubs or with an unusable position', () => {
    expect(nearestHub([18.6, 54.38], [])).toBeNull()
    expect(nearestHub([Number.NaN, 54.38], [GALERIA])).toBeNull()
  })

  it('ignores a Hub with unusable coordinates', () => {
    const broken = hub('broken', Number.NaN, 54.38)
    expect(nearestHub([18.6, 54.38], [broken, FORUM])?.hub.id).toBe('forum')
    expect(nearestHub([18.6, 54.38], [broken])).toBeNull()
  })
})

describe('describeNearestHub', () => {
  it('formats metres below a kilometre and kilometres above', () => {
    expect(describeNearestHub([18.6, 54.381], [GALERIA])).toMatch(/^GALERIA · \d+ m$/)
    expect(describeNearestHub([18.65, 54.4], [FORUM])).toMatch(/^FORUM · \d+\.\d km$/)
  })

  it('shows a dash when it cannot be determined', () => {
    expect(describeNearestHub([18.6, 54.38], [])).toBe('—')
  })
})
