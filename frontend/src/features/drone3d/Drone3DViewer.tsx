import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

import { usePrefersReducedMotion } from '../flights/usePrefersReducedMotion'
import type { CameraApi } from './DroneCanvas'
import type { DronePartId } from './droneParts'
import { isWebGLAvailable } from './webgl'

// The Three.js code is a separate chunk: it is only fetched when a viewer is actually shown.
const DroneCanvas = lazy(() => import('./DroneCanvas'))

export interface Drone3DViewerProps {
  /** Spin the propellers. Ignored when the user prefers reduced motion. Default: true. */
  animate?: boolean
  /** Reports a clicked part (motor, battery, ...). Reserved for the future component inspector. */
  onPartSelect?: (part: DronePartId) => void
  /** Sizing/placement; the viewer fills its box, so give it a height. */
  className?: string
}

const BUTTON_CLASS =
  'rounded border border-line bg-surface/80 px-2 py-1 text-xs text-fg backdrop-blur hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent'

function Placeholder({ role, children }: { role?: 'status'; children: ReactNode }) {
  return (
    <div
      role={role}
      className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center text-sm text-fg-muted"
    >
      {children}
    </div>
  )
}

function Fallback() {
  return (
    <Placeholder>
      <svg
        viewBox="0 0 64 64"
        className="size-14 text-fg-muted"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <rect x="26" y="22" width="12" height="20" rx="6" />
        <path d="M28 26 14 14M36 26l14-12M28 38 14 50M36 38l14 12" />
        <circle cx="12" cy="12" r="6" />
        <circle cx="52" cy="12" r="6" />
        <circle cx="12" cy="52" r="6" />
        <circle cx="52" cy="52" r="6" />
      </svg>
      <p className="font-medium text-fg">3D view unavailable</p>
      <p>WebGL is not available in this browser, so the drone model cannot be shown.</p>
    </Placeholder>
  )
}

class ViewerErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: unknown) {
    console.error('Drone 3D viewer failed', error)
  }
  render() {
    return this.state.failed ? <Fallback /> : this.props.children
  }
}

/** True while the element is on screen and the tab is visible (always true without the APIs). */
function useIsActive(element: React.RefObject<Element | null>): boolean {
  const [onScreen, setOnScreen] = useState(true)
  const [tabVisible, setTabVisible] = useState(() => document.visibilityState !== 'hidden')

  useEffect(() => {
    const target = element.current
    if (!target || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting))
    observer.observe(target)
    return () => observer.disconnect()
  }, [element])

  useEffect(() => {
    const onChange = () => setTabVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])

  return onScreen && tabVisible
}

const ROTATE_STEP = 0.15
const TILT_STEP = 0.1

/**
 * Reusable interactive 3D quadcopter. Orbit by dragging or with the arrow keys; zoom with the
 * buttons, +/- keys, or the wheel once the viewer has focus (so it never captures page scrolling).
 * Renders only while needed: animation frames run just while the propellers spin on a visible tab.
 */
export function Drone3DViewer({
  animate = true,
  onPartSelect,
  className = '',
}: Drone3DViewerProps) {
  const [webgl] = useState(isWebGLAvailable)
  const [contextLost, setContextLost] = useState(false)
  const [focused, setFocused] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const api = useRef<CameraApi | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  const active = useIsActive(root)
  const running = animate && !reducedMotion && active

  const onContextLost = useCallback(() => setContextLost(true), [])

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || !api.current) return
    const handled = (() => {
      switch (event.key) {
        case 'ArrowLeft':
          return api.current.orbit(-ROTATE_STEP, 0)
        case 'ArrowRight':
          return api.current.orbit(ROTATE_STEP, 0)
        case 'ArrowUp':
          return api.current.orbit(0, -TILT_STEP)
        case 'ArrowDown':
          return api.current.orbit(0, TILT_STEP)
        case '+':
        case '=':
          return api.current.zoom(0.85)
        case '-':
        case '_':
          return api.current.zoom(1 / 0.85)
        case 'Home':
        case '0':
          return api.current.reset()
        default:
          return 'ignored'
      }
    })()
    if (handled !== 'ignored') event.preventDefault()
  }

  const showCanvas = webgl && !contextLost

  return (
    <div
      ref={root}
      tabIndex={0}
      role="group"
      aria-label="Interactive 3D drone model. Use arrow keys to rotate, plus and minus to zoom, Home to reset."
      onKeyDown={onKeyDown}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      className={`@container relative overflow-hidden rounded-lg bg-linear-to-b from-surface-raised to-canvas focus-visible:outline-2 focus-visible:outline-accent ${className}`}
    >
      {showCanvas ? (
        <ViewerErrorBoundary>
          <Suspense fallback={<Placeholder role="status">Loading 3D model…</Placeholder>}>
            <DroneCanvas
              running={running}
              wheelZoom={focused}
              apiRef={api}
              onPartSelect={onPartSelect}
              onContextLost={onContextLost}
            />
          </Suspense>
          <div className="absolute right-2 bottom-2 flex gap-1">
            <button
              type="button"
              className={BUTTON_CLASS}
              aria-label="Zoom in"
              onClick={() => api.current?.zoom(0.85)}
            >
              +
            </button>
            <button
              type="button"
              className={BUTTON_CLASS}
              aria-label="Zoom out"
              onClick={() => api.current?.zoom(1 / 0.85)}
            >
              −
            </button>
            <button type="button" className={BUTTON_CLASS} onClick={() => api.current?.reset()}>
              Reset view
            </button>
          </div>
          <p className="pointer-events-none absolute bottom-2 left-2 hidden text-xs text-fg-muted @md:block">
            Drag to rotate · click, then scroll to zoom
          </p>
        </ViewerErrorBoundary>
      ) : (
        <Fallback />
      )}
    </div>
  )
}
