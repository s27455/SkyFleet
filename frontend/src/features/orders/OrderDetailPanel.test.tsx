import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Flight } from '../../types/flight'
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
  cancelledAt: null,
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

  it('shows the cancelled status and time of a cancelled order', () => {
    const cancelled: Order = {
      ...ORDER,
      status: 'CANCELLED',
      cancelledAt: '2026-11-13T12:00:00Z',
    }

    render(<OrderDetailPanel order={cancelled} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Status')).toHaveTextContent('Cancelled')
    expect(screen.getByText('Cancelled', { selector: 'dt' }).nextElementSibling).toHaveTextContent(
      formatUtcTimestamp('2026-11-13T12:00:00Z'),
    )
  })

  it('offers a Cancel order action for an eligible order when it can be used', () => {
    const { rerender } = render(
      <OrderDetailPanel
        order={ORDER}
        hub={HUB}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: 'Cancel order' })).toBeInTheDocument()

    rerender(
      <OrderDetailPanel
        order={{ ...ORDER, status: 'DELIVERED' }}
        hub={HUB}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
  })

  it('says that a cancelled order has no active flight when none is reported', () => {
    const cancelled: Order = {
      ...ORDER,
      status: 'CANCELLED',
      cancelledAt: '2026-11-13T12:00:00Z',
    }

    render(
      <OrderDetailPanel
        order={cancelled}
        hub={HUB}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )

    const notice = screen.getByText(/This order was cancelled at/)
    expect(notice).toHaveTextContent('No flight is active for it')
    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
  })

  it('shows the recalled flight, its phase and target Hub, for a cancelled order', () => {
    const cancelled: Order = {
      ...ORDER,
      status: 'CANCELLED',
      cancelledAt: '2026-11-13T12:00:00Z',
    }
    const flight: Flight = {
      missionId: 'MIS-AAAA0001',
      orderId: 'ORD-004',
      droneId: 'DRN-010',
      missionStatus: 'IN_FLIGHT',
      phase: 'RETURNING',
      progress: 0.3,
      position: [18.6, 54.37],
      batteryPct: 96,
      target: { position: [18.643527, 54.349346], etaS: 9 },
      originHubId: 'hub-forum-gdansk',
      plannedReturnHubId: 'hub-forum-gdansk',
      landingTargetHubId: 'hub-forum-gdansk',
      startedAt: '2026-11-13T11:59:50Z',
      deliveredAt: null,
      recalledAt: '2026-11-13T12:00:00Z',
      failedAt: null,
      updatedAt: '2026-11-13T12:00:02Z',
      snapshotAgeS: 1,
      emergency: null,
    }

    render(
      <OrderDetailPanel
        order={cancelled}
        hub={HUB}
        hubs={[HUB]}
        flight={flight}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )

    expect(
      screen.getByText(/The drone was recalled and is returning with the parcel/),
    ).toBeVisible()
    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Recalled: returning with the parcel')
    expect(section).toHaveTextContent('Returning with the parcel to Forum Gdańsk')
    expect(section).toHaveTextContent('MIS-AAAA0001')
  })

  it('says the delivery was interrupted by a drone failure and offers no cancellation', () => {
    const interrupted: Order = { ...ORDER, status: 'OUT_FOR_DELIVERY' }
    const flight: Flight = {
      missionId: 'MIS-AAAA0001',
      orderId: 'ORD-004',
      droneId: 'DRN-010',
      missionStatus: 'EMERGENCY',
      phase: 'EMERGENCY',
      progress: 1,
      position: [18.6, 54.37],
      batteryPct: 90,
      target: null,
      originHubId: 'hub-forum-gdansk',
      plannedReturnHubId: 'hub-forum-gdansk',
      landingTargetHubId: 'hub-forum-gdansk',
      startedAt: '2026-11-13T11:59:50Z',
      deliveredAt: null,
      recalledAt: null,
      failedAt: '2026-11-13T12:00:00Z',
      updatedAt: '2026-11-13T12:00:10Z',
      snapshotAgeS: 1,
      emergency: { reason: 'DRONE_FAILURE', at: '2026-11-13T12:00:09Z', position: [18.6, 54.37] },
    }

    render(
      <OrderDetailPanel
        order={interrupted}
        hub={HUB}
        hubs={[HUB]}
        flight={flight}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )

    expect(screen.getByText(/Delivery interrupted by drone failure/)).toHaveTextContent(
      'DRN-010 is grounded, requiring service; the parcel was not delivered',
    )
    expect(screen.getByText(/Cancelling is not available for this order/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Flight' })).toHaveTextContent('requires service')
  })

  it('still offers Cancel order for an order whose drone has not failed', () => {
    render(
      <OrderDetailPanel
        order={{ ...ORDER, status: 'OUT_FOR_DELIVERY' }}
        hub={HUB}
        markerSpread={false}
        onClose={() => {}}
        onCancelled={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: 'Cancel order' })).toBeInTheDocument()
    expect(screen.queryByText(/Delivery interrupted/)).not.toBeInTheDocument()
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
