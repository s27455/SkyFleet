import type { FocusPosition } from './focusTarget'

/** The least zoom a focus ends at: city-block level, where a marker is easy to identify. */
export const FOCUS_ZOOM = 15
export const FOCUS_DURATION_MS = 900
/**
 * On a phone the detail panel covers the lower part of the map, so the target is shown this
 * fraction of the map height above the centre. (On a wide screen the panels flank the map evenly,
 * so the centre is already the free middle.)
 */
export const NARROW_OFFSET_FRACTION = -0.25

/** Tailwind's `sm` breakpoint: below it the layout is the phone layout. */
const WIDE_QUERY = '(min-width: 640px)'

export function isNarrowViewport(): boolean {
  return typeof window.matchMedia === 'function' && !window.matchMedia(WIDE_QUERY).matches
}

/** The part of the Mapbox map that a focus needs, so it can be tested without WebGL. */
export interface FocusableMap {
  getZoom(): number
  getContainer(): { clientHeight: number }
  flyTo(options: {
    center: [number, number]
    zoom: number
    offset: [number, number]
    duration: number
    essential: boolean
  }): unknown
}

/**
 * Moves the camera once to a position. The zoom is the operator's own when it is already closer than
 * `FOCUS_ZOOM`, otherwise `FOCUS_ZOOM`, so it never zooms out on someone who zoomed in. A new call
 * replaces a running animation (Mapbox stops the earlier one), so the latest call always wins.
 * With reduced motion the duration is 0 and the move is immediate.
 */
export function focusCamera(
  map: FocusableMap,
  position: FocusPosition,
  { reducedMotion, narrow }: { reducedMotion: boolean; narrow: boolean },
): void {
  const height = narrow ? map.getContainer().clientHeight : 0
  map.flyTo({
    center: [position[0], position[1]],
    zoom: Math.max(map.getZoom(), FOCUS_ZOOM),
    offset: [0, Math.round(height * NARROW_OFFSET_FRACTION) || 0], // `|| 0`: never -0
    duration: reducedMotion ? 0 : FOCUS_DURATION_MS,
    // an immediate move must not be turned into an animation by the library
    essential: reducedMotion,
  })
}
