import { describe, expect, it } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { isUsableCoordinate, resolveFocusTarget } from './focusTarget'

const hub = (id: string, coordinates: [number, number]): Hub =>
  ({ id, name: `Hub ${id}`, address: 'x', coordinates, droneCapacity: 50 }) as Hub
const drone = (id: string, coordinates: [number, number], hubId = 'a'): Drone =>
  ({ id, hubId, status: 'IDLE', batteryPct: 90, coordinates }) as unknown as Drone
const order = (id: string, coordinates: [number, number]): Order =>
  ({ id, originHubId: 'a', coordinates, destinationAddress: 'x' }) as unknown as Order

const DATA = {
  hubs: [hub('a', [18.6, 54.38]), hub('b', [18.5, 54.5])],
  drones: [drone('DRN-1', [18.61, 54.39]), drone('DRN-2', [18.6, 54.38])],
  orders: [order('ORD-1', [18.62, 54.36])],
}

describe('isUsableCoordinate', () => {
  it.each([
    [[18.6, 54.38]],
    [[-0.5, 51.5]],
    [[180, 90]],
    [[-180, -90]],
    [[0, 54.38]], // a real longitude of 0 is fine; only the pair (0, 0) is "no position"
    [[18.6, 0]],
  ])('accepts %j', (value) => expect(isUsableCoordinate(value)).toBe(true))

  it.each([
    [[0, 0]],
    [[Number.NaN, 54.38]],
    [[18.6, Number.NaN]],
    [[Number.POSITIVE_INFINITY, 54.38]],
    [[181, 54.38]],
    [[18.6, 91]],
    [[-181, 0.1]],
    [[18.6]],
    [[18.6, 54.38, 10]],
    [['18.6', '54.38']],
    [null],
    [undefined],
    ['18.6,54.38'],
  ])('rejects %j', (value) => expect(isUsableCoordinate(value)).toBe(false))
})

describe('resolveFocusTarget', () => {
  it("uses a drone's latest known coordinates", () => {
    expect(resolveFocusTarget('drone', 'DRN-1', DATA)).toEqual({
      label: 'DRN-1',
      position: [18.61, 54.39],
    })
  })

  it('uses the coordinates of a docked drone, which are its Hub', () => {
    expect(resolveFocusTarget('drone', 'DRN-2', DATA).position).toEqual([18.6, 54.38])
  })

  it('uses the Hub coordinates and names the Hub', () => {
    expect(resolveFocusTarget('hub', 'b', DATA)).toEqual({
      label: 'Hub b',
      position: [18.5, 54.5],
    })
  })

  it("uses an order's stored delivery destination, not its drone or origin Hub", () => {
    const result = resolveFocusTarget('order', 'ORD-1', DATA)

    expect(result.position).toEqual([18.62, 54.36])
    expect(result.position).not.toEqual([18.6, 54.38]) // the origin Hub
  })

  it('gives no position for an unknown entity, and still a label for a message', () => {
    expect(resolveFocusTarget('drone', 'DRN-404', DATA)).toEqual({
      label: 'DRN-404',
      position: null,
    })
    expect(resolveFocusTarget('hub', 'nope', DATA)).toEqual({ label: 'nope', position: null })
    expect(resolveFocusTarget('order', 'ORD-404', DATA).position).toBeNull()
  })

  it('gives no position for an unusable stored location', () => {
    const data = {
      ...DATA,
      drones: [drone('DRN-0', [0, 0]), drone('DRN-N', [Number.NaN, 54])],
      orders: [order('ORD-0', [0, 0]), order('ORD-FAR', [200, 54])],
      hubs: [hub('z', [18.6, 95])],
    }

    expect(resolveFocusTarget('drone', 'DRN-0', data).position).toBeNull()
    expect(resolveFocusTarget('drone', 'DRN-N', data).position).toBeNull()
    expect(resolveFocusTarget('order', 'ORD-0', data).position).toBeNull()
    expect(resolveFocusTarget('order', 'ORD-FAR', data).position).toBeNull()
    expect(resolveFocusTarget('hub', 'z', data).position).toBeNull()
  })

  it('does not modify or "correct" the stored coordinates of a historical order', () => {
    const stored: [number, number] = [18.5972, 54.3768] // an old, approximate point
    const result = resolveFocusTarget('order', 'ORD-1', {
      ...DATA,
      orders: [order('ORD-1', stored)],
    })

    expect(result.position).toEqual([18.5972, 54.3768])
  })
})
