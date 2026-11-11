import { fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Hub } from '../../types/hub'
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
    remove: () => void
  }[] = []
  return { instances, markers }
})

vi.mock('mapbox-gl', () => {
  class FakeMarker {
    element: HTMLElement
    lngLat?: [number, number]
    remove = vi.fn(() => this.element.remove())
    constructor(options: { element: HTMLElement }) {
      this.element = options.element
      fake.markers.push(this)
    }
    setLngLat(lngLat: [number, number]) {
      this.lngLat = lngLat
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
    city: 'Gdańsk',
    coordinates: [18.6, 54.4],
    status: 'operational',
    droneCapacity: 50,
  },
  {
    id: 'hub-b',
    name: 'Hub B',
    city: 'Gdynia',
    coordinates: [18.5, 54.5],
    status: 'operational',
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
      expect(screen.getByRole('button', { name: 'Hub: Hub A, Gdańsk' })).toBeInTheDocument()
    })

    it('reports the selected hub when a marker is clicked', () => {
      vi.stubEnv('VITE_MAPBOX_TOKEN', 'pk.test')
      const onSelectHub = vi.fn()

      render(<MapView hubs={TEST_HUBS} onSelectHub={onSelectHub} />)
      act(() => fake.instances[0].handlers.load())
      fireEvent.click(screen.getByRole('button', { name: 'Hub: Hub B, Gdynia' }))

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
