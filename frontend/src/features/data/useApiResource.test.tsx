import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useApiResource } from './useApiResource'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useApiResource', () => {
  it('starts loading and becomes ready with the loaded data', async () => {
    const load = vi.fn(() => Promise.resolve(['a']))

    const { result } = renderHook(() => useApiResource(load))

    expect(result.current.state).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.state).toEqual({ status: 'ready', data: ['a'] }))
  })

  it('reports an error and recovers on retry', async () => {
    const load = vi.fn<() => Promise<string[]>>().mockRejectedValueOnce(new Error('down'))
    load.mockResolvedValueOnce(['ok'])

    const { result } = renderHook(() => useApiResource(load))
    await waitFor(() => expect(result.current.state).toEqual({ status: 'error' }))

    act(() => result.current.retry())
    expect(result.current.state).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.state).toEqual({ status: 'ready', data: ['ok'] }))
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('aborts the previous request on retry and ignores its late result', async () => {
    const first = deferred<string[]>()
    const second = deferred<string[]>()
    const signals: AbortSignal[] = []
    const load = vi.fn((signal: AbortSignal) => {
      signals.push(signal)
      return signals.length === 1 ? first.promise : second.promise
    })

    const { result } = renderHook(() => useApiResource(load))
    act(() => result.current.retry())
    expect(signals[0].aborted).toBe(true)

    await act(async () => first.resolve(['stale']))
    expect(result.current.state).toEqual({ status: 'loading' })

    await act(async () => second.resolve(['fresh']))
    expect(result.current.state).toEqual({ status: 'ready', data: ['fresh'] })
  })

  it('ignores a late failure of an aborted request', async () => {
    const first = deferred<string[]>()
    const second = deferred<string[]>()
    let calls = 0
    const load = vi.fn(() => (++calls === 1 ? first.promise : second.promise))

    const { result } = renderHook(() => useApiResource(load))
    act(() => result.current.retry())
    await act(async () => first.reject(new Error('late')))

    expect(result.current.state).toEqual({ status: 'loading' })
    await act(async () => second.resolve(['fresh']))
    expect(result.current.state).toEqual({ status: 'ready', data: ['fresh'] })
  })

  it('aborts the request on unmount', () => {
    let signal: AbortSignal | undefined
    const load = vi.fn((s: AbortSignal) => {
      signal = s
      return new Promise<string[]>(() => {})
    })

    const { unmount } = renderHook(() => useApiResource(load))
    unmount()

    expect(signal?.aborted).toBe(true)
  })
})
