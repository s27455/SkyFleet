import { render, screen } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MapView } from './MapView'

type Handler = () => void

// jsdom has no WebGL, so the Mapbox Map class is replaced with a controllable fake.
const fake = vi.hoisted(() => {
  const instances: {
    handlers: Record<string, Handler>
    remove: () => void
    resize: () => void
  }[] = []
  return { instances }
})

vi.mock('mapbox-gl', () => {
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
  return { default: { Map: FakeMap } }
})

describe('MapView', () => {
  beforeEach(() => {
    fake.instances.length = 0
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
})
