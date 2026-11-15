import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  FOCUS_DURATION_MS,
  FOCUS_ZOOM,
  NARROW_OFFSET_FRACTION,
  type FocusableMap,
  focusCamera,
  isNarrowViewport,
} from './mapCamera'

afterEach(() => vi.unstubAllGlobals())

function fakeMap(zoom: number, height = 800) {
  const flyTo = vi.fn()
  const map: FocusableMap = {
    getZoom: () => zoom,
    getContainer: () => ({ clientHeight: height }),
    flyTo,
  }
  return { map, flyTo }
}

const WIDE = { reducedMotion: false, narrow: false }

describe('focusCamera', () => {
  it('flies to the position, as [longitude, latitude], with the minimum focus zoom', () => {
    const { map, flyTo } = fakeMap(11)

    focusCamera(map, [18.6, 54.38], WIDE)

    expect(flyTo).toHaveBeenCalledOnce()
    expect(flyTo).toHaveBeenCalledWith({
      center: [18.6, 54.38],
      zoom: FOCUS_ZOOM,
      offset: [0, 0],
      duration: FOCUS_DURATION_MS,
      essential: false,
    })
  })

  it("keeps the operator's closer zoom and never zooms out", () => {
    const close = fakeMap(17.3)
    focusCamera(close.map, [18.6, 54.38], WIDE)
    expect(close.flyTo.mock.calls[0][0].zoom).toBe(17.3)

    const exact = fakeMap(FOCUS_ZOOM)
    focusCamera(exact.map, [18.6, 54.38], WIDE)
    expect(exact.flyTo.mock.calls[0][0].zoom).toBe(FOCUS_ZOOM)

    const far = fakeMap(FOCUS_ZOOM - 0.01)
    focusCamera(far.map, [18.6, 54.38], WIDE)
    expect(far.flyTo.mock.calls[0][0].zoom).toBe(FOCUS_ZOOM)
  })

  it('shows the target above the centre on a phone, so the bottom panel does not cover it', () => {
    const { map, flyTo } = fakeMap(12, 800)

    focusCamera(map, [18.6, 54.38], { reducedMotion: false, narrow: true })

    expect(NARROW_OFFSET_FRACTION).toBeLessThan(0)
    expect(flyTo.mock.calls[0][0].offset).toEqual([0, -200]) // a quarter of 800 px
  })

  it('uses no offset on a wide screen, where the side panels flank the map evenly', () => {
    const { map, flyTo } = fakeMap(12, 800)

    focusCamera(map, [18.6, 54.38], WIDE)

    expect(flyTo.mock.calls[0][0].offset).toEqual([0, 0])
  })

  it('does not produce a negative zero offset for a map with no height yet', () => {
    const { map, flyTo } = fakeMap(12, 0)

    focusCamera(map, [18.6, 54.38], { reducedMotion: false, narrow: true })

    const offset = flyTo.mock.calls[0][0].offset
    expect(Object.is(offset[1], 0)).toBe(true)
  })

  it('moves immediately, and not as an animation, with reduced motion', () => {
    const { map, flyTo } = fakeMap(11)

    focusCamera(map, [18.6, 54.38], { reducedMotion: true, narrow: false })

    expect(flyTo.mock.calls[0][0]).toMatchObject({ duration: 0, essential: true })
  })
})

describe('isNarrowViewport', () => {
  it('is narrow below the sm breakpoint and wide from it', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query !== '(min-width: 640px)' }))
    expect(isNarrowViewport()).toBe(true)

    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(min-width: 640px)' }))
    expect(isNarrowViewport()).toBe(false)
  })

  it('treats an environment without matchMedia as wide', () => {
    vi.stubGlobal('matchMedia', undefined)

    expect(isNarrowViewport()).toBe(false)
  })
})
