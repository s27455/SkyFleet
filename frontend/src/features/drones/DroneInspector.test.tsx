import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { DroneInspector } from './DroneInspector'
import type { InspectorData } from './inspectorData'

// jsdom has no WebGL: the viewer itself is covered by its own tests.
vi.mock('../drone3d', () => ({ Drone3DViewer: () => <div data-testid="viewer" /> }))

const DRONE: Drone = {
  id: 'DRN-004',
  hubId: 'hub-riviera',
  status: 'IN_FLIGHT',
  batteryPct: 72,
  coordinates: [18.5317863, 54.5046621],
  model: {
    id: 'SF-1',
    name: 'SkyFleet SF-1 Courier',
    airframeType: 'quadcopter',
    maxPayloadKg: 3,
    maxRangeKm: 20,
    recommendedMissionRangeKm: 14,
    cruiseSpeedKmh: 45,
    maxSpeedKmh: 60,
    nominalFlightTimeMin: 32,
    minBatteryReservePct: 20,
    chargeTo80Minutes: 45,
    maxWindMps: 10,
    emptyWeightKg: 9,
  },
}

const HUBS: Hub[] = [
  {
    id: 'hub-riviera',
    name: 'Centrum Riviera',
    address: 'Gdynia',
    coordinates: [18.53, 54.5],
    droneCapacity: 50,
  },
]

const FLIGHT: Flight = {
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  droneId: 'DRN-004',
  missionStatus: 'IN_FLIGHT',
  phase: 'DELIVERING',
  progress: 0.4,
  position: [18.5, 54.4],
  batteryPct: 71,
  target: null,
  originHubId: 'hub-riviera',
  plannedReturnHubId: 'hub-riviera',
  landingTargetHubId: 'hub-riviera',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: null,
  updatedAt: '2026-11-12T10:00:01Z',
  snapshotAgeS: 1,
  emergency: null,
}

const ORDER: Order = {
  id: 'ORD-1',
  originHubId: 'hub-riviera',
  destinationAddress: 'Długa 1, Gdańsk',
  coordinates: [18.65, 54.35],
  packageWeightKg: 1.8,
  status: 'OUT_FOR_DELIVERY',
  createdAt: '2026-11-12T09:00:00Z',
  updatedAt: '2026-11-12T10:00:00Z',
}

const FLYING: InspectorData = {
  flight: { kind: 'found', value: FLIGHT },
  mission: {
    kind: 'found',
    value: { id: 'MIS-1', status: 'IN_FLIGHT', returnHubId: 'hub-riviera', totalKm: 3.2 },
  },
  payload: { kind: 'found', value: ORDER },
}

const IDLE: InspectorData = {
  flight: { kind: 'none' },
  mission: { kind: 'none' },
  payload: { kind: 'none' },
}

function renderInspector(overrides: Partial<Parameters<typeof DroneInspector>[0]> = {}) {
  const onClose = vi.fn()
  const view = render(
    <DroneInspector
      drone={DRONE}
      hub={HUBS[0]}
      hubs={HUBS}
      data={FLYING}
      workerStale={false}
      dataStale={false}
      onClose={onClose}
      {...overrides}
    />,
  )
  return { onClose, ...view }
}

const section = (name: string) => screen.getByRole('region', { name })

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('reduce'),
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

describe('DroneInspector', () => {
  beforeEach(() => stubReducedMotion(true))
  afterEach(() => vi.useRealTimers())

  it('is a labelled modal dialog with the 3D viewer', () => {
    renderInspector()

    const dialog = screen.getByRole('dialog', { name: 'DRN-004' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(within(dialog).getByTestId('viewer')).toBeInTheDocument()
    expect(within(dialog).getByText('SkyFleet SF-1 Courier')).toBeInTheDocument()
    expect(within(dialog).getByText(/Illustrative model/)).toBeInTheDocument()
  })

  it('shows the real operational data of a flying drone', () => {
    renderInspector()

    const operational = section('Operational')
    expect(within(operational).getByRole('progressbar', { name: 'Battery' })).toHaveAttribute(
      'aria-valuenow',
      '72',
    )
    expect(within(operational).getByText('72%')).toBeInTheDocument()
    expect(within(operational).getByText('Centrum Riviera')).toBeInTheDocument()
    expect(within(operational).getByText('54.504662, 18.531786')).toBeInTheDocument()

    expect(within(section('Flight')).getByText('Delivering the parcel')).toBeInTheDocument()
    const mission = section('Mission')
    expect(within(mission).getByText('MIS-1')).toBeInTheDocument()
    expect(within(mission).getByText('3.2 km')).toBeInTheDocument()
    const payload = section('Payload')
    expect(within(payload).getByText('1.8 kg')).toBeInTheDocument()
    expect(within(payload).getByText('Długa 1, Gdańsk')).toBeInTheDocument()
  })

  it('shows the model specification including the additional API fields', () => {
    renderInspector()

    const specification = section('Model specification')
    expect(within(specification).getByText('quadcopter')).toBeInTheDocument()
    expect(within(specification).getByText('9 kg')).toBeInTheDocument()
    expect(within(specification).getByText('45 / 60 km/h')).toBeInTheDocument()
    expect(within(specification).getByText('45 min')).toBeInTheDocument()
    expect(within(specification).getByText('10 m/s')).toBeInTheDocument()
  })

  it('says plainly when an idle drone has no flight, mission or parcel', () => {
    renderInspector({ data: IDLE })

    expect(within(section('Flight')).getByText('No active flight.')).toBeInTheDocument()
    expect(within(section('Mission')).getByText('No active mission.')).toBeInTheDocument()
    expect(within(section('Payload')).getByText('No parcel assigned.')).toBeInTheDocument()
  })

  it('shows unreadable data as unavailable, never as "none"', () => {
    renderInspector({
      data: {
        flight: { kind: 'unavailable', reason: 'loading' },
        mission: { kind: 'unavailable', reason: 'error' },
        payload: { kind: 'unavailable', reason: 'missing' },
      },
    })

    expect(within(section('Flight')).getByText('Loading…')).toBeInTheDocument()
    expect(within(section('Mission')).getByText(/could not be read/)).toBeInTheDocument()
    expect(
      within(section('Payload')).getByText(/not found in the current data/),
    ).toBeInTheDocument()
    expect(screen.queryByText('No active mission.')).not.toBeInTheDocument()
  })

  it('shows "—" for mission details a flight alone cannot provide', () => {
    renderInspector({
      data: { ...FLYING, mission: { kind: 'found', value: { id: 'MIS-1', status: 'IN_FLIGHT' } } },
    })

    expect(within(section('Mission')).getAllByText('—')).toHaveLength(2)
  })

  it('warns when the latest refresh failed and keeps the last known data', () => {
    renderInspector({ dataStale: true })

    expect(screen.getByRole('status')).toHaveTextContent(/last known and may be outdated/)
    expect(within(section('Operational')).getByText('72%')).toBeInTheDocument()
  })

  it('shows labelled simulated telemetry estimated from the real flight and parcel', () => {
    renderInspector()

    const telemetry = section('Simulated telemetry')
    expect(within(telemetry).getByText('Simulated')).toBeInTheDocument()
    // The flight phase (DELIVERING) and the 1.8 kg parcel are inputs of the estimate.
    expect(within(telemetry).getByText('Flying, parcel on board')).toBeInTheDocument()
    // The drone model is a quadcopter: a header row plus four motors.
    expect(within(telemetry).getAllByRole('row')).toHaveLength(5)
    // The real data sections stay separate and unlabelled by "simulated".
    expect(within(section('Operational')).queryByText('Simulated')).not.toBeInTheDocument()
  })

  it('shows telemetry for an idle drone as standby', () => {
    renderInspector({ drone: { ...DRONE, status: 'IDLE' }, data: IDLE })

    expect(
      within(section('Simulated telemetry')).getByText('Standby, motors off'),
    ).toBeInTheDocument()
  })

  it('moves focus to the close button and closes with it', () => {
    const { onClose } = renderInspector()

    const close = screen.getByRole('button', { name: 'Close inspector' })
    expect(close).toHaveFocus()
    fireEvent.click(close)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape', () => {
    const { onClose } = renderInspector()

    fireEvent.keyDown(document.body, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('plays the exit animation before closing when motion is allowed', () => {
    stubReducedMotion(false)
    vi.useFakeTimers()
    const { onClose } = renderInspector()

    fireEvent.keyDown(document.body, { key: 'Escape' })
    fireEvent.keyDown(document.body, { key: 'Escape' }) // a second request changes nothing
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toHaveClass('inspector-exit')

    vi.advanceTimersByTime(200)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('keeps Tab inside the dialog', () => {
    renderInspector()
    const dialog = screen.getByRole('dialog')
    const focusable = [...dialog.querySelectorAll<HTMLElement>('button, [tabindex="0"]')]
    const last = focusable[focusable.length - 1]

    last.focus()
    fireEvent.keyDown(document.body, { key: 'Tab' })
    expect(screen.getByRole('button', { name: 'Close inspector' })).toHaveFocus()

    fireEvent.keyDown(document.body, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
  })

  it('returns focus to the element that opened it', () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()

    const { unmount } = renderInspector()
    expect(opener).not.toHaveFocus()
    unmount()

    expect(opener).toHaveFocus()
    opener.remove()
  })
})
