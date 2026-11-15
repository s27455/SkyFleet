import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { ORDER_RESPONSES } from '../../test/orderFixtures'
import { OrderGenerationControl } from './OrderGenerationControl'
import { OrderSimulationPanel } from './OrderSimulationPanel'
import { useOrderSimulation } from './useOrderSimulation'

interface ServerStatus {
  enabled: boolean
  worker_running: boolean
  last_check_at: string | null
  last_outcome: string | null
  outstanding_orders: number
  max_outstanding_orders: number
}

const OFF: ServerStatus = {
  enabled: false,
  worker_running: true,
  last_check_at: null,
  last_outcome: null,
  outstanding_orders: 3,
  max_outstanding_orders: 20,
}
const ON: ServerStatus = {
  enabled: true,
  worker_running: true,
  last_check_at: '2026-11-12T10:00:00Z',
  last_outcome: 'Created ORD-1: ul. Długa 45, Gdańsk, 1.2 kg',
  outstanding_orders: 7,
  max_outstanding_orders: 20,
}

interface Options {
  enableResponse?: () => Promise<Response>
  generateResponse?: () => Promise<Response>
}

const created = (id: string) => jsonResponse({ ...ORDER_RESPONSES[0], id }, 201)

/** A server whose mode changes only when the backend is asked to change it. */
function stubServer(initial = OFF, options: Options = {}) {
  let current = initial
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url.replace(/^.*\/api/, '/api')}`)
      if (url.endsWith('/simulation/enable')) {
        const respond = options.enableResponse ?? (() => Promise.resolve(jsonResponse(ON)))
        return respond().then((response) => {
          if (response.ok) current = { ...ON } // a confirmed change is what the server now reports
          return response
        })
      }
      if (url.endsWith('/simulation/disable')) {
        current = { ...OFF }
        return Promise.resolve(jsonResponse(current))
      }
      if (url.endsWith('/orders/generate')) {
        const respond = options.generateResponse ?? (() => Promise.resolve(created('ORD-NEW00001')))
        return respond().then((response) => {
          if (response.ok) {
            current = { ...current, outstanding_orders: current.outstanding_orders + 1 }
          }
          return response
        })
      }
      return Promise.resolve(jsonResponse(current))
    }),
  )
  return calls
}

const toggle = () => screen.findByRole('switch', { name: 'Automatic orders' })

/** The header switch and the Management panel share one poll, as in the app. */
function Harness({ onGenerated }: { onGenerated: () => void }) {
  const resource = useOrderSimulation()
  return (
    <>
      <OrderGenerationControl resource={resource} />
      <OrderSimulationPanel resource={resource} onGenerated={onGenerated} />
    </>
  )
}
const generateButton = () => screen.getByRole('button', { name: /Generate One Order|Generating/ })
const noop = () => undefined

describe('OrderSimulationPanel', () => {
  it('shows what the server reports, OFF by default, with the backlog and no outcome yet', async () => {
    stubServer()
    render(<Harness onGenerated={noop} />)

    expect(screen.getByRole('status')).toHaveTextContent('loading')
    const button = await toggle()
    expect(button).toHaveAttribute('aria-checked', 'false')
    expect(button).toHaveTextContent('OFF')
    expect(screen.getByText('Available')).toBeInTheDocument()
    expect(screen.getByText('3 / 20')).toBeInTheDocument()
    expect(screen.getByText('No automatic orders yet.')).toBeInTheDocument()
  })

  it('shows ON with the last outcome when the server is already ON', async () => {
    stubServer(ON)
    render(<Harness onGenerated={noop} />)

    expect(await toggle()).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('7 / 20')).toBeInTheDocument()
    expect(screen.getByText(/Last automatic result: Created ORD-1/)).toBeInTheDocument()
  })

  it('turns on only after the backend confirms, then shows the server state', async () => {
    const calls = stubServer()
    render(<Harness onGenerated={noop} />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    expect(calls).toContain('POST /api/orders/simulation/enable')
    expect(calls.filter((call) => call.startsWith('GET')).length).toBeGreaterThanOrEqual(2)
  })

  it('turns off again', async () => {
    const calls = stubServer(ON)
    render(<Harness onGenerated={noop} />)

    fireEvent.click(await toggle())

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'))
    expect(calls).toContain('POST /api/orders/simulation/disable')
  })

  it('never touches Automatic Dispatch', async () => {
    const calls = stubServer()
    render(<Harness onGenerated={noop} />)

    fireEvent.click(await toggle())
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    fireEvent.click(generateButton())
    await screen.findByText('Created order ORD-NEW00001.')

    expect(calls.some((call) => call.includes('/dispatch'))).toBe(false)
  })

  it('does not claim ON when the worker is unavailable (503) and shows the backend message', async () => {
    stubServer(OFF, {
      enableResponse: () =>
        Promise.resolve(
          jsonResponse(
            {
              detail: {
                code: 'SIMULATION_WORKER_UNAVAILABLE',
                message: 'The simulation worker is not running; start it and try again',
              },
            },
            503,
          ),
        ),
    })
    render(<Harness onGenerated={noop} />)

    fireEvent.click(await toggle())

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The simulation worker is not running',
    )
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch')).not.toBeDisabled() // recoverable: try again later
  })

  it('ignores repeated clicks while a change is in flight', async () => {
    let release: (response: Response) => void = () => undefined
    const calls = stubServer(OFF, {
      enableResponse: () => new Promise<Response>((resolve) => (release = resolve)),
    })
    render(<Harness onGenerated={noop} />)

    const button = await toggle()
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    expect(calls.filter((call) => call.includes('/simulation/enable'))).toHaveLength(1)
    expect(button).toBeDisabled()
    release(jsonResponse(ON))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
  })

  it('warns and cannot enable while the worker is not running, but can still generate one order', async () => {
    const calls = stubServer({ ...OFF, worker_running: false })
    render(<Harness onGenerated={noop} />)

    const button = await toggle()

    expect(button).toBeDisabled()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Simulation worker is not running')
    fireEvent.click(generateButton())
    expect(await screen.findByText('Created order ORD-NEW00001.')).toBeInTheDocument()
    expect(calls).toContain('POST /api/orders/generate')
  })

  it('shows an error with Retry when the status cannot be read, then recovers', async () => {
    let healthy = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(healthy ? jsonResponse(OFF) : jsonResponse({ detail: 'x' }, 500)),
      ),
    )
    render(<Harness onGenerated={noop} />)

    const retry = await screen.findByRole('button', { name: 'Retry order simulation' })
    healthy = true
    fireEvent.click(retry)

    expect(await toggle()).toHaveAttribute('aria-checked', 'false')
  })

  it('keeps the last status and says it may be out of date when a refresh fails', async () => {
    let statusWorks = true
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/orders/generate')) return Promise.resolve(created('ORD-NEW00003'))
        return Promise.resolve(statusWorks ? jsonResponse(OFF) : jsonResponse({}, 500))
      }),
    )
    render(<Harness onGenerated={noop} />)
    await toggle()
    statusWorks = false

    fireEvent.click(generateButton()) // re-reads the status afterwards, which now fails

    expect(await screen.findByText('Status may be out of date')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false') // old data stays
  })

  describe('Generate One Order', () => {
    it('calls the backend exactly once, confirms it and tells the list to refresh', async () => {
      const calls = stubServer() // automatic generation is OFF
      const onGenerated = vi.fn()
      render(<Harness onGenerated={onGenerated} />)
      await toggle()

      fireEvent.click(generateButton())

      expect(await screen.findByText('Created order ORD-NEW00001.')).toBeInTheDocument()
      expect(calls.filter((call) => call === 'POST /api/orders/generate')).toHaveLength(1)
      expect(onGenerated).toHaveBeenCalledTimes(1)
      await waitFor(() => expect(screen.getByText('4 / 20')).toBeInTheDocument()) // status re-read
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false') // mode unchanged
    })

    it('ignores repeated clicks while the request is pending', async () => {
      let release: (response: Response) => void = () => undefined
      const calls = stubServer(OFF, {
        generateResponse: () => new Promise<Response>((resolve) => (release = resolve)),
      })
      render(<Harness onGenerated={noop} />)
      await toggle()

      fireEvent.click(generateButton())
      fireEvent.click(generateButton())
      fireEvent.click(generateButton())

      expect(calls.filter((call) => call === 'POST /api/orders/generate')).toHaveLength(1)
      expect(generateButton()).toBeDisabled()
      release(created('ORD-NEW00002'))
      expect(await screen.findByText('Created order ORD-NEW00002.')).toBeInTheDocument()
    })

    it('shows the failure and does not refresh the list', async () => {
      stubServer(OFF, {
        generateResponse: () => Promise.resolve(jsonResponse({ detail: 'database down' }, 500)),
      })
      const onGenerated = vi.fn()
      render(<Harness onGenerated={onGenerated} />)
      await toggle()

      fireEvent.click(generateButton())

      expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate an order')
      expect(onGenerated).not.toHaveBeenCalled()
      expect(screen.queryByText(/Created order/)).not.toBeInTheDocument()
      expect(generateButton()).not.toBeDisabled() // can try again
    })

    it('says the backlog limit applies to automatic generation only', async () => {
      stubServer()
      render(<Harness onGenerated={noop} />)
      await toggle()

      expect(screen.getByText(/pauses automatic generation only/)).toBeInTheDocument()
    })
  })
})
