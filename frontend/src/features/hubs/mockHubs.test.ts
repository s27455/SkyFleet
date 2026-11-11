import { describe, expect, it } from 'vitest'

import { TRICITY_BOUNDS } from '../map/mapConfig'
import { getHubs } from './mockHubs'

describe('mock hubs', () => {
  const hubs = getHubs()

  it('provides the four initial hubs', () => {
    expect(hubs.map((hub) => hub.name)).toEqual([
      'Galeria Bałtycka',
      'Forum Gdańsk',
      'Centrum Riviera',
      'Centrum Handlowe Osowa',
    ])
  })

  it('uses unique stable ids', () => {
    expect(new Set(hubs.map((hub) => hub.id)).size).toBe(hubs.length)
  })

  it('sets the initial drone capacity to 50 for every hub', () => {
    hubs.forEach((hub) => expect(hub.droneCapacity).toBe(50))
  })

  it('places every hub inside the Tricity bounds', () => {
    const [[west, south], [east, north]] = TRICITY_BOUNDS as [[number, number], [number, number]]
    hubs.forEach(({ coordinates: [lng, lat] }) => {
      expect(lng).toBeGreaterThanOrEqual(west)
      expect(lng).toBeLessThanOrEqual(east)
      expect(lat).toBeGreaterThanOrEqual(south)
      expect(lat).toBeLessThanOrEqual(north)
    })
  })
})
