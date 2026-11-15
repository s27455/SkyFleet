import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import { DronesList } from './DronesList'
import { EventsTab } from './EventsTab'
import { HubsList } from './HubsList'
import { buildNotices } from './notices'
import { OperationsPanel } from './OperationsPanel'
import type { OperationsTab } from './tabs'

afterEach(() => vi.unstubAllGlobals())

const HUB: Hub = {
  id: 'hub-a',
  name: 'Galeria Bałtycka',
  address: 'ul. Grunwaldzka 141',
  coordinates: [18.6, 54.38],
  droneCapacity: 6,
}
const DRONE = {
  id: 'DRN-001',
  hubId: 'hub-a',
  status: 'IDLE',
  batteryPct: 87,
  coordinates: [18.6, 54.38],
} as unknown as Drone

const LABELS = {
  drones: 'Drones (1)',
  hubs: 'Hubs (1)',
  orders: 'Orders (0)',
  events: 'Events',
} as const

function Panel({ initial = 'orders' as OperationsTab }) {
  const [tab, setTab] = useState<OperationsTab>(initial)
  const [counter, setCounter] = useState(0)
  return (
    <OperationsPanel tab={tab} onTabChange={setTab} labels={LABELS}>
      <button type="button" onClick={() => setCounter((value) => value + 1)}>
        {tab} count {counter}
      </button>
    </OperationsPanel>
  )
}

describe('OperationsPanel', () => {
  it('is closed by default and shows the four tabs once opened', () => {
    render(<Panel />)
    expect(screen.getByRole('button', { name: 'Operations' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.queryByRole('tab')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Drones (1)',
      'Hubs (1)',
      'Orders (0)',
      'Events',
    ])
    expect(screen.getByRole('tab', { name: 'Orders (0)' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveClass('overflow-y-auto')
  })

  it('shows the tab chosen while closed when it is opened later', () => {
    render(<Panel initial="hubs" />)

    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    expect(screen.getByRole('tab', { name: 'Hubs (1)' })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches tabs by click and by arrow keys, Home and End, with roving focus', () => {
    render(<Panel />)
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))
    const tab = (name: string) => screen.getByRole('tab', { name })

    fireEvent.click(tab('Drones (1)'))
    expect(tab('Drones (1)')).toHaveAttribute('aria-selected', 'true')
    expect(tab('Drones (1)')).toHaveAttribute('tabindex', '0')
    expect(tab('Hubs (1)')).toHaveAttribute('tabindex', '-1')

    fireEvent.keyDown(tab('Drones (1)'), { key: 'ArrowRight' })
    expect(tab('Hubs (1)')).toHaveAttribute('aria-selected', 'true')
    expect(tab('Hubs (1)')).toHaveFocus()

    fireEvent.keyDown(tab('Hubs (1)'), { key: 'End' })
    expect(tab('Events')).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(tab('Events'), { key: 'ArrowRight' }) // wraps around
    expect(tab('Drones (1)')).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(tab('Drones (1)'), { key: 'ArrowLeft' })
    expect(tab('Events')).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(tab('Events'), { key: 'Home' })
    expect(tab('Drones (1)')).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps its open state when a tab is switched', () => {
    render(<Panel />)
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    fireEvent.click(screen.getByRole('tab', { name: 'Events' }))

    expect(screen.getByRole('button', { name: 'Operations' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })
})

describe('Drones and Hubs lists', () => {
  it('lists a drone with status, battery and Hub and selects it by click', () => {
    const onSelect = vi.fn()
    render(
      <DronesList
        drones={[DRONE]}
        hubs={[HUB]}
        selectedDroneId="DRN-001"
        onSelectDrone={onSelect}
      />,
    )

    const row = screen.getByRole('button', { name: /DRN-001/ })
    expect(row).toHaveTextContent('Idle · 87%')
    expect(row).toHaveTextContent('Galeria Bałtycka')
    expect(row).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(row)
    expect(onSelect).toHaveBeenCalledWith('DRN-001')
  })

  it('lists a Hub with its docked count and selects it by click', () => {
    const onSelect = vi.fn()
    render(
      <HubsList
        hubs={[HUB]}
        dockedCounts={new Map([['hub-a', 2]])}
        selectedHubId={null}
        onSelectHub={onSelect}
      />,
    )

    const row = screen.getByRole('button', { name: /Galeria Bałtycka/ })
    expect(row).toHaveTextContent('2 / 6 drones')
    expect(row).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(row)
    expect(onSelect).toHaveBeenCalledWith('hub-a')
  })

  it('shows honest empty states', () => {
    const noop = vi.fn()
    const { rerender } = render(
      <DronesList drones={[]} hubs={[]} selectedDroneId={null} onSelectDrone={noop} />,
    )
    expect(screen.getByText('No drones.')).toBeInTheDocument()
    rerender(
      <HubsList hubs={[]} dockedCounts={new Map()} selectedHubId={null} onSelectHub={noop} />,
    )
    expect(screen.getByText('No Hubs.')).toBeInTheDocument()
  })
})

describe('buildNotices', () => {
  const quiet = {
    emergencies: [],
    rainWarningActive: false,
    lprActive: false,
    flightsUnavailable: false,
    flightsStale: false,
    fleetStale: false,
    workerStoppedWhileFlying: false,
  }
  const emergency = { missionId: 'MIS-1', droneId: 'DRN-9' } as unknown as Flight

  it('has nothing to say while all is well', () => {
    expect(buildNotices(quiet)).toEqual([])
  })

  it('lists critical emergencies first, then the other current conditions', () => {
    const notices = buildNotices({
      ...quiet,
      emergencies: [emergency],
      rainWarningActive: true,
      lprActive: true,
      workerStoppedWhileFlying: true,
      flightsStale: true,
      fleetStale: true,
    })

    expect(notices.map((notice) => notice.id)).toEqual([
      'emergency-MIS-1',
      'rain',
      'lpr',
      'worker',
      'flights',
      'fleet',
    ])
    expect(notices[0]).toMatchObject({ tone: 'critical' })
    expect(notices[0].text).toContain('DRN-9')
  })

  it('says unavailable rather than stale when flights cannot be read at all', () => {
    const notices = buildNotices({ ...quiet, flightsUnavailable: true, flightsStale: true })

    expect(notices).toHaveLength(1)
    expect(notices[0].text).toMatch(/unavailable/)
  })
})

describe('EventsTab', () => {
  it('shows a clear empty state and does not claim to be a full history', () => {
    render(<EventsTab notices={[]} activity={null} activityRefreshKey={0} />)

    expect(screen.getByText('No active alerts.')).toBeInTheDocument()
    expect(screen.getByText(/Select a drone or an order/)).toBeInTheDocument()
    expect(screen.queryByText(/history/i)).toBeNull()
  })

  it('lists the current alerts', () => {
    render(
      <EventsTab
        notices={[{ id: 'rain', tone: 'warning', text: 'Rain warning active: x' }]}
        activity={null}
        activityRefreshKey={0}
      />,
    )

    expect(screen.getByText('Rain warning active: x')).toBeInTheDocument()
    expect(screen.queryByText('No active alerts.')).toBeNull()
  })

  it('reads the selected drone’s activity, and the selected order’s', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve(jsonResponse([])))
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(
      <EventsTab notices={[]} activity={{ kind: 'drone', id: 'DRN-001' }} activityRefreshKey={0} />,
    )
    expect(await screen.findByText('No recorded activity for this drone.')).toBeInTheDocument()
    expect(String(fetchMock.mock.calls[0][0])).toContain('drone_id=DRN-001')

    rerender(
      <EventsTab notices={[]} activity={{ kind: 'order', id: 'ORD-001' }} activityRefreshKey={0} />,
    )
    expect(await screen.findByText('No recorded activity for this order.')).toBeInTheDocument()
  })
})
