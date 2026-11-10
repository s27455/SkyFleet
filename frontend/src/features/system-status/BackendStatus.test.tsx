import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BackendStatus } from './BackendStatus'

describe('BackendStatus', () => {
  it('shows a connecting state while the first check is pending', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )

    render(<BackendStatus />)

    expect(screen.getByRole('status')).toHaveTextContent('Connecting to backend')
  })

  it('shows connected when the health endpoint responds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ status: 'ok' })))),
    )

    render(<BackendStatus />)

    expect(await screen.findByText('Backend connected')).toBeInTheDocument()
  })

  it('shows unreachable when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )

    render(<BackendStatus />)

    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })

  it('shows unreachable when the backend returns an error status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('', { status: 503 }))),
    )

    render(<BackendStatus />)

    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })
})
