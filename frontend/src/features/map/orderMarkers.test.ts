import { describe, expect, it } from 'vitest'

import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import {
  computeOrderOffsets,
  createOrderMarkerElement,
  orderMarkerLabel,
  setOrderMarkerSelected,
  updateOrderMarkerElement,
} from './orderMarkers'

function order(id: string, coordinates: [number, number]): Order {
  return {
    id,
    originHubId: 'hub-a',
    destinationAddress: 'ul. Test 1',
    coordinates,
    packageWeightKg: 1.5,
    status: 'READY_FOR_PICKUP',
    deliveredAt: null,
    cancelledAt: null,
    deliveryFailedAt: null,
    createdAt: '2026-11-11T21:53:08Z',
    updatedAt: '2026-11-11T21:53:08Z',
  }
}

const HUB: Hub = {
  id: 'hub-a',
  name: 'Hub A',
  address: 'Ulica 1',
  coordinates: [18.6, 54.4],
  droneCapacity: 50,
}

const distance = ([x, y]: readonly [number, number]) => Math.hypot(x, y)

describe('computeOrderOffsets', () => {
  it('gives no offset to a lone destination away from every Hub', () => {
    expect(computeOrderOffsets([order('ORD-001', [18.7, 54.5])], [HUB]).size).toBe(0)
  })

  it('spreads orders that share a destination on a ring, deterministically, without moving them', () => {
    const point: [number, number] = [18.7, 54.5]
    const orders = ['ORD-003', 'ORD-001', 'ORD-002'].map((id) => order(id, point))
    const before = JSON.stringify(orders)

    const offsets = computeOrderOffsets(orders, [HUB])

    const values = ['ORD-001', 'ORD-002', 'ORD-003'].map((id) => offsets.get(id)!)
    expect(new Set(values.map((v) => v.join(','))).size).toBe(3)
    expect(values[0][1]).toBeLessThan(0) // the first order sits at the top
    for (let i = 0; i < values.length; i++) {
      for (let j = i + 1; j < values.length; j++) {
        expect(
          distance([values[i][0] - values[j][0], values[i][1] - values[j][1]]),
        ).toBeGreaterThanOrEqual(24)
      }
    }
    expect(JSON.stringify(orders)).toBe(before)
  })

  it('moves a destination that sits exactly on a Hub clear of the Hub marker', () => {
    const offsets = computeOrderOffsets([order('ORD-001', HUB.coordinates)], [HUB])

    expect(distance(offsets.get('ORD-001')!)).toBeGreaterThanOrEqual(40 / 2 + 24 / 2)
  })
})

describe('order marker element', () => {
  it('has an accessible name with id, status and weight, and a hidden diamond mark', () => {
    const element = createOrderMarkerElement(order('ORD-007', [18.7, 54.5]), () => {})

    expect(element.getAttribute('aria-label')).toBe(
      'Order ORD-007 destination, Ready for pickup (Waiting), 1.5 kg',
    )
    expect(orderMarkerLabel(order('ORD-007', [18.7, 54.5]))).toBe(
      element.getAttribute('aria-label'),
    )
    expect(element.dataset.markerKind).toBe('order')
    expect(element).toHaveClass('size-6', 'z-5')
    expect(element.querySelector('[data-order-diamond]')).toHaveAttribute('aria-hidden', 'true')
    expect(element.querySelector('[data-order-diamond]')).toHaveClass('rotate-45')
  })

  it('updates the selected state in place, with a non-colour ring cue', () => {
    const element = createOrderMarkerElement(order('ORD-007', [18.7, 54.5]), () => {})
    const diamond = element.querySelector('[data-order-diamond]')!

    setOrderMarkerSelected(element, true)
    expect(element).toHaveAttribute('aria-pressed', 'true')
    expect(diamond).toHaveClass('ring-4')

    setOrderMarkerSelected(element, false)
    expect(element).toHaveAttribute('aria-pressed', 'false')
    expect(diamond).not.toHaveClass('ring-4')
  })

  it('reports clicks', () => {
    let clicks = 0
    const element = createOrderMarkerElement(order('ORD-007', [18.7, 54.5]), () => (clicks += 1))

    element.click()

    expect(clicks).toBe(1)
  })
})

describe('order marker state (Feature 017B)', () => {
  const withStatus = (status: Order['status']): Order => ({
    ...order('ORD-007', [18.7, 54.5]),
    status,
  })

  it.each([
    ['READY_FOR_PICKUP', 'pending', 'bg-status-neutral', 'Waiting'],
    ['OUT_FOR_DELIVERY', 'in_progress', 'bg-status-active', 'In delivery'],
    ['DELIVERED', 'delivered', 'bg-status-ok', 'Delivered'],
  ] as const)('draws %s as %s with the state in words', (status, state, colour, word) => {
    const element = createOrderMarkerElement(withStatus(status), () => {})

    expect(element.dataset.orderState).toBe(state)
    expect(element.querySelector('[data-order-diamond]')).toHaveClass(colour, 'border-fg')
    expect(element.getAttribute('aria-label')).toContain(`(${word})`)
  })

  it('changes colour, state and name in place, keeping the element and its click handler', () => {
    let clicks = 0
    const element = createOrderMarkerElement(withStatus('READY_FOR_PICKUP'), () => (clicks += 1))
    const diamond = element.querySelector('[data-order-diamond]')!

    updateOrderMarkerElement(element, withStatus('OUT_FOR_DELIVERY'))
    expect(diamond).toHaveClass('bg-status-active')
    expect(diamond).not.toHaveClass('bg-status-neutral')

    updateOrderMarkerElement(element, withStatus('DELIVERED'))
    expect(diamond).toHaveClass('bg-status-ok')
    expect(diamond).not.toHaveClass('bg-status-active')
    expect(element.getAttribute('aria-label')).toContain('Delivered (Delivered)')
    element.click()
    expect(clicks).toBe(1)
  })

  it('keeps the state colour while selected and after a state change', () => {
    const element = createOrderMarkerElement(withStatus('OUT_FOR_DELIVERY'), () => {})
    const diamond = element.querySelector('[data-order-diamond]')!

    setOrderMarkerSelected(element, true)
    updateOrderMarkerElement(element, withStatus('DELIVERED'))

    expect(diamond).toHaveClass('bg-status-ok', 'ring-4') // new colour, selection ring kept
    setOrderMarkerSelected(element, false)
    expect(diamond).toHaveClass('bg-status-ok')
    expect(diamond).not.toHaveClass('ring-4')
  })

  it('shows an unknown status neutrally and does not throw', () => {
    const element = createOrderMarkerElement(
      { ...withStatus('DELIVERED'), status: 'FAILED' as Order['status'] },
      () => {},
    )

    expect(element.dataset.orderState).toBe('other')
  })
})
