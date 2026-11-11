import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import type { Hub } from '../../types/hub'
import { MAP_STYLE, TRICITY_BOUNDS, TRICITY_FIT_PADDING_PX, getMapboxToken } from './mapConfig'

type MapStatus = 'loading' | 'ready' | 'error'

function MapMessage({ role, children }: { role: 'status' | 'alert'; children: ReactNode }) {
  return (
    <div
      role={role}
      className="absolute inset-0 z-10 flex items-center justify-center bg-canvas p-4 text-center text-sm text-fg-muted"
    >
      <div className="max-w-sm">{children}</div>
    </div>
  )
}

const NO_HUBS: readonly Hub[] = []

const HUB_MARKER_CLASS =
  'flex size-10 items-center justify-center rounded-md border-2 border-accent shadow-md cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
const HUB_MARKER_IDLE_CLASSES = ['bg-canvas', 'text-accent']
const HUB_MARKER_SELECTED_CLASSES = ['bg-accent', 'text-canvas']

function createHubMarkerElement(hub: Hub, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = HUB_MARKER_CLASS
  element.setAttribute('aria-label', `Hub: ${hub.name}, ${hub.address}`)
  element.textContent = 'H'
  element.addEventListener('click', onClick)
  setHubMarkerSelected(element, false)
  return element
}

/** Updates the existing element in place so keyboard focus survives a selection change. */
function setHubMarkerSelected(element: HTMLElement, selected: boolean) {
  element.classList.remove(...(selected ? HUB_MARKER_IDLE_CLASSES : HUB_MARKER_SELECTED_CLASSES))
  element.classList.add(...(selected ? HUB_MARKER_SELECTED_CLASSES : HUB_MARKER_IDLE_CLASSES))
  element.setAttribute('aria-pressed', String(selected))
}

interface MapViewProps {
  hubs?: readonly Hub[]
  selectedHubId?: string | null
  onSelectHub?: (hubId: string) => void
}

/**
 * Interactive Mapbox map filling its positioned parent (`absolute inset-0`).
 * Presentation only: it renders the Hubs it is given and reports selection; it owns no data.
 */
export function MapView({ hubs = NO_HUBS, selectedHubId = null, onSelectHub }: MapViewProps) {
  const token = getMapboxToken()
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const markerElementsRef = useRef(new Map<string, HTMLElement>())
  const onSelectHubRef = useRef(onSelectHub)
  const [status, setStatus] = useState<MapStatus>('loading')

  useEffect(() => {
    onSelectHubRef.current = onSelectHub
  }, [onSelectHub])

  // Markers are DOM-based (native keyboard/touch support); fine for a handful of Hubs.
  // They are rebuilt only when `hubs` changes, never on selection (see the effect below).
  useEffect(() => {
    const map = mapRef.current
    const elements = markerElementsRef.current
    if (status !== 'ready' || !map) return

    const markers = hubs.map((hub) => {
      const element = createHubMarkerElement(hub, () => onSelectHubRef.current?.(hub.id))
      elements.set(hub.id, element)
      return new mapboxgl.Marker({ element }).setLngLat(hub.coordinates).addTo(map)
    })

    return () => {
      markers.forEach((marker) => marker.remove())
      elements.clear()
    }
  }, [hubs, status])

  // Declared after the marker effect so it also styles freshly created markers.
  useEffect(() => {
    markerElementsRef.current.forEach((element, hubId) =>
      setHubMarkerSelected(element, hubId === selectedHubId),
    )
  }, [hubs, status, selectedHubId])

  useEffect(() => {
    const container = containerRef.current
    if (!token || !container) return

    let map: mapboxgl.Map
    try {
      map = new mapboxgl.Map({
        accessToken: token,
        container,
        style: MAP_STYLE,
        bounds: TRICITY_BOUNDS,
        fitBoundsOptions: { padding: TRICITY_FIT_PADDING_PX },
      })
    } catch {
      // Deferred so the state update is not a synchronous setState inside the effect body.
      queueMicrotask(() => setStatus('error'))
      return
    }

    mapRef.current = map

    let hasLoaded = false
    map.on('load', () => {
      hasLoaded = true
      setStatus('ready')
    })
    // Errors before the first load (bad token, style failure) are fatal. Later errors, such as a
    // single failed tile, must not hide a working map.
    map.on('error', () => {
      if (!hasLoaded) setStatus('error')
    })

    // Mapbox only listens to window resizes; the workspace can also change size on its own.
    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      mapRef.current = null
      map.remove()
    }
  }, [token])

  if (!token) {
    return (
      <MapMessage role="alert">
        <p className="font-medium text-fg">Map unavailable</p>
        <p className="mt-1">
          Set <code className="font-mono">VITE_MAPBOX_TOKEN</code> in{' '}
          <code className="font-mono">frontend/.env.local</code> and restart the dev server.
        </p>
      </MapMessage>
    )
  }

  return (
    <div className="absolute inset-0">
      {/* size-full, not absolute: mapbox-gl.css (unlayered) forces position: relative on this
          element and would override Tailwind's layered `absolute`, collapsing the height to 0. */}
      <div ref={containerRef} className="size-full" />
      {status === 'loading' && <MapMessage role="status">Loading map…</MapMessage>}
      {status === 'error' && (
        <MapMessage role="alert">
          <p className="font-medium text-fg">Map failed to load</p>
          <p className="mt-1">
            Check that your Mapbox token is valid and allowed for this site, then reload.
          </p>
        </MapMessage>
      )}
    </div>
  )
}
