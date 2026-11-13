import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { DroneDetailPanel } from './DroneDetailPanel'

const DRONE: Drone = {
  id: 'DRN-004',
  hubId: 'hub-centrum-riviera',
  status: 'IDLE',
  batteryPct: 90,
  coordinates: [18.5317863, 54.5046621],
  model: {
    id: 'SF-1',
    name: 'SkyFleet SF-1 Courier',
    maxPayloadKg: 3,
    maxRangeKm: 20,
    recommendedMissionRangeKm: 14,
    cruiseSpeedKmh: 45,
    nominalFlightTimeMin: 32,
    minBatteryReservePct: 20,
    airframeType: 'quadcopter',
    maxSpeedKmh: 60,
    chargeTo80Minutes: 45,
    maxWindMps: 10,
    emptyWeightKg: 9,
  },
}

const HUB: Hub = {
  id: 'hub-centrum-riviera',
  name: 'Centrum Riviera',
  address: 'Kazimierza Górskiego 2, Gdynia',
  coordinates: [18.5317863, 54.5046621],
  droneCapacity: 50,
}

const valueOf = (label: string) => screen.getByText(label).nextElementSibling

describe('DroneDetailPanel', () => {
  it('shows identity, status, battery and the assigned Hub name', () => {
    render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: 'DRN-004' })).toBeInTheDocument()
    expect(screen.getByText('SkyFleet SF-1 Courier')).toBeInTheDocument()
    expect(valueOf('Status')).toHaveTextContent('Idle')
    expect(valueOf('Battery')).toHaveTextContent('90%')
    expect(valueOf('Current Hub')).toHaveTextContent('Centrum Riviera')
  })

  it('falls back to the Hub id when the Hub is not available', () => {
    render(<DroneDetailPanel drone={DRONE} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Current Hub')).toHaveTextContent('hub-centrum-riviera')
  })

  it('shows the model capabilities including the 3 kg payload', () => {
    render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Maximum payload')).toHaveTextContent('3 kg')
    expect(valueOf('Maximum total flight distance')).toHaveTextContent('20 km')
    expect(valueOf('Conservative mission distance')).toHaveTextContent('14 km')
    expect(valueOf('Cruise speed')).toHaveTextContent('45 km/h')
    expect(valueOf('Nominal flight time')).toHaveTextContent('32 min')
    expect(valueOf('Minimum battery reserve')).toHaveTextContent('20%')
  })

  it('shows the real stored position and labels the data as a snapshot', () => {
    render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread={false} onClose={() => {}} />)

    expect(valueOf('Stored position')).toHaveTextContent('54.504662, 18.531786')
    expect(
      screen.getByText(/refreshed about every 2 seconds; flights are simulated/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/spread slightly/)).not.toBeInTheDocument()
  })

  it('explains the display spread when the marker was moved on screen', () => {
    render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread onClose={() => {}} />)

    expect(screen.getByText(/spread slightly on screen/)).toBeInTheDocument()
  })

  it('closes via the close button and on Escape', () => {
    const onClose = vi.fn()
    render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread={false} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close drone details' }))
    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(2)
  })

  describe('inspector entry point', () => {
    it('shows no Inspect Drone button unless the inspector can be opened', () => {
      render(<DroneDetailPanel drone={DRONE} hub={HUB} markerSpread={false} onClose={() => {}} />)

      expect(screen.queryByRole('button', { name: 'Inspect Drone' })).not.toBeInTheDocument()
    })

    it('opens the inspector from the Inspect Drone button below the primary information', () => {
      const onInspect = vi.fn()
      render(
        <DroneDetailPanel
          drone={DRONE}
          hub={HUB}
          markerSpread={false}
          onClose={() => {}}
          onInspect={onInspect}
        />,
      )

      const button = screen.getByRole('button', { name: 'Inspect Drone' })
      expect(valueOf('Stored position')?.closest('dl')?.nextElementSibling).toBe(button)
      fireEvent.click(button)

      expect(onInspect).toHaveBeenCalledTimes(1)
    })

    it('stops closing on Escape while the inspector is open on top', () => {
      const onClose = vi.fn()
      const { rerender } = render(
        <DroneDetailPanel drone={DRONE} markerSpread={false} onClose={onClose} />,
      )
      fireEvent.keyDown(window, { key: 'Escape' })
      expect(onClose).toHaveBeenCalledTimes(1)

      rerender(
        <DroneDetailPanel
          drone={DRONE}
          markerSpread={false}
          onClose={onClose}
          closeOnEscape={false}
        />,
      )
      fireEvent.keyDown(window, { key: 'Escape' })
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })
})
