import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { EventTimeline } from './EventTimeline'

afterEach(() => vi.unstubAllGlobals())

const FAILURE = {
  id: 10,
  event_type: 'DRONE_FAILURE',
  occurred_at: '2026-11-15T10:00:00+00:00',
  origin: 'AUTOMATIC',
  order_id: 'ORD-1',
  mission_id: 'MIS-1',
  flight_id: 'MIS-1',
  drone_id: 'DRN-010',
  reason: 'Simulated drone failure (before delivery); emergency landing',
  details: { stage: 'BEFORE_DELIVERY', landing_position: [18.6, 54.4] },
}

const RECOVERED = {
  id: 11,
  event_type: 'DRONE_RECOVERED',
  occurred_at: '2026-11-15T10:07:00+00:00',
  origin: 'AUTOMATIC',
  order_id: 'ORD-1',
  mission_id: 'MIS-1',
  flight_id: 'MIS-1',
  drone_id: 'DRN-010',
  reason: 'Drone recovered by ground crew and moved to Centrum Riviera',
  details: {
    hub_id: 'hub-centrum-riviera',
    from_position: [18.6, 54.4],
    status: 'CHARGING',
    battery_pct: 42,
  },
}

function respondWith(events: unknown[]) {
  const fetchMock = vi.fn((_url: string) => Promise.resolve(jsonResponse(events)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('EventTimeline DRONE_RECOVERED (Feature 022)', () => {
  it('shows a drone recovery in the drone activity, newest first, without failing', async () => {
    respondWith([FAILURE, RECOVERED])

    render(<EventTimeline droneId="DRN-010" />)

    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Drone recovered and returned to a Hub')
    expect(items[0]).toHaveTextContent('Automatic')
    expect(items[0]).toHaveTextContent('Mission MIS-1')
    expect(items[0]).toHaveTextContent('Drone DRN-010')
    expect(items[0]).toHaveTextContent('moved to Centrum Riviera')
    expect(items[1]).toHaveTextContent('Drone failure') // the failure is still part of the history
  })

  it('shows it in the order activity too, after the failure, in the API order', async () => {
    respondWith([FAILURE, RECOVERED])

    render(<EventTimeline orderId="ORD-1" />)

    const items = await screen.findAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Drone failure'),
      expect.stringContaining('Drone recovered and returned to a Hub'),
    ])
  })

  it('still rejects an event type it does not know', async () => {
    respondWith([{ ...RECOVERED, event_type: 'DRONE_TELEPORTED' }])

    render(<EventTimeline droneId="DRN-010" />)

    expect(await screen.findByText('Activity unavailable')).toBeInTheDocument()
  })
})
