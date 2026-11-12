import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { REQUEST_TIMEOUT_MS } from './polling'
import { usePolledResource } from './usePolledResource'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const advance = (ms: number) => act(async () => vi.advanceTimersByTimeAsync(ms))
const flush = () => act(async () => vi.advanceTimersByTimeAsync(0))

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('usePolledResource', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    setVisibility('visible')
    vi.useRealTimers()
  })

  it('starts loading and becomes ready, and reads only once when polling is off', async () => {
    const load = vi.fn(() => Promise.resolve(['a']))

    const { result } = renderHook(() => usePolledResource(load, null))
    expect(result.current.state).toEqual({ status: 'loading' })
    await flush()
    await advance(60_000)

    expect(result.current.state).toEqual({ status: 'ready', data: ['a'] })
    expect(result.current.stale).toBe(false)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('reads again after every interval', async () => {
    let n = 0
    const load = vi.fn(() => Promise.resolve([++n]))

    const { result } = renderHook(() => usePolledResource(load, 1000))
    await flush()
    expect(result.current.state).toEqual({ status: 'ready', data: [1] })

    await advance(1000)
    expect(result.current.state).toEqual({ status: 'ready', data: [2] })
    await advance(1000)
    expect(result.current.state).toEqual({ status: 'ready', data: [3] })
    expect(load).toHaveBeenCalledTimes(3)
  })

  it('never overlaps requests: the next one starts an interval after the previous finished', async () => {
    const pending = [deferred<number[]>(), deferred<number[]>()]
    let calls = 0
    const load = vi.fn(() => pending[calls++].promise)

    renderHook(() => usePolledResource(load, 1000))
    await flush()
    await advance(5000) // a slow request is still running: nothing else is started
    expect(load).toHaveBeenCalledTimes(1)

    await act(async () => pending[0].resolve([1]))
    await advance(999)
    expect(load).toHaveBeenCalledTimes(1)
    await advance(1)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('keeps the last good data and flags it stale when a refresh fails, then recovers', async () => {
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockResolvedValueOnce(['ok'])
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue(['back'])

    const { result } = renderHook(() => usePolledResource(load, 1000))
    await flush()
    await advance(1000)

    expect(result.current.state).toEqual({ status: 'ready', data: ['ok'] }) // never blanked
    expect(result.current.stale).toBe(true)

    await advance(1000)
    expect(result.current.state).toEqual({ status: 'ready', data: ['back'] })
    expect(result.current.stale).toBe(false)
  })

  it('reports an error when the first read fails, and recovers on its own', async () => {
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue(['up'])

    const { result } = renderHook(() => usePolledResource(load, 1000))
    await flush()
    expect(result.current.state).toEqual({ status: 'error' })

    await advance(1000)
    expect(result.current.state).toEqual({ status: 'ready', data: ['up'] })
  })

  it('keeps the same data object when nothing changed, but still records the receipt time', async () => {
    const load = vi.fn(() => Promise.resolve({ drones: [1, 2] }))

    const { result } = renderHook(() => usePolledResource(load, 1000, { trackReceivedAt: true }))
    await flush()
    const first = result.current.state
    const firstReceivedAt = result.current.receivedAt
    expect(firstReceivedAt).not.toBeNull()

    await advance(1000)

    expect(result.current.state).toBe(first) // identical identity: consumers do not rebuild
    expect(result.current.receivedAt).toBeGreaterThan(firstReceivedAt as number)
  })

  it('does not request anything while the tab is hidden, and reads at once when it returns', async () => {
    const load = vi.fn(() => Promise.resolve(['x']))
    renderHook(() => usePolledResource(load, 1000))
    await flush()
    expect(load).toHaveBeenCalledTimes(1)

    setVisibility('hidden')
    await advance(10_000)
    expect(load).toHaveBeenCalledTimes(1)

    setVisibility('visible')
    await flush()
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('refresh reads again right away without showing a loading state', async () => {
    let n = 0
    const load = vi.fn(() => Promise.resolve([++n]))
    const { result } = renderHook(() => usePolledResource(load, 10_000))
    await flush()

    act(() => result.current.refresh())
    expect(result.current.state).toEqual({ status: 'ready', data: [1] }) // still the old data
    await flush()

    expect(result.current.state).toEqual({ status: 'ready', data: [2] })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('retry starts over with a loading state', async () => {
    const load = vi.fn(() => Promise.resolve(['x']))
    const { result } = renderHook(() => usePolledResource(load, null))
    await flush()

    act(() => result.current.retry())
    expect(result.current.state).toEqual({ status: 'loading' })
    await flush()

    expect(result.current.state).toEqual({ status: 'ready', data: ['x'] })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('aborts the request and stops polling on unmount', async () => {
    let signal: AbortSignal | undefined
    const load = vi.fn((s: AbortSignal) => {
      signal = s
      return new Promise<string[]>(() => {})
    })

    const { unmount } = renderHook(() => usePolledResource(load, 1000))
    unmount()
    await advance(10_000)

    expect(signal?.aborted).toBe(true)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('ignores a late answer after unmount', async () => {
    const slow = deferred<string[]>()
    const load = vi.fn(() => slow.promise)
    const { result, unmount } = renderHook(() => usePolledResource(load, 1000))
    unmount()

    await act(async () => slow.resolve(['late']))

    expect(result.current.state).toEqual({ status: 'loading' })
  })
})

describe('usePolledResource while a read is running', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    REQUEST_TIMEOUT_MS.value = 10_000
    vi.useRealTimers()
  })

  it('queues one more read when a refresh arrives during a read, so the answer is fresh', async () => {
    const pending = [deferred<number[]>(), deferred<number[]>()]
    let calls = 0
    const load = vi.fn(() => pending[calls++].promise)
    const { result } = renderHook(() => usePolledResource(load, 10_000))
    await flush()
    expect(load).toHaveBeenCalledTimes(1)

    act(() => result.current.refresh()) // e.g. right after a mission start, while a poll runs
    act(() => result.current.refresh()) // a second request does not queue a third read
    expect(load).toHaveBeenCalledTimes(1) // never overlapping

    await act(async () => pending[0].resolve([1])) // the old read returns pre-action data
    await flush()
    expect(load).toHaveBeenCalledTimes(2) // and the follow-up starts immediately
    await act(async () => pending[1].resolve([2]))

    expect(result.current.state).toEqual({ status: 'ready', data: [2] })
    await advance(5000)
    expect(load).toHaveBeenCalledTimes(2) // the normal interval carries on from there
  })

  it('counts a read that never answers as a failure and keeps polling', async () => {
    REQUEST_TIMEOUT_MS.value = 3000
    const signals: AbortSignal[] = []
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string[]>>()
      .mockImplementationOnce(() => Promise.resolve(['ok']))
      .mockImplementationOnce((signal) => {
        signals.push(signal)
        return new Promise<string[]>(() => {}) // a stalled connection
      })
      .mockImplementation(() => Promise.resolve(['back']))

    const { result } = renderHook(() => usePolledResource(load, 1000))
    await flush()
    await advance(1000) // the second read starts and stalls
    expect(result.current.stale).toBe(false)

    await advance(3000) // the timeout
    expect(result.current.stale).toBe(true) // never silently frozen
    expect(result.current.state).toEqual({ status: 'ready', data: ['ok'] })
    expect(signals[0].aborted).toBe(true)

    await advance(1000)
    expect(result.current.state).toEqual({ status: 'ready', data: ['back'] })
    expect(result.current.stale).toBe(false)
  })

  it('reports an error when the very first read never answers', async () => {
    REQUEST_TIMEOUT_MS.value = 2000
    const load = vi.fn(() => new Promise<string[]>(() => {}))

    const { result } = renderHook(() => usePolledResource(load, null))
    await advance(2000)

    expect(result.current.state).toEqual({ status: 'error' })
  })

  it('starts over on retry even while a read is running', async () => {
    const pending = [deferred<string[]>(), deferred<string[]>()]
    let calls = 0
    const load = vi.fn((signal: AbortSignal) => {
      void signal
      return pending[calls++].promise
    })
    const { result } = renderHook(() => usePolledResource(load, null))
    await flush()

    act(() => result.current.retry())
    expect(result.current.state).toEqual({ status: 'loading' })
    await act(async () => pending[0].resolve(['stale answer'])) // the first read was abandoned
    expect(result.current.state).toEqual({ status: 'loading' })
    await act(async () => pending[1].resolve(['fresh']))

    expect(result.current.state).toEqual({ status: 'ready', data: ['fresh'] })
  })

  it('does not keep re-rendering for unchanged answers', async () => {
    let renders = 0
    const load = vi.fn(() => Promise.resolve({ same: true }))
    renderHook(() => {
      renders += 1
      return usePolledResource(load, 1000)
    })
    await flush()
    await advance(1000) // React may render once more before it bails out of an identical update
    const settled = renders

    await advance(5000)

    expect(load).toHaveBeenCalledTimes(7)
    expect(renders).toBe(settled) // six more unchanged answers caused no render at all
  })

  it('does not track the arrival time unless asked', async () => {
    const load = vi.fn(() => Promise.resolve(['x']))
    const { result } = renderHook(() => usePolledResource(load, null))
    await flush()

    expect(result.current.receivedAt).toBeNull()
  })
})
