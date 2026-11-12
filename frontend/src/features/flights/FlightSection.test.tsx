import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import { FlightSection } from './FlightSection'

const HUBS: Hub[] = [
  {
    id: 'hub-galeria-baltycka',
    name: 'Galeria Bałtycka',
    address: 'a',
    coordinates: [18.6, 54.38],
    droneCapacity: 50,
  },
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    address: 'b',
    coordinates: [18.64, 54.35],
    droneCapacity: 50,
  },
]

const FLIGHT: Flight = {
  missionId: 'MIS-AAAA0001',
  orderId: 'ORD-001',
  droneId: 'DRN-010',
  missionStatus: 'IN_FLIGHT',
  phase: 'RETURNING',
  progress: 0.6,
  position: [18.599, 54.38],
  batteryPct: 94,
  target: { position: [18.6, 54.38], etaS: 12 },
  originHubId: 'hub-galeria-baltycka',
  plannedReturnHubId: 'hub-galeria-baltycka',
  landingTargetHubId: 'hub-galeria-baltycka',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: '2026-11-12T10:00:19Z',
  updatedAt: '2026-11-12T10:00:25Z',
  snapshotAgeS: 2,
  emergency: null,
}

const valueOf = (label: string) => screen.getByText(label).nextElementSibling

describe('FlightSection', () => {
  it('shows phase, mission, progress, battery and the planned return Hub', () => {
    render(<FlightSection flight={FLIGHT} hubs={HUBS} workerStale={false} />)

    expect(valueOf('Phase')).toHaveTextContent('Returning to a Hub')
    expect(valueOf('Mission')).toHaveTextContent('MIS-AAAA0001 (IN_FLIGHT)')
    expect(screen.getByRole('progressbar', { name: 'Flight progress' })).toHaveAttribute(
      'aria-valuenow',
      '60',
    )
    expect(screen.getByRole('progressbar', { name: 'Flight battery' })).toHaveAttribute(
      'aria-valuenow',
      '94',
    )
    expect(valueOf('Flight battery')).toHaveTextContent('94%')
    expect(valueOf('Planned return Hub')).toHaveTextContent('Galeria Bałtycka')
    expect(screen.queryByText('Now heading to')).not.toBeInTheDocument()
  })

  it('counts the time to the next point from the snapshot age', () => {
    render(<FlightSection flight={FLIGHT} hubs={HUBS} workerStale={false} />)

    expect(valueOf('Next point in')).toHaveTextContent('about 10 s') // 12 s eta, 2 s already gone
  })

  it('says where a diverted drone is heading now, and falls back to the Hub id', () => {
    const diverted: Flight = {
      ...FLIGHT,
      phase: 'DIVERTING',
      landingTargetHubId: 'hub-forum-gdansk',
    }
    render(<FlightSection flight={diverted} hubs={HUBS} workerStale={false} />)

    expect(valueOf('Phase')).toHaveTextContent('Diverting to another Hub')
    expect(valueOf('Now heading to')).toHaveTextContent('Forum Gdańsk')

    render(<FlightSection flight={diverted} hubs={[]} workerStale={false} />)
    expect(screen.getAllByText('hub-forum-gdansk').length).toBeGreaterThan(0)
  })

  it('warns when the worker stopped updating the flight', () => {
    render(<FlightSection flight={FLIGHT} hubs={HUBS} workerStale />)

    expect(screen.getByRole('status')).toHaveTextContent(/stopped updating this flight/)
  })

  it('shows a simulated emergency, labelled as not a real landing site', () => {
    const emergency: Flight = {
      ...FLIGHT,
      phase: 'EMERGENCY',
      target: null,
      emergency: {
        reason: 'BATTERY_INSUFFICIENT',
        at: '2026-11-12T10:00:30Z',
        position: [18.6012, 54.3821],
      },
    }
    render(<FlightSection flight={emergency} hubs={HUBS} workerStale={false} />)

    // Plain text in the panel: the persistent banner is the alert, so it is not announced twice.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const alert = screen.getByText(/Simulated emergency:/)
    expect(alert).toHaveTextContent('no other Hub was within reach of its battery')
    expect(alert).toHaveTextContent('54.38210, 18.60120')
    expect(alert).toHaveTextContent('not a computed safe landing site')
    expect(valueOf('Phase')).toHaveTextContent('Emergency')
    expect(screen.queryByText('Next point in')).not.toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'Flight' })).getByText('Emergency'),
    ).toBeInTheDocument()
  })
})
