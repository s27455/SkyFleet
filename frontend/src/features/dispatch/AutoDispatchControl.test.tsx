import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { AutoDispatchControl } from './AutoDispatchControl'

interface ServerStatus {
  enabled: boolean
  worker_running: boolean
  last_check_at: string | null
  last_outcome: string | null
}

const OFF: ServerStatus = {
  enabled: false,
  worker_running: true,
  last_check_at: null,
  last_outcome: null,
}
const ON: ServerStatus = {
  enabled: true,
  worker_running: true,
  last_check_at: '2026-11-12T10:00:00Z',
  last_outcome: 'Started 1 mission(s)',
}

/** A server whose mode changes only when the backend is asked to change it. */
function stubServer(initial = OFF, enableResponse?: () => Promise<Response>) {
  let current = initial
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url.replace(/^.*\/api/, '/api')}`)
      if (url.endsWith('/auto/enable')) {
        if (enableResponse) {
          return enableResponse().then((response) => {
            if (response.ok) current = { ...ON } // a confirmed change is what the server now reports
            return response
          })
        }
        current = { ...ON }
        return Promise.resolve(jsonResponse(current))
      }
      if (url.endsWith('/auto/disable')) {
        current = { ...OFF }
        return Promise.resolve(jsonResponse(current))
      }
      return Promise.resolve(jsonResponse(current))
    }),
  )
  return calls
}

const toggle = () => screen.findByRole('switch', { name: 'Auto dispatch' })

describe('AutoDispatchControl', () => {
  it('shows what the server reports, OFF by default', async () => {
    stubServer()
    render(<AutoDispatchControl />)

    expect(screen.getByRole('status')).toHaveTextContent('loading')
    const button = await toggle()
    expect(button).toHaveAttribute('aria-checked', 'false')
    expect(button).toHaveTextContent('OFF')
  })

  it('shows ON with the last outcome when the server is already ON', async () => {
    stubServer(ON)
    render(<AutoDispatchControl />)

    const button = await toggle()
    expect(button).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText(/Started 1 mission\(s\)/)).toBeInTheDocument()
  })

  it('turns on only after the backend confirms, then shows the server state', async () => {
    const calls = stubServer()
    render(<AutoDispatchControl />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    expect(calls).toContain('POST /api/dispatch/auto/enable')
    expect(calls.filter((call) => call.startsWith('GET')).length).toBeGreaterThanOrEqual(2)
  })

  it('turns off again', async () => {
    const calls = stubServer(ON)
    render(<AutoDispatchControl />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'))
    expect(calls).toContain('POST /api/dispatch/auto/disable')
  })

  it('does not claim ON when the backend refuses, and shows its message', async () => {
    stubServer(OFF, () =>
      Promise.resolve(
        jsonResponse(
          {
            detail: { code: 'SIMULATION_WORKER_UNAVAILABLE', message: 'The worker is not running' },
          },
          503,
        ),
      ),
    )
    render(<AutoDispatchControl />)

    fireEvent.click(await toggle())

    expect(await screen.findByRole('alert')).toHaveTextContent('The worker is not running')
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('ignores repeated clicks while a change is in flight', async () => {
    let release: (response: Response) => void = () => undefined
    const calls = stubServer(OFF, () => new Promise<Response>((resolve) => (release = resolve)))
    render(<AutoDispatchControl />)

    const button = await toggle()
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    expect(calls.filter((call) => call.includes('/auto/enable'))).toHaveLength(1)
    release(jsonResponse(ON))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
  })

  it('warns and cannot enable while the worker is not running', async () => {
    stubServer({ ...OFF, worker_running: false })
    render(<AutoDispatchControl />)

    const button = await toggle()

    expect(button).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Simulation worker is not running')
  })

  it('shows an error with Retry when the status cannot be read, then recovers', async () => {
    let healthy = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(healthy ? jsonResponse(OFF) : jsonResponse({ detail: 'x' }, 500)),
      ),
    )
    render(<AutoDispatchControl />)

    const retry = await screen.findByRole('button', { name: 'Retry auto dispatch' })
    healthy = true
    fireEvent.click(retry)

    expect(await toggle()).toHaveAttribute('aria-checked', 'false')
  })
})
