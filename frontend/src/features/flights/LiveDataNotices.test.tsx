import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Flight, FlightsSnapshot } from '../../types/flight'
import type { Mission } from '../../types/mission'
import type { PolledResource } from '../data/usePolledResource'
import { LiveDataNotices, MAX_EMERGENCY_ALERTS } from './LiveDataNotices'

const baseFlight: Flight = {
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  purpose: 'DELIVERY',
  droneId: 'DRN-1',
  missionStatus: 'EMERGENCY',
  phase: 'EMERGENCY',
  progress: 1,
  position: [18.6012, 54.3821],
  batteryPct: 12,
  target: null,
  originHubId: 'hub-a',
  plannedReturnHubId: 'hub-a',
  landingTargetHubId: 'hub-a',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: '2026-11-12T10:00:03Z',
  recalledAt: null,
  failedAt: null,
  recipientUnavailableAt: null,
  handoverFailedAt: null,
  yieldingToLpr: false,
  updatedAt: '2026-11-12T10:00:09Z',
  snapshotAgeS: 0,
  emergency: {
    reason: 'NO_HUB_WITH_CAPACITY',
    at: '2026-11-12T10:00:09Z',
    position: [18.6012, 54.3821],
  },
}

const emergency = (n: number): Flight => ({
  ...baseFlight,
  missionId: `MIS-${n}`,
  droneId: `DRN-${n}`,
})

function flightsResource(
  flights: Flight[],
  extra: Partial<PolledResource<FlightsSnapshot>> = {},
): PolledResource<FlightsSnapshot> {
  const snapshot: FlightsSnapshot = {
    serverTime: '2026-11-12T10:00:10Z',
    workerHeartbeatAt: '2026-11-12T10:00:09Z',
    workerStale: false,
    flights,
  }
  return {
    state: { status: 'ready', data: snapshot },
    stale: false,
    receivedAt: 0,
    retry: vi.fn(),
    refresh: vi.fn(),
    ...extra,
  }
}

const missionsResource: PolledResource<Mission[]> = {
  state: { status: 'ready', data: [] },
  stale: false,
  receivedAt: null,
  retry: vi.fn(),
  refresh: vi.fn(),
}

describe('LiveDataNotices emergencies', () => {
  it('lists a few emergencies in full and summarises the rest', () => {
    const many = Array.from({ length: MAX_EMERGENCY_ALERTS + 2 }, (_, i) => emergency(i + 1))

    render(<LiveDataNotices flights={flightsResource(many)} missions={missionsResource} />)

    const alerts = screen.getAllByRole('alert')
    expect(alerts).toHaveLength(MAX_EMERGENCY_ALERTS + 1) // the full cards plus one summary
    expect(alerts[0]).toHaveTextContent('Simulated emergency: DRN-1 (MIS-1)')
    expect(alerts[MAX_EMERGENCY_ALERTS - 1]).toHaveTextContent(`DRN-${MAX_EMERGENCY_ALERTS}`)
    expect(alerts[MAX_EMERGENCY_ALERTS]).toHaveTextContent('2 more simulated emergencies')
    expect(screen.queryByText(/DRN-5/)).not.toBeInTheDocument()
  })

  it('shows every emergency in full while there are few of them', () => {
    render(
      <LiveDataNotices
        flights={flightsResource([emergency(1), emergency(2)])}
        missions={missionsResource}
      />,
    )

    expect(screen.getAllByRole('alert')).toHaveLength(2)
    expect(screen.queryByText(/more simulated emergencies/)).not.toBeInTheDocument()
  })
})

describe('LiveDataNotices other notices', () => {
  it('shows nothing while all is well', () => {
    const { container } = render(
      <LiveDataNotices flights={flightsResource([])} missions={missionsResource} />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('offers Retry when flights could not be read at all, and Refresh when only a refresh failed', () => {
    const retry = vi.fn()
    const refresh = vi.fn()
    const { rerender } = render(
      <LiveDataNotices
        flights={flightsResource([], { state: { status: 'error' }, retry })}
        missions={missionsResource}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading flights' }))
    expect(retry).toHaveBeenCalledOnce()

    rerender(
      <LiveDataNotices
        flights={flightsResource([], { stale: true, refresh })}
        missions={missionsResource}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Refresh flights' }))
    expect(refresh).toHaveBeenCalledOnce()
    expect(screen.getByRole('status')).toHaveTextContent(/last known positions/)
  })

  it('offers a refresh of the fleet data when drones or orders could not be refreshed', () => {
    const onRefreshFleet = vi.fn()

    render(
      <LiveDataNotices
        flights={flightsResource([])}
        missions={missionsResource}
        fleetStale
        onRefreshFleet={onRefreshFleet}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Refresh fleet data' }))

    expect(onRefreshFleet).toHaveBeenCalledOnce()
  })
})
