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
  purpose: 'DELIVERY',
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
  recalledAt: null,
  failedAt: null,
  recipientUnavailableAt: null,
  handoverFailedAt: null,
  yieldingToLpr: false,
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

  it('says that a recalled drone is returning with its parcel and where to', () => {
    const recalled: Flight = {
      ...FLIGHT,
      deliveredAt: null,
      recalledAt: '2026-11-12T10:00:08Z',
      landingTargetHubId: 'hub-forum-gdansk',
    }

    render(<FlightSection flight={recalled} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(within(section).getByText('Recalled')).toBeInTheDocument()
    expect(section).toHaveTextContent('Returning with the parcel to Forum Gdańsk')
    expect(within(section).queryByText('Now heading to')).not.toBeInTheDocument()
  })

  it('labels the phase of a recalled flight as a recall, not as an ordinary return', () => {
    const recalled: Flight = { ...FLIGHT, deliveredAt: null, recalledAt: '2026-11-12T10:00:08Z' }

    render(<FlightSection flight={recalled} hubs={HUBS} workerStale={false} />)

    expect(screen.getByText('Recalled: returning with the parcel')).toBeInTheDocument()
    expect(screen.queryByText('Returning to a Hub')).not.toBeInTheDocument()
  })

  it('keeps the ordinary phase text for a flight that was not recalled', () => {
    render(<FlightSection flight={FLIGHT} hubs={HUBS} workerStale={false} />)

    expect(screen.getByText('Returning to a Hub')).toBeInTheDocument()
  })

  it('shows the emergency approach of a failed drone with its landing point', () => {
    const approaching: Flight = {
      ...FLIGHT,
      phase: 'EMERGENCY_APPROACH',
      deliveredAt: null,
      failedAt: '2026-11-12T10:00:08Z',
      recalledAt: '2026-11-12T10:00:05Z', // failing while recalled: the failure wins
      target: { position: [18.6012, 54.3821], etaS: 6 },
    }

    render(<FlightSection flight={approaching} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Emergency landing: drone failure')
    expect(section).toHaveTextContent('Emergency landing point')
    expect(section).toHaveTextContent('54.38210, 18.60120')
    expect(section).toHaveTextContent('no longer follows its delivery or recall route')
    expect(within(section).queryByText('Recalled')).not.toBeInTheDocument()
    expect(within(section).queryByText('Planned return Hub')).not.toBeInTheDocument()
  })

  it('shows a grounded failed drone as requiring service', () => {
    const grounded: Flight = {
      ...FLIGHT,
      phase: 'EMERGENCY',
      target: null,
      failedAt: '2026-11-12T10:00:08Z',
      emergency: {
        reason: 'DRONE_FAILURE',
        at: '2026-11-12T10:00:15Z',
        position: [18.6012, 54.3821],
        acknowledgedAt: null,
      },
    }

    render(<FlightSection flight={grounded} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Grounded after drone failure: requires service')
    expect(section).toHaveTextContent('grounded, requiring service')
    expect(section).toHaveTextContent('Its mission does not resume')
  })

  it('says the recipient was reported unavailable while the attempt is still pending', () => {
    const pending: Flight = {
      ...FLIGHT,
      phase: 'OUTBOUND',
      deliveredAt: null,
      recipientUnavailableAt: '2026-11-12T10:00:05Z',
    }

    render(<FlightSection flight={pending} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Unavailable: the delivery fails on arrival')
    expect(section).toHaveTextContent('The drone still flies to the destination')
    expect(section).not.toHaveTextContent('Delivery failed')
  })

  it('shows the loaded return after a failed handover with its target Hub', () => {
    const returning: Flight = {
      ...FLIGHT,
      phase: 'RETURNING',
      deliveredAt: null,
      recipientUnavailableAt: '2026-11-12T10:00:05Z',
      handoverFailedAt: '2026-11-12T10:00:19Z',
    }

    render(<FlightSection flight={returning} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Delivery failed: returning with the parcel')
    expect(section).toHaveTextContent('With the parcel to')
    expect(section).toHaveTextContent('the parcel was not delivered')
    expect(within(section).queryByText('Planned return Hub')).not.toBeInTheDocument()
    expect(section).not.toHaveTextContent('fails on arrival') // no longer pending
  })

  it('says the drone is waiting for the LPR helicopter, apart from an emergency', () => {
    const waiting: Flight = { ...FLIGHT, phase: 'OUTBOUND', deliveredAt: null, yieldingToLpr: true }

    render(<FlightSection flight={waiting} hubs={HUBS} workerStale={false} />)

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Yielding to LPR helicopter')
    expect(section).toHaveTextContent('resumes its mission when the helicopter has passed')
    expect(section).not.toHaveTextContent('Emergency')
    expect(section).not.toHaveTextContent('maintenance')
  })

  it('shows the normal phase again once the drone resumes', () => {
    render(
      <FlightSection
        flight={{ ...FLIGHT, phase: 'OUTBOUND', deliveredAt: null, yieldingToLpr: false }}
        hubs={HUBS}
        workerStale={false}
      />,
    )

    const section = screen.getByRole('region', { name: 'Flight' })
    expect(section).toHaveTextContent('Outbound with the parcel')
    expect(section).not.toHaveTextContent('LPR')
  })

  it('does not call a failed drone yielding', () => {
    const failed: Flight = {
      ...FLIGHT,
      phase: 'EMERGENCY_APPROACH',
      deliveredAt: null,
      failedAt: '2026-11-12T10:00:08Z',
      yieldingToLpr: true,
    }

    render(<FlightSection flight={failed} hubs={HUBS} workerStale={false} />)

    expect(screen.getByRole('region', { name: 'Flight' })).not.toHaveTextContent('LPR')
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
        acknowledgedAt: null,
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

describe('FlightSection for a relocation (Feature 019A)', () => {
  const RELOCATION: Flight = {
    ...FLIGHT,
    orderId: null,
    purpose: 'RELOCATION',
    phase: 'RELOCATING',
    deliveredAt: null,
    plannedReturnHubId: 'hub-forum-gdansk',
    landingTargetHubId: 'hub-forum-gdansk',
  }

  it('names the destination Hub and says there is no order or parcel', () => {
    render(<FlightSection flight={RELOCATION} hubs={HUBS} workerStale={false} />)

    expect(valueOf('Phase')).toHaveTextContent('Relocating to Forum Gdańsk')
    expect(valueOf('Destination Hub')).toHaveTextContent('Forum Gdańsk')
    expect(screen.queryByText('Planned return Hub')).not.toBeInTheDocument()
    expect(screen.getByText(/no order, no parcel/)).toBeInTheDocument()
  })

  it('lets the LPR wait and a drone failure take over the label', () => {
    const { rerender } = render(
      <FlightSection
        flight={{ ...RELOCATION, yieldingToLpr: true }}
        hubs={HUBS}
        workerStale={false}
      />,
    )
    expect(valueOf('Phase')).toHaveTextContent('Yielding to LPR helicopter')

    rerender(
      <FlightSection
        flight={{ ...RELOCATION, failedAt: '2026-11-12T10:00:05Z', phase: 'EMERGENCY_APPROACH' }}
        hubs={HUBS}
        workerStale={false}
      />,
    )
    expect(valueOf('Phase')).toHaveTextContent('Emergency landing: drone failure')
  })
})
