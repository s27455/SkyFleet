import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { type ReactNode, useEffect, useRef, useState } from 'react'

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

/**
 * Interactive Mapbox map filling its positioned parent (`absolute inset-0`).
 * Presentation only: operational data is added by later features.
 */
export function MapView() {
  const token = getMapboxToken()
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<MapStatus>('loading')

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
