import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { POLL_INTERVALS_MS } from '../data/polling'
import { RandomIncidentsControl } from './RandomIncidentsControl'
import { useRandomIncidents } from './useRandomIncidents'

afterEach(() => vi.unstubAllGlobals())

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
  last_check_at: '2026-11-12T10:03:00Z',
  last_outcome: 'Triggered: LPR helicopter started',
}
const WORKER_DOWN = {
  detail: {
    code: 'SIMULATION_WORKER_UNAVAILABLE',
    message: 'The simulation worker is not running (no recent heartbeat); start it with `uv run`',
    last_heartbeat_at: null,
    max_age_seconds: 10,
  },
}

interface Options {
  enableResponse?: () => Promise<Response>
  disableResponse?: () => Promise<Response>
}

/** A server whose mode changes only when the backend is asked to change it. */
function stubServer(initial = OFF, options: Options = {}) {
  const server = { current: initial }
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url.replace(/^.*\/api/, '/api')}`)
      if (url.endsWith('/incidents/random/enable')) {
        const respond = options.enableResponse ?? (() => Promise.resolve(jsonResponse(ON)))
        return respond().then((response) => {
          if (response.ok) server.current = { ...ON }
          return response
        })
      }
      if (url.endsWith('/incidents/random/disable')) {
        const respond = options.disableResponse ?? (() => Promise.resolve(jsonResponse({ ...OFF })))
        return respond().then((response) => {
          if (response.ok) server.current = { ...server.current, enabled: false }
          return response
        })
      }
      return Promise.resolve(jsonResponse(server.current))
    }),
  )
  return { server, calls }
}

/** The one shared poll, as `App` provides it. */
function Harness() {
  const resource = useRandomIncidents()
  return <RandomIncidentsControl resource={resource} />
}

const toggle = () => screen.findByRole('switch', { name: 'Random incidents' })

describe('RandomIncidentsControl', () => {
  it('loads the state first, then shows the server state: OFF with no attempt', async () => {
    stubServer()
    render(<Harness />)

    expect(screen.getByRole('status')).toHaveTextContent('loading')
    const button = await toggle()
    expect(button).toHaveAttribute('aria-checked', 'false')
    expect(button).toBeEnabled()
    expect(screen.getByText('OFF')).toBeInTheDocument()
    expect(screen.getByText(/no incidents are triggered automatically/)).toBeInTheDocument()
    expect(screen.queryByText(/Last attempt/)).toBeNull()
  })

  it('shows ON with the last attempt time and outcome when the server is ON', async () => {
    stubServer(ON)
    render(<Harness />)

    expect(await toggle()).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('ON')).toBeInTheDocument()
    expect(screen.getByText(/Last attempt: Triggered: LPR helicopter started/)).toHaveTextContent(
      '12 Nov 2026',
    )
    expect(screen.getByText(/an attempt may be skipped/)).toBeInTheDocument()
  })

  it('says there was no attempt yet while ON, and does not promise an incident', async () => {
    stubServer({ ...ON, last_check_at: null, last_outcome: null })
    render(<Harness />)

    await toggle()

    expect(screen.getByText('No attempt yet.')).toBeInTheDocument()
  })

  it('shows a skipped attempt as it was reported', async () => {
    stubServer({ ...ON, last_outcome: 'Skipped: Drone failure: fleet guard' })
    render(<Harness />)

    await toggle()

    expect(
      screen.getByText(/Last attempt: Skipped: Drone failure: fleet guard/),
    ).toBeInTheDocument()
  })

  it('turns on only after the backend confirms, then shows the server state', async () => {
    const { calls } = stubServer()
    render(<Harness />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    expect(calls).toContain('POST /api/incidents/random/enable')
    expect(calls.filter((call) => call.startsWith('GET')).length).toBeGreaterThanOrEqual(2)
    expect(calls).not.toContain('POST /api/incidents/random/disable')
  })

  it('turns off again', async () => {
    const { calls } = stubServer(ON)
    render(<Harness />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'))
    expect(calls).toContain('POST /api/incidents/random/disable')
  })

  it('does not change the switch before the backend answers, and blocks the switch meanwhile', async () => {
    let release: (response: Response) => void = () => undefined
    const { calls } = stubServer(OFF, {
      enableResponse: () => new Promise<Response>((resolve) => (release = resolve)),
    })
    render(<Harness />)

    const button = await toggle()
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    expect(button).toHaveAttribute('aria-checked', 'false') // no optimistic ON
    expect(button).toBeDisabled()
    expect(screen.getByText('Working…')).toBeInTheDocument()
    expect(calls.filter((call) => call.includes('/random/enable'))).toHaveLength(1)

    release(jsonResponse(ON))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    expect(screen.getByRole('switch')).toBeEnabled()
    expect(screen.queryByText('Working…')).toBeNull()
  })

  it('explains a worker that went away (503) concisely and leaves the switch OFF and usable', async () => {
    stubServer(OFF, { enableResponse: () => Promise.resolve(jsonResponse(WORKER_DOWN, 503)) })
    render(<Harness />)

    fireEvent.click(await toggle())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The simulation worker is not running')
    expect(alert).toHaveTextContent('cannot be enabled')
    expect(alert).not.toHaveTextContent('uv run') // not the backend's long command text
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch')).toBeEnabled() // recoverable: try again later
  })

  it('cannot be enabled while the status says the worker is not running', async () => {
    const { calls } = stubServer({ ...OFF, worker_running: false })
    render(<Harness />)

    const button = await toggle()

    expect(button).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Simulation worker is not running')
    fireEvent.click(button)
    expect(calls.some((call) => call.startsWith('POST'))).toBe(false)
  })

  it('shows another API failure with the backend message and keeps the state', async () => {
    stubServer(OFF, {
      enableResponse: () =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'X', message: 'Could not save the mode' } }, 500),
        ),
    })
    render(<Harness />)

    fireEvent.click(await toggle())

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save the mode')
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('shows a network failure and keeps the state', async () => {
    stubServer(OFF, { enableResponse: () => Promise.reject(new TypeError('Failed to fetch')) })
    render(<Harness />)

    fireEvent.click(await toggle())

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('clears an earlier error when the operator tries again', async () => {
    let fail = true
    stubServer(OFF, {
      enableResponse: () =>
        fail
          ? Promise.resolve(jsonResponse({ detail: 'boom' }, 500))
          : Promise.resolve(jsonResponse(ON)),
    })
    render(<Harness />)

    fireEvent.click(await toggle())
    await screen.findByRole('alert')
    fail = false
    fireEvent.click(screen.getByRole('switch'))

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows an error with Retry when the status cannot be read, then recovers', async () => {
    let healthy = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(healthy ? jsonResponse(OFF) : jsonResponse({ detail: 'x' }, 500)),
      ),
    )
    render(<Harness />)

    const retry = await screen.findByRole('button', { name: 'Retry random incidents' })
    healthy = true
    fireEvent.click(retry)

    expect(await toggle()).toHaveAttribute('aria-checked', 'false')
  })

  it('rejects a malformed answer instead of guessing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ enabled: 'yes' }))),
    )
    render(<Harness />)

    expect(await screen.findByRole('button', { name: 'Retry random incidents' })).toBeVisible()
    expect(screen.queryByRole('switch')).toBeNull()
  })

  it('keeps the last status and says it may be out of date when a refresh fails', async () => {
    let statusWorks = true
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/random/enable')) return Promise.resolve(jsonResponse(ON))
        return Promise.resolve(statusWorks ? jsonResponse(OFF) : jsonResponse({}, 500))
      }),
    )
    render(<Harness />)
    await toggle()
    statusWorks = false

    fireEvent.click(screen.getByRole('switch')) // the answer is fine, the re-read afterwards fails

    expect(await screen.findByText('Status may be out of date')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false') // old data stays
  })

  it('follows the backend when it changes by itself (for example a worker restart)', async () => {
    const previous = POLL_INTERVALS_MS.fleet
    POLL_INTERVALS_MS.fleet = 20 // must be set before the hook mounts
    try {
      const { server } = stubServer(ON)
      render(<Harness />)
      expect(await toggle()).toHaveAttribute('aria-checked', 'true')

      server.current = { ...OFF, last_outcome: 'Reset to OFF when the simulation worker started' }

      await waitFor(() =>
        expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'),
      )
      expect(
        screen.getByText(/Reset to OFF when the simulation worker started/),
      ).toBeInTheDocument()
    } finally {
      POLL_INTERVALS_MS.fleet = previous
    }
  })

  it('has an accessible label and description for the switch', async () => {
    stubServer()
    render(<Harness />)

    const button = await toggle()

    expect(button).toHaveAccessibleName('Random incidents')
    expect(button).toHaveAccessibleDescription(/no incidents are triggered automatically/)
  })
})
