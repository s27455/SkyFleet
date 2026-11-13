import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { HubDetailPanel } from './HubDetailPanel'

const HUB: Hub = {
  id: 'hub-test',
  name: 'Test Mall',
  address: 'Testowa 1, Gdynia',
  coordinates: [18.5, 54.5],
  droneCapacity: 50,
}

describe('HubDetailPanel', () => {
  it('shows hub identity, address and the maximum drone capacity', () => {
    render(<HubDetailPanel hub={HUB} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: 'Test Mall' })).toBeInTheDocument()
    expect(screen.getByText('Testowa 1, Gdynia')).toBeInTheDocument()
    expect(screen.getByText('Maximum drone capacity').nextElementSibling).toHaveTextContent('50')
  })

  it('shows no status, mock data notice or occupancy', () => {
    render(<HubDetailPanel hub={HUB} onClose={() => {}} />)

    expect(screen.queryByText('Status')).not.toBeInTheDocument()
    expect(screen.queryByText(/mock data/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/occupancy/i)).not.toBeInTheDocument()
    expect(screen.getByText(/not a real SkyFleet facility/)).toBeInTheDocument()
  })

  it('closes via the close button', () => {
    const onClose = vi.fn()
    render(<HubDetailPanel hub={HUB} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close hub details' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes on Escape', () => {
    const onClose = vi.fn()
    render(<HubDetailPanel hub={HUB} onClose={onClose} />)

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledOnce()
  })
})

const DOCKED = (id: string, status: Drone['status'] = 'IDLE'): Drone => ({
  id,
  hubId: 'hub-test',
  status,
  batteryPct: 90,
  coordinates: [18.5, 54.5],
  model: {
    id: 'SF-1',
    name: 'SkyFleet SF-1 Courier',
    maxPayloadKg: 3,
    maxRangeKm: 20,
    recommendedMissionRangeKm: 14,
    cruiseSpeedKmh: 45,
    nominalFlightTimeMin: 32,
    minBatteryReservePct: 20,
    airframeType: 'hexacopter',
    maxSpeedKmh: 60,
    chargeTo80Minutes: 45,
    maxWindMps: 10,
    emptyWeightKg: 9,
  },
})

describe('HubDetailPanel mission hint', () => {
  it('marks only the docked drones that have an assigned mission', () => {
    render(
      <HubDetailPanel
        hub={HUB}
        dockedDrones={[DOCKED('DRN-001'), DOCKED('DRN-002')]}
        assignedMissionDroneIds={new Set(['DRN-002'])}
        onClose={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: /DRN-001/ })).not.toHaveTextContent(
      'mission assigned',
    )
    expect(screen.getByRole('button', { name: /DRN-002/ })).toHaveTextContent('mission assigned')
  })

  it('shows no hint when no mission information is available', () => {
    render(<HubDetailPanel hub={HUB} dockedDrones={[DOCKED('DRN-001')]} onClose={() => {}} />)

    expect(screen.queryByText(/mission assigned/)).not.toBeInTheDocument()
  })
})
