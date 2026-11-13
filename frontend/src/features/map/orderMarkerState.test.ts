import { describe, expect, it } from 'vitest'

import { ORDER_STATUSES } from '../../types/order'
import { ORDER_MARKER_STATES, orderMarkerState } from './orderMarkerState'

describe('orderMarkerState', () => {
  it.each([
    ['CREATED', 'pending'],
    ['AWAITING_HANDOVER', 'pending'],
    ['READY_FOR_PICKUP', 'pending'],
    ['OUT_FOR_DELIVERY', 'in_progress'],
    ['DELIVERED', 'delivered'],
    ['CANCELLED', 'cancelled'],
  ])('maps %s to %s', (status, state) => {
    expect(orderMarkerState(status)).toBe(state)
  })

  it('shows an undelivered order of a failed flight as interrupted, and nothing else', () => {
    expect(orderMarkerState('OUT_FOR_DELIVERY', true)).toBe('interrupted')
    expect(orderMarkerState('OUT_FOR_DELIVERY', false)).toBe('in_progress')
    expect(orderMarkerState('DELIVERED', true)).toBe('delivered') // a delivery stays delivered
    expect(orderMarkerState('CANCELLED', true)).toBe('cancelled') // a cancellation stays visible
    expect(ORDER_MARKER_STATES.interrupted.label).toBe('Interrupted')
    expect(ORDER_MARKER_STATES.interrupted.diamondClasses).not.toContain('bg-status-ok')
  })

  it('covers every status the frontend knows', () => {
    for (const status of ORDER_STATUSES) expect(orderMarkerState(status)).not.toBe('other')
  })

  it('shows an unknown status neutrally instead of guessing', () => {
    expect(orderMarkerState('FAILED')).toBe('other')
    expect(orderMarkerState('')).toBe('other')
    expect(orderMarkerState('toString')).toBe('other')
  })

  it('gives each state its own words and colour', () => {
    expect(ORDER_MARKER_STATES.pending.label).toBe('Waiting')
    expect(ORDER_MARKER_STATES.in_progress.label).toBe('In delivery')
    expect(ORDER_MARKER_STATES.delivered.label).toBe('Delivered')
    expect(ORDER_MARKER_STATES.cancelled.label).toBe('Cancelled')
    expect(ORDER_MARKER_STATES.cancelled.diamondClasses).toContain('bg-status-critical') // red
    expect(ORDER_MARKER_STATES.cancelled.diamondClasses).not.toContain('bg-status-ok') // never green
    expect(ORDER_MARKER_STATES.cancelled.swatchClass).toBe('bg-status-critical')
    expect(ORDER_MARKER_STATES.pending.diamondClasses).toContain('bg-status-neutral')
    expect(ORDER_MARKER_STATES.in_progress.diamondClasses).toContain('bg-status-active')
    expect(ORDER_MARKER_STATES.delivered.diamondClasses).toContain('bg-status-ok')
  })
})
