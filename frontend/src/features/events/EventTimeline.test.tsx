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

describe('EventTimeline refresh key', () => {
  it('reads the events again when the key changes, without waiting for the next poll', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValue(jsonResponse([{ ...EVENT, id: 9, event_type: 'ORDER_CANCELLED' }]))
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(<EventTimeline orderId="ORD-1" refreshKey={0} />)
    expect(await screen.findByText('No recorded activity for this order.')).toBeInTheDocument()

    rerender(<EventTimeline orderId="ORD-1" refreshKey={1} />)

    expect(await screen.findByText('Order cancelled')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('EventTimeline for a drone (Feature 019A)', () => {
  it('reads the events of the drone and describes a relocation without an order', async () => {
    const fetchMock = vi.fn((_url: string) =>
      Promise.resolve(
        jsonResponse([
          {
            ...EVENT,
            id: 11,
            event_type: 'DRONE_RELOCATION',
            order_id: null,
            mission_id: 'MIS-RELOC001',
            drone_id: 'DRN-010',
            reason: 'Drone DRN-010 relocates from Galeria Bałtycka to Forum Gdańsk',
            details: { phase: 'STARTED' },
          },
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<EventTimeline droneId="DRN-010" />)

    const item = await screen.findByRole('listitem')
    expect(item).toHaveTextContent('Drone relocation')
    expect(item).toHaveTextContent('Drone DRN-010 relocates from Galeria Bałtycka to Forum Gdańsk')
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/events?drone_id=DRN-010')
  })

  it('has an honest empty state for a drone', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse([]))),
    )

    render(<EventTimeline droneId="DRN-010" />)

    expect(await screen.findByText('No recorded activity for this drone.')).toBeInTheDocument()
  })
})

describe('EventTimeline for a drone shows only the latest three', () => {
  const drone = (id: number, occurredAt: string) => ({
    ...EVENT,
    id,
    event_type: 'DRONE_RELOCATION',
    order_id: null,
    drone_id: 'DRN-010',
    occurred_at: occurredAt,
    reason: `record ${id}`,
  })

  async function show(events: ReturnType<typeof drone>[]) {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(events))),
    )
    render(<EventTimeline droneId="DRN-010" />)
  }

  it('shows one and three records as they are', async () => {
    await show([drone(1, '2026-11-13T10:00:00Z')])
    expect(await screen.findAllByRole('listitem')).toHaveLength(1)
  })

  it('shows three records newest first', async () => {
    await show([
      drone(1, '2026-11-13T10:00:00Z'),
      drone(2, '2026-11-13T10:01:00Z'),
      drone(3, '2026-11-13T10:02:00Z'),
    ])
    const items = await screen.findAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('record 3'),
      expect.stringContaining('record 2'),
      expect.stringContaining('record 1'),
    ])
  })

  it('drops older records beyond three and adds no "showing N" message', async () => {
    await show([
      drone(1, '2026-11-13T10:00:00Z'),
      drone(2, '2026-11-13T10:01:00Z'),
      drone(3, '2026-11-13T10:02:00Z'),
      drone(4, '2026-11-13T10:03:00Z'),
      drone(5, '2026-11-13T10:04:00Z'),
    ])
    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('record 5')
    expect(items[2]).toHaveTextContent('record 3')
    expect(screen.queryByText(/record 1/)).not.toBeInTheDocument()
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument()
  })

  it('puts the later id first when two records share a timestamp', async () => {
    await show([
      drone(7, '2026-11-13T10:00:00Z'),
      drone(8, '2026-11-13T10:00:00Z'),
      drone(6, '2026-11-13T09:00:00Z'),
      drone(5, '2026-11-13T08:00:00Z'),
    ])
    const items = await screen.findAllByRole('listitem')
    expect(items[0]).toHaveTextContent('record 8')
    expect(items[1]).toHaveTextContent('record 7')
    expect(items[2]).toHaveTextContent('record 6')
  })

  it('keeps an order timeline in full and oldest first', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse([1, 2, 3, 4].map((id) => ({ ...EVENT, id, reason: `record ${id}` }))),
        ),
      ),
    )
    render(<EventTimeline orderId="ORD-1" />)
    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('record 1')
  })
})
