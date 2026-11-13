import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { EventTimeline } from './EventTimeline'

const EVENT = {
  id: 7,
  event_type: 'ORDER_CREATED',
  occurred_at: '2026-11-13T10:00:00+00:00',
  origin: 'MANUAL',
  order_id: 'ORD-1',
  mission_id: null,
  flight_id: null,
  drone_id: null,
  reason: 'Order created as READY_FOR_PICKUP',
  details: null,
}

afterEach(() => vi.unstubAllGlobals())

describe('EventTimeline', () => {
  it('shows real events in the order the API returned them, with time and origin', async () => {
    const fetchMock = vi.fn((_url: string) =>
      Promise.resolve(
        jsonResponse([
          { ...EVENT, id: 1 },
          { ...EVENT, id: 2, origin: 'AUTOMATIC' },
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<EventTimeline orderId="ORD-1" />)

    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Order created')
    expect(items[0]).toHaveTextContent('Manual')
    expect(items[0]).toHaveTextContent('13 Nov')
    expect(items[1]).toHaveTextContent('Automatic')
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/events?order_id=ORD-1')
  })

  it('shows an honest empty state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse([]))),
    )

    render(<EventTimeline orderId="ORD-1" />)

    expect(await screen.findByText('No recorded activity for this order.')).toBeInTheDocument()
  })

  it('shows a loading state first', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    )

    render(<EventTimeline orderId="ORD-1" />)

    expect(screen.getByText('Loading activity…')).toBeInTheDocument()
  })

  it('shows an error with Retry and recovers', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(jsonResponse([EVENT]))
    vi.stubGlobal('fetch', fetchMock)

    render(<EventTimeline orderId="ORD-1" />)
    const retry = await screen.findByRole('button', { name: 'Retry activity' })
    retry.click()

    await waitFor(() => expect(screen.getByRole('listitem')).toHaveTextContent('Order created'))
  })

  it('rejects a timestamp without a zone instead of showing it as UTC', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse([{ ...EVENT, occurred_at: '2026-11-13T10:00:00' }])),
      ),
    )

    render(<EventTimeline orderId="ORD-1" />)

    expect(await screen.findByText(/Activity unavailable/)).toBeInTheDocument()
  })
})
