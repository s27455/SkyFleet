import { fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import type { FlightVisual } from '../flights/interpolation'
import { MapView } from './MapView'

type Handler = () => void

// jsdom has no WebGL, so the Mapbox Map class is replaced with a controllable fake.
const fake = vi.hoisted(() => {
  const instances: {
    handlers: Record<string, Handler>
    remove: () => void
    resize: () => void
  }[] = []
  const markers: {
    element: HTMLElement
    lngLat?: [number, number]
    offset?: [number, number]
    remove: () => void
  }[] = []
  return { instances, markers }
})

vi.mock('mapbox-gl', () => {
  class FakeMarker {
    element: HTMLElement
    lngLat?: [number, number]
    offset?: [number, number]
    remove = vi.fn(() => this.element.remove())
    constructor(options: { element: HTMLElement; offset?: [number, number] }) {
      this.element = options.element
      this.offset = options.offset
      fake.markers.push(this)
    }
    setLngLat(lngLat: [number, number]) {
      this.lngLat = lngLat
      return this
    }
    setOffset(offset: [number, number]) {
      this.offset = offset
      return this
    }
    addTo() {
      document.body.appendChild(this.element)
      return this
    }
  }
  class FakeMap {
    handlers: Record<string, Handler> = {}
    remove = vi.fn()
    resize = vi.fn()
    constructor() {
      fake.instances.push(this)
    }
    on(event: string, handler: Handler) {
      this.handlers[event] = handler
    }
  }
  return { default: { Map: FakeMap, Marker: FakeMarker } }
})

const TEST_HUBS: Hub[] = [
  {
    id: 'hub-a',
    name: 'Hub A',
    address: 'Ulica A 1, Gdańsk',
    coordinates: [18.6, 54.4],
    droneCapacity: 50,
  },
  {
    id: 'hub-b',
    name: 'Hub B',
    address: 'Ulica B 2, Gdynia',
    coordinates: [18.5, 54.5],
    droneCapacity: 50,
  },
]

describe('MapView', () => {
  beforeEach(() => {
    fake.instances.length = 0
    fake.markers.length = 0
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
  })

  it('explains the missing token and does not create a map', () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', '')

    render(<MapView />)

    expect(screen.getByRole('alert')).toHaveTextContent('VITE_MAPBOX_TOKEN')
    expect(fake.instances).toHaveLength(0)
  })

  it('shows a loading state until the map has loaded', () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

    render(<MapView />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading map')

    act(() => fake.instances[0].handlers.load())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows an error when the map fails before loading', () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.bad')

    render(<MapView />)
    act(() => fake.instances[0].handlers.error())

    expect(screen.getByRole('alert')).toHaveTextContent('Map failed to load')
  })

  it('keeps the map visible when an error happens after it has loaded', () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

    render(<MapView />)
    act(() => fake.instances[0].handlers.load())
    act(() => fake.instances[0].handlers.error())

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('removes the map instance on unmount', () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

    const { unmount } = render(<MapView />)
    const map = fake.instances[0]
    unmount()

    expect(map.remove).toHaveBeenCalledOnce()
  })

  describe('hub markers', () => {
    it('places no markers until the map has loaded', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

      render(<MapView hubs={TEST_HUBS} />)

      expect(fake.markers).toHaveLength(0)
    })

    it('places one marker per hub at its coordinates once loaded', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

      render(<MapView hubs={TEST_HUBS} />)
      act(() => fake.instances[0].handlers.load())

      expect(fake.markers.map((m) => m.lngLat)).toEqual([
        [18.6, 54.4],
        [18.5, 54.5],
      ])
      expect(
        screen.getByRole('button', { name: 'Hub: Hub A, Ulica A 1, Gdańsk' }),
      ).toBeInTheDocument()
    })

    it('reports the selected hub when a marker is clicked', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
      const onSelectHub = vi.fn()

      render(<MapView hubs={TEST_HUBS} onSelectHub={onSelectHub} />)
      act(() => fake.instances[0].handlers.load())
      fireEvent.click(screen.getByRole('button', { name: 'Hub: Hub B, Ulica B 2, Gdynia' }))

      expect(onSelectHub).toHaveBeenCalledWith('hub-b')
    })

    it('marks only the selected hub as pressed', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

      render(<MapView hubs={TEST_HUBS} selectedHubId="hub-a" />)
      act(() => fake.instances[0].handlers.load())

      expect(screen.getByRole('button', { name: /Hub A/ })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByRole('button', { name: /Hub B/ })).toHaveAttribute('aria-pressed', 'false')
    })

    it('keeps the same marker elements when the selection changes', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

      const { rerender } = render(<MapView hubs={TEST_HUBS} selectedHubId={null} />)
      act(() => fake.instances[0].handlers.load())
      const buttonA = screen.getByRole('button', { name: /Hub A/ })
      buttonA.focus()

      rerender(<MapView hubs={TEST_HUBS} selectedHubId="hub-a" />)

      expect(screen.getByRole('button', { name: /Hub A/ })).toBe(buttonA)
      expect(buttonA).toHaveAttribute('aria-pressed', 'true')
      expect(buttonA).toHaveFocus()
      expect(fake.markers).toHaveLength(2)
    })

    it('removes markers on unmount', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')

      const { unmount } = render(<MapView hubs={TEST_HUBS} />)
      act(() => fake.instances[0].handlers.load())
      const markers = [...fake.markers]
      unmount()

      markers.forEach((marker) => expect(marker.remove).toHaveBeenCalled())
    })
  })
})

const TEST_MODEL = {
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
}

const TEST_DRONES: Drone[] = [
  {
    id: 'DRN-001',
    hubId: 'hub-a',
    status: 'IN_FLIGHT',
    batteryPct: 100,
    coordinates: [18.6, 54.4],
    model: TEST_MODEL,
  },
  {
    id: 'DRN-002',
    hubId: 'hub-a',
    status: 'IN_FLIGHT',
    batteryPct: 90,
    coordinates: [18.6, 54.4],
    model: TEST_MODEL,
  },
]

describe('MapView drone markers', () => {
  beforeEach(() => {
    fake.instances.length = 0
    fake.markers.length = 0
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
  })

  const loadMap = () => act(() => fake.instances[0].handlers.load())
  const droneMarkers = () => fake.markers.filter((m) => m.element.dataset.markerKind === 'drone')

  it('places no drone markers until the map has loaded', () => {
    render(<MapView drones={TEST_DRONES} />)

    expect(droneMarkers()).toHaveLength(0)
  })

  it('places each drone at its real coordinates, whatever the display offset', () => {
    render(
      <MapView
        drones={TEST_DRONES}
        droneOffsets={
          new Map([
            ['DRN-001', [0, -44]],
            ['DRN-002', [38, 22]],
          ])
        }
      />,
    )
    loadMap()

    expect(droneMarkers().map((m) => m.lngLat)).toEqual([
      [18.6, 54.4],
      [18.6, 54.4],
    ])
    expect(droneMarkers().map((m) => m.offset)).toEqual([
      [0, -44],
      [38, 22],
    ])
  })

  it('uses no pixel offset for a drone without a display offset', () => {
    render(<MapView drones={TEST_DRONES} />)
    loadMap()

    expect(droneMarkers().map((m) => m.offset)).toEqual([
      [0, 0],
      [0, 0],
    ])
  })

  it('gives drone and Hub markers different shapes of marker and accessible names', () => {
    render(<MapView hubs={TEST_HUBS} drones={TEST_DRONES} />)
    loadMap()

    const hub = screen.getByRole('button', { name: /^Hub: Hub A/ })
    const drone = screen.getByRole('button', { name: 'Drone DRN-001, In flight, battery 100%' })
    expect(hub.dataset.markerKind).toBe('hub')
    expect(drone.dataset.markerKind).toBe('drone')
    expect(drone.className).toContain('rounded-full')
    expect(drone.className).toContain('size-6') // small: 24px target, 12px glyph
    expect(drone.querySelector('svg')).toHaveAttribute('width', '12')
    expect(hub.className).not.toContain('rounded-full')
    expect(drone.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('reports the selected drone when a drone marker is clicked', () => {
    const onSelectDrone = vi.fn()
    render(<MapView drones={TEST_DRONES} onSelectDrone={onSelectDrone} />)
    loadMap()

    fireEvent.click(screen.getByRole('button', { name: /DRN-002/ }))

    expect(onSelectDrone).toHaveBeenCalledWith('DRN-002')
  })

  it('does not report a Hub selection for a drone click and vice versa', () => {
    const onSelectHub = vi.fn()
    const onSelectDrone = vi.fn()
    render(
      <MapView
        hubs={TEST_HUBS}
        drones={TEST_DRONES}
        onSelectHub={onSelectHub}
        onSelectDrone={onSelectDrone}
      />,
    )
    loadMap()

    fireEvent.click(screen.getByRole('button', { name: /DRN-001/ }))
    expect(onSelectHub).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /^Hub: Hub A/ }))
    expect(onSelectHub).toHaveBeenCalledWith('hub-a')
    expect(onSelectDrone).toHaveBeenCalledTimes(1)
  })

  it('marks only the selected drone as pressed', () => {
    render(<MapView drones={TEST_DRONES} selectedDroneId="DRN-001" />)
    loadMap()

    expect(screen.getByRole('button', { name: /DRN-001/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /DRN-002/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('keeps the same drone marker element and focus when the selection changes', () => {
    const { rerender } = render(<MapView drones={TEST_DRONES} selectedDroneId={null} />)
    loadMap()
    const button = screen.getByRole('button', { name: /DRN-001/ })
    button.focus()

    rerender(<MapView drones={TEST_DRONES} selectedDroneId="DRN-001" />)

    expect(screen.getByRole('button', { name: /DRN-001/ })).toBe(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button).toHaveFocus()
    expect(droneMarkers()).toHaveLength(2)
  })

  it('applies new display offsets to the existing markers without rebuilding them', () => {
    const { rerender } = render(
      <MapView drones={TEST_DRONES} droneOffsets={new Map([['DRN-001', [0, -46]]])} />,
    )
    loadMap()
    const button = screen.getByRole('button', { name: /DRN-001/ })
    button.focus()
    const marker = droneMarkers()[0]

    rerender(<MapView drones={TEST_DRONES} droneOffsets={new Map([['DRN-001', [40, 23]]])} />)

    expect(screen.getByRole('button', { name: /DRN-001/ })).toBe(button)
    expect(button).toHaveFocus()
    expect(droneMarkers()).toHaveLength(2)
    expect(marker.offset).toEqual([40, 23])
    expect(marker.lngLat).toEqual([18.6, 54.4]) // the real coordinates never change
    expect(marker.remove).not.toHaveBeenCalled()
  })

  it('does not rebuild drone markers when only the Hubs change', () => {
    const { rerender } = render(<MapView hubs={[]} drones={TEST_DRONES} />)
    loadMap()
    const button = screen.getByRole('button', { name: /DRN-001/ })
    button.focus()

    rerender(<MapView hubs={TEST_HUBS} drones={TEST_DRONES} />)

    expect(screen.getByRole('button', { name: /DRN-001/ })).toBe(button)
    expect(button).toHaveFocus()
    expect(droneMarkers()).toHaveLength(2)
  })

  it('gives drone markers a higher stacking order than Hub markers', () => {
    render(<MapView hubs={TEST_HUBS} drones={TEST_DRONES} />)
    loadMap()

    expect(screen.getByRole('button', { name: /^Hub: Hub A/ })).toHaveClass('z-10')
    expect(screen.getByRole('button', { name: /DRN-001/ })).toHaveClass('z-20')
  })

  it('shows a non-colour cue on the selected drone marker', () => {
    render(<MapView drones={TEST_DRONES} selectedDroneId="DRN-001" />)
    loadMap()

    expect(screen.getByRole('button', { name: /DRN-001/ })).toHaveClass('ring-4')
    expect(screen.getByRole('button', { name: /DRN-002/ })).not.toHaveClass('ring-4')
  })

  it('keeps Hub markers when the drones change, and the other way around', () => {
    const { rerender } = render(<MapView hubs={TEST_HUBS} drones={[]} />)
    loadMap()
    expect(fake.markers).toHaveLength(2)

    rerender(<MapView hubs={TEST_HUBS} drones={TEST_DRONES} />)

    expect(screen.getAllByRole('button', { name: /^Hub: / })).toHaveLength(2)
    expect(droneMarkers()).toHaveLength(2)
  })

  it('removes drone markers on unmount', () => {
    const { unmount } = render(<MapView drones={TEST_DRONES} />)
    loadMap()
    const markers = [...droneMarkers()]
    unmount()

    markers.forEach((marker) => expect(marker.remove).toHaveBeenCalled())
  })
})

describe('MapView Hub drone badges and away markers', () => {
  beforeEach(() => {
    fake.instances.length = 0
    fake.markers.length = 0
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
  })

  const loadMap = () => act(() => fake.instances[0].handlers.load())
  const badge = (hubName: string) =>
    screen
      .getByRole('button', { name: new RegExp(`^Hub: ${hubName},`) })
      .querySelector<HTMLElement>('[data-drone-badge]')!

  it('shows the docked count as a badge and in the Hub accessible name', () => {
    render(<MapView hubs={TEST_HUBS} dockedCounts={new Map([['hub-a', 3]])} />)
    loadMap()

    const hubA = screen.getByRole('button', {
      name: 'Hub: Hub A, Ulica A 1, Gdańsk, 3 drones docked',
    })
    expect(badge('Hub A')).toHaveTextContent('3')
    expect(badge('Hub A')).toBeVisible()
    expect(badge('Hub A')).toHaveAttribute('aria-hidden', 'true')
    expect(hubA.dataset.markerKind).toBe('hub')
  })

  it('uses the singular for one drone and hides the badge at zero', () => {
    render(<MapView hubs={TEST_HUBS} dockedCounts={new Map([['hub-a', 1]])} />)
    loadMap()

    expect(screen.getByRole('button', { name: /Hub A.*, 1 drone docked$/ })).toBeInTheDocument()
    expect(badge('Hub B')).not.toBeVisible()
    expect(
      screen.getByRole('button', { name: 'Hub: Hub B, Ulica B 2, Gdynia' }),
    ).toBeInTheDocument()
  })

  it('updates the badge in place without rebuilding the Hub marker or losing focus', () => {
    const { rerender } = render(<MapView hubs={TEST_HUBS} dockedCounts={new Map()} />)
    loadMap()
    const button = screen.getByRole('button', { name: /^Hub: Hub A/ })
    button.focus()

    rerender(<MapView hubs={TEST_HUBS} dockedCounts={new Map([['hub-a', 2]])} />)

    expect(screen.getByRole('button', { name: /^Hub: Hub A/ })).toBe(button)
    expect(button).toHaveFocus()
    expect(badge('Hub A')).toHaveTextContent('2')
    expect(fake.markers).toHaveLength(2)
  })

  it('keeps the badge when the Hub is selected, and a Hub click still selects it', () => {
    const onSelectHub = vi.fn()
    render(
      <MapView
        hubs={TEST_HUBS}
        dockedCounts={new Map([['hub-a', 3]])}
        selectedHubId="hub-a"
        onSelectHub={onSelectHub}
      />,
    )
    loadMap()

    fireEvent.click(badge('Hub A')) // a click on the badge bubbles to the Hub button
    expect(onSelectHub).toHaveBeenCalledWith('hub-a')
    expect(badge('Hub A')).toHaveTextContent('3')
  })

  it('marks a non-flying drone as away from a Hub with a distinct dashed marker', () => {
    const away: Drone = { ...TEST_DRONES[0], status: 'MAINTENANCE', id: 'DRN-009' }
    render(<MapView drones={[TEST_DRONES[0], away]} />)
    loadMap()

    const flying = screen.getByRole('button', { name: /DRN-001/ })
    const parked = screen.getByRole('button', {
      name: 'Drone DRN-009, Maintenance, battery 100%, not at a Hub',
    })
    expect(flying.dataset.placement).toBe('in-flight')
    expect(flying).not.toHaveClass('border-dashed')
    expect(parked.dataset.placement).toBe('away')
    expect(parked).toHaveClass('border-dashed')
  })
})

const TEST_ORDERS: Order[] = [
  {
    id: 'ORD-001',
    originHubId: 'hub-a',
    destinationAddress: 'ul. Test 1',
    coordinates: [18.7, 54.5],
    packageWeightKg: 1.5,
    status: 'READY_FOR_PICKUP',
    deliveredAt: null,
    createdAt: '2026-11-11T21:53:08Z',
    updatedAt: '2026-11-11T21:53:08Z',
  },
  {
    id: 'ORD-002',
    originHubId: 'hub-a',
    destinationAddress: 'ul. Test 2',
    coordinates: [18.7, 54.5],
    packageWeightKg: 0.5,
    status: 'READY_FOR_PICKUP',
    deliveredAt: null,
    createdAt: '2026-11-11T21:53:08Z',
    updatedAt: '2026-11-11T21:53:08Z',
  },
]

describe('MapView order destination markers', () => {
  beforeEach(() => {
    fake.instances.length = 0
    fake.markers.length = 0
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
  })

  const loadMap = () => act(() => fake.instances[0].handlers.load())
  const orderMarkers = () => fake.markers.filter((m) => m.element.dataset.markerKind === 'order')

  it('places no order markers until the map has loaded', () => {
    render(<MapView orders={TEST_ORDERS} />)

    expect(orderMarkers()).toHaveLength(0)
  })

  it('places each destination at its real coordinates, whatever the display offset', () => {
    render(
      <MapView
        orders={TEST_ORDERS}
        orderOffsets={
          new Map([
            ['ORD-001', [0, -40]],
            ['ORD-002', [35, 20]],
          ])
        }
      />,
    )
    loadMap()

    expect(orderMarkers().map((m) => m.lngLat)).toEqual([
      [18.7, 54.5],
      [18.7, 54.5],
    ])
    expect(orderMarkers().map((m) => m.offset)).toEqual([
      [0, -40],
      [35, 20],
    ])
  })

  it('reports the selected order when a destination marker is clicked, and nothing else', () => {
    const onSelectOrder = vi.fn()
    const onSelectHub = vi.fn()
    render(
      <MapView
        hubs={TEST_HUBS}
        orders={TEST_ORDERS}
        onSelectOrder={onSelectOrder}
        onSelectHub={onSelectHub}
      />,
    )
    loadMap()

    fireEvent.click(screen.getByRole('button', { name: /^Order ORD-002 destination/ }))

    expect(onSelectOrder).toHaveBeenCalledWith('ORD-002')
    expect(onSelectHub).not.toHaveBeenCalled()
  })

  it('recolours a marker in place as its order is delivered and removes only its own', () => {
    const at = (status: Order['status']): Order[] =>
      TEST_ORDERS.map((order) => (order.id === 'ORD-001' ? { ...order, status } : order))
    const { rerender } = render(<MapView orders={at('READY_FOR_PICKUP')} />)
    loadMap()
    const marker = screen.getByRole('button', { name: /^Order ORD-001 destination/ })
    const other = screen.getByRole('button', { name: /^Order ORD-002 destination/ })
    const diamond = marker.querySelector('[data-order-diamond]')!
    marker.focus()
    expect(marker).toHaveAttribute('data-order-state', 'pending')
    expect(diamond).toHaveClass('bg-status-neutral')
    expect(orderMarkers()).toHaveLength(2)

    rerender(<MapView orders={at('OUT_FOR_DELIVERY')} />)
    expect(marker).toHaveAttribute('data-order-state', 'in_progress')
    expect(diamond).toHaveClass('bg-status-active')
    expect(marker).toHaveAccessibleName(/Out for delivery \(In delivery\)/)

    rerender(<MapView orders={at('DELIVERED')} />)
    expect(marker).toHaveAttribute('data-order-state', 'delivered')
    expect(diamond).toHaveClass('bg-status-ok')
    expect(marker).toHaveAccessibleName(/Delivered \(Delivered\)/)
    // The same elements and markers: nothing was rebuilt, so no duplicates, flashes or lost focus.
    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toBe(marker)
    expect(marker).toHaveFocus()
    expect(orderMarkers()).toHaveLength(2)

    // The grace period ends: the active list drops the order and only its marker goes.
    rerender(<MapView orders={TEST_ORDERS.filter((order) => order.id !== 'ORD-001')} />)
    expect(screen.queryByRole('button', { name: /^Order ORD-001 destination/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^Order ORD-002 destination/ })).toBe(other)
    expect(document.querySelectorAll('[data-marker-kind="order"]')).toHaveLength(1)
  })

  it('draws an already delivered order green at once after a reload, with no client timer', () => {
    // A reload starts with the server's answer: the delivered order is in it (the server still
    // counts it active), so it is green straight away. Expiry is the server's job; the map only
    // follows what the active list returns, so a reload can neither restart nor extend the window.
    const timers = vi.spyOn(globalThis, 'setTimeout')
    const delivered: Order = {
      ...TEST_ORDERS[0],
      status: 'DELIVERED',
      deliveredAt: '2026-11-13T12:00:00Z',
    }

    render(<MapView orders={[delivered, TEST_ORDERS[1]]} />)
    loadMap()

    const marker = screen.getByRole('button', { name: /^Order ORD-001 destination/ })
    expect(marker).toHaveAttribute('data-order-state', 'delivered')
    expect(marker.querySelector('[data-order-diamond]')).toHaveClass('bg-status-ok')
    expect(orderMarkers()).toHaveLength(2)
    const mapTimers = timers.mock.calls.filter(([, delay]) => delay === 120_000)
    expect(mapTimers).toHaveLength(0)
    timers.mockRestore()
  })

  it('adds a marker for a new order and leaves the existing markers untouched', () => {
    const { rerender } = render(<MapView orders={[TEST_ORDERS[0]]} />)
    loadMap()
    const first = screen.getByRole('button', { name: /^Order ORD-001 destination/ })
    const created = orderMarkers().length

    rerender(<MapView orders={TEST_ORDERS} />)

    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toBe(first)
    expect(screen.getByRole('button', { name: /^Order ORD-002 destination/ })).toBeInTheDocument()
    expect(orderMarkers()).toHaveLength(created + 1) // only one marker was created
  })

  it('moves a marker when an order destination is edited, without rebuilding it', () => {
    const { rerender } = render(<MapView orders={TEST_ORDERS} />)
    loadMap()
    const marker = screen.getByRole('button', { name: /^Order ORD-001 destination/ })

    rerender(
      <MapView
        orders={TEST_ORDERS.map((order) =>
          order.id === 'ORD-001' ? { ...order, coordinates: [18.8, 54.6] } : order,
        )}
      />,
    )

    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toBe(marker)
    expect(orderMarkers().find((m) => m.element === marker)?.lngLat).toEqual([18.8, 54.6])
  })

  it('marks only the selected destination and keeps the element and focus on change', () => {
    const { rerender } = render(<MapView orders={TEST_ORDERS} selectedOrderId={null} />)
    loadMap()
    const button = screen.getByRole('button', { name: /^Order ORD-001 destination/ })
    button.focus()

    rerender(<MapView orders={TEST_ORDERS} selectedOrderId="ORD-001" />)

    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toBe(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button).toHaveFocus()
    expect(screen.getByRole('button', { name: /^Order ORD-002 destination/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(orderMarkers()).toHaveLength(2)
  })

  it('applies new offsets without rebuilding, and does not rebuild when only Hubs change', () => {
    const { rerender } = render(
      <MapView hubs={[]} orders={TEST_ORDERS} orderOffsets={new Map([['ORD-001', [0, -40]]])} />,
    )
    loadMap()
    const button = screen.getByRole('button', { name: /^Order ORD-001 destination/ })
    button.focus()
    const marker = orderMarkers()[0]

    rerender(
      <MapView
        hubs={TEST_HUBS}
        orders={TEST_ORDERS}
        orderOffsets={new Map([['ORD-001', [30, 25]]])}
      />,
    )

    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toBe(button)
    expect(button).toHaveFocus()
    expect(marker.offset).toEqual([30, 25])
    expect(marker.lngLat).toEqual([18.7, 54.5])
    expect(marker.remove).not.toHaveBeenCalled()
  })

  it('stacks destinations below Hub and drone markers and removes them on unmount', () => {
    const { unmount } = render(
      <MapView hubs={TEST_HUBS} drones={TEST_DRONES} orders={TEST_ORDERS} />,
    )
    loadMap()

    expect(screen.getByRole('button', { name: /^Order ORD-001 destination/ })).toHaveClass('z-5')
    expect(screen.getByRole('button', { name: /^Hub: Hub A/ })).toHaveClass('z-10')
    expect(screen.getByRole('button', { name: /DRN-001/ })).toHaveClass('z-20')

    const markers = [...orderMarkers()]
    unmount()
    markers.forEach((marker) => expect(marker.remove).toHaveBeenCalled())
  })

  it('drops the destination markers when the orders are no longer provided', () => {
    const { rerender } = render(<MapView orders={TEST_ORDERS} />)
    loadMap()
    expect(orderMarkers()).toHaveLength(2)

    rerender(<MapView orders={[]} />)

    expect(screen.queryByRole('button', { name: /destination/ })).not.toBeInTheDocument()
  })
})

// --- flying drones: in-place updates and smooth motion between snapshots -----------------------

describe('MapView flying drone markers', () => {
  const FLYING: Drone = {
    id: 'DRN-010',
    hubId: 'hub-a',
    status: 'IN_FLIGHT',
    batteryPct: 98,
    coordinates: [18.6, 54.4],
    model: TEST_MODEL,
  }

  const visual = (overrides: Partial<FlightVisual> = {}): FlightVisual => ({
    droneId: 'DRN-010',
    motion: {
      position: [18.6, 54.4],
      target: { position: [18.7, 54.5], etaS: 10 },
      snapshotAgeS: 0,
    },
    receivedAt: 1000,
    animate: true,
    ...overrides,
  })

  let frames: ((time: number) => void)[]
  let now: number

  beforeEach(() => {
    fake.instances.length = 0
    fake.markers.length = 0
    frames = []
    now = 1000
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
    vi.stubGlobal('requestAnimationFrame', (callback: (time: number) => void) => {
      frames.push(callback)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      frames[id - 1] = () => {}
    })
    vi.spyOn(performance, 'now').mockImplementation(() => now)
  })

  const loadMap = () => act(() => fake.instances[0].handlers.load())
  const droneMarkers = () => fake.markers.filter((m) => m.element.dataset.markerKind === 'drone')
  const runFrame = () => {
    const pending = frames.splice(0)
    act(() => pending.forEach((callback) => callback(now)))
  }

  it('draws a flying drone at its flight snapshot', () => {
    render(
      <MapView
        drones={[{ ...FLYING, coordinates: [18.0, 54.0] }]}
        flights={[visual({ animate: false })]}
      />,
    )
    loadMap()

    expect(droneMarkers()[0].lngLat).toEqual([18.6, 54.4]) // the flight, not the drone row
  })

  it('moves the marker toward the backend target and never past it', () => {
    render(<MapView drones={[FLYING]} flights={[visual()]} />)
    loadMap()
    const marker = droneMarkers()[0]

    now = 1000 + 5000 // 5 s after the snapshot arrived: halfway of the 10 s eta
    runFrame()
    expect(marker.lngLat?.[0]).toBeCloseTo(18.65)
    expect(marker.lngLat?.[1]).toBeCloseTo(54.45)

    now = 1000 + 60_000
    runFrame()
    expect(marker.lngLat).toEqual([18.7, 54.5]) // clamped at the target
  })

  it('does not animate when told not to (reduced motion, stopped worker)', () => {
    render(<MapView drones={[FLYING]} flights={[visual({ animate: false })]} />)
    loadMap()

    expect(frames).toHaveLength(0)
    now = 1000 + 5000
    expect(droneMarkers()[0].lngLat).toEqual([18.6, 54.4]) // stays at the snapshot
  })

  it('stops animating on unmount', () => {
    const { unmount } = render(<MapView drones={[FLYING]} flights={[visual()]} />)
    loadMap()
    runFrame() // schedules the next frame

    unmount()
    const marker = droneMarkers()[0]
    const before = marker.lngLat
    now = 1000 + 9000
    runFrame()

    expect(marker.lngLat).toEqual(before) // the cancelled frame did nothing
  })

  it('updates the existing marker in place for each new snapshot, keeping focus', () => {
    const { rerender } = render(<MapView drones={[FLYING]} flights={[visual()]} />)
    loadMap()
    const button = screen.getByRole('button', { name: /DRN-010, In flight, battery 98%/ })
    button.focus()
    const marker = droneMarkers()[0]

    rerender(
      <MapView
        drones={[{ ...FLYING, batteryPct: 96, coordinates: [18.62, 54.42] }]}
        flights={[visual({ motion: { ...visual().motion, position: [18.62, 54.42] } })]}
      />,
    )

    expect(screen.getByRole('button', { name: /DRN-010, In flight, battery 96%/ })).toBe(button)
    expect(button).toHaveFocus()
    expect(droneMarkers()).toHaveLength(1)
    expect(marker.remove).not.toHaveBeenCalled()
    expect(marker.lngLat).toEqual([18.62, 54.42])
  })

  it('rebuilds a marker only when the drone changes kind, such as flying to parked', () => {
    const { rerender } = render(<MapView drones={[FLYING]} flights={[visual()]} />)
    loadMap()
    const first = droneMarkers()[0]

    rerender(<MapView drones={[{ ...FLYING, status: 'MAINTENANCE' }]} flights={[]} />)

    expect(first.remove).toHaveBeenCalled()
    const parked = screen.getByRole('button', {
      name: 'Drone DRN-010, Maintenance, battery 98%, not at a Hub',
    })
    expect(parked.dataset.placement).toBe('away')
  })

  it('removes the marker when the drone is no longer flying or away', () => {
    const { rerender } = render(<MapView drones={[FLYING]} flights={[visual()]} />)
    loadMap()
    const marker = droneMarkers()[0]

    rerender(<MapView drones={[]} flights={[]} />)

    expect(marker.remove).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /DRN-010/ })).not.toBeInTheDocument()
  })
})
