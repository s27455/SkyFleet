import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { OrderDetailPanel } from './OrderDetailPanel'
import { formatUtcTimestamp } from './orderStatus'

const ORDER: Order = {
  id: 'ORD-004',
  originHubId: 'hub-forum-gdansk',
  destinationAddress: 'ul. Długa 45, Gdańsk',
  coordinates: [18.6531, 54.3487],
  packageWeightKg: 0.3,
  status: 'READY_FOR_PICKUP',
  deliveredAt: null,
  createdAt: '2026-11-11T21:53:08.077240Z',
  updatedAt: '2026-11-12T08:05:00Z',
}

const HUB: Hub = {
  id: 'hub-forum-gdansk',
  name: 'Forum Gdańsk',
  address: 'Targ Sienny 7, Gdańsk',
  coordinates: [18.643527, 54.349346],
  droneCapacity: 50,
}

const valueOf = (label: string) => screen.getByText(label).nextElementSibling

describe('OrderDetailPanel', () => {
  it('shows identity, status, weight, origin Hub name and destination', () => {
    render(<OrderDetailPanel order={ORDER} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: 'ORD-004' })).toBeInTheDocument()
    expect(valueOf('Status')).toHaveTextContent('Ready for pickup')
    expect(valueOf('Package weight')).toHaveTextContent('0.3 kg')
    expect(valueOf('Origin Hub')).toHaveTextContent('Forum Gdańsk')
    expect(valueOf('Destination')).toHaveTextContent('ul. Długa 45, Gdańsk')
    expect(valueOf('Destination position')).toHaveTextContent('54.348700, 18.653100')
  })

  it('falls back to the Hub id when the Hub is not available', () => {
    render(<OrderDetailPanel order={ORDER} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Origin Hub')).toHaveTextContent('hub-forum-gdansk')
  })

  it('shows both timestamps in UTC, independent of the local time zone', () => {
    render(<OrderDetailPanel order={ORDER} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Created')).toHaveTextContent('11 Nov 2026, 21:53 UTC')
    expect(valueOf('Updated')).toHaveTextContent('12 Nov 2026, 08:05 UTC')
    expect(formatUtcTimestamp('2026-01-01T00:00:00Z')).toBe('1 Jan 2026, 00:00 UTC')
  })

  it('labels the data as simulation and never mentions a drone assignment', () => {
    render(<OrderDetailPanel order={ORDER} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(screen.getByText(/Simulation data/)).toBeInTheDocument()
    expect(screen.queryByText(/assigned/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/spread slightly/)).not.toBeInTheDocument()
  })

  it('explains the display spread when the marker was moved on screen', () => {
    render(<OrderDetailPanel order={ORDER} hub={HUB} markerSpread onClose={() => {}} />)

    expect(screen.getByText(/spread slightly on screen/)).toBeInTheDocument()
  })

  it('closes via the close button and on Escape', () => {
    const onClose = vi.fn()
    render(<OrderDetailPanel order={ORDER} hub={HUB} markerSpread={false} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close order details' }))
    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
