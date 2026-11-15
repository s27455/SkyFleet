import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { acknowledgeEmergency } from '../../api/acknowledgements'
import { ApiError } from '../../api/client'
import type { Flight, FlightsSnapshot } from '../../types/flight'
import type { Mission } from '../../types/mission'
import type { PolledResource } from '../data/usePolledResource'
import { LiveDataNotices, MAX_EMERGENCY_ALERTS } from './LiveDataNotices'

vi.mock('../../api/acknowledgements', () => ({ acknowledgeEmergency: vi.fn() }))
const acknowledge = vi.mocked(acknowledgeEmergency)

const baseFlight: Flight = {
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  purpose: 'DELIVERY',
  droneId: 'DRN-1',
  missionStatus: 'EMERGENCY',
  phase: 'EMERGENCY',
  progress: 1,
  position: [18.6012, 54.3821],
  batteryPct: 12,
  target: null,
  originHubId: 'hub-a',
  plannedReturnHubId: 'hub-a',
  landingTargetHubId: 'hub-a',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: null,
  recalledAt: null,
  failedAt: '2026-11-12T10:00:05Z',
  recipientUnavailableAt: null,
  handoverFailedAt: null,
  yieldingToLpr: false,
  updatedAt: '2026-11-12T10:00:09Z',
  snapshotAgeS: 0,
  emergency: {
    reason: 'DRONE_FAILURE',
    at: '2026-11-12T10:00:09Z',
    position: [18.6012, 54.3821],
    acknowledgedAt: null,
  },
}

const emergency = (n: number, acknowledgedAt: string | null = null): Flight => ({
  ...baseFlight,
  missionId: `MIS-${n}`,
  droneId: `DRN-${n}`,
  emergency: { ...baseFlight.emergency!, acknowledgedAt },
})

function flightsResource(
  flights: Flight[],
  extra: Partial<PolledResource<FlightsSnapshot>> = {},
): PolledResource<FlightsSnapshot> {
  return {
    state: {
      status: 'ready',
      data: {
        serverTime: '2026-11-12T10:00:10Z',
        workerHeartbeatAt: '2026-11-12T10:00:09Z',
        workerStale: false,
        flights,
      },
    },
    stale: false,
    receivedAt: 0,
    retry: vi.fn(),
    refresh: vi.fn(),
    ...extra,
  }
}

const missions: PolledResource<Mission[]> = {
  state: { status: 'ready', data: [] },
  stale: false,
  receivedAt: null,
  retry: vi.fn(),
  refresh: vi.fn(),
}

const OK = (id: string) => ({ missionId: id, acknowledgedAt: '2026-11-12T10:05:00Z' })

/** A promise settled by the test, to observe the pending state of a request. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const ackButton = (drone: string) =>
  screen.getByRole('button', { name: `Acknowledge emergency for ${drone}` })

beforeEach(() => {
  acknowledge.mockReset()
})
afterEach(() => vi.unstubAllGlobals())

describe('LiveDataNotices acknowledgement', () => {
  it('gives every emergency alert its own accessible Acknowledge button', () => {
    render(
      <LiveDataNotices
        flights={flightsResource([emergency(1), emergency(2)])}
        missions={missions}
      />,
    )

    expect(ackButton('DRN-1')).toBeEnabled()
    expect(ackButton('DRN-2')).toBeEnabled()
    expect(ackButton('DRN-1').tagName).toBe('BUTTON') // keyboard operable by default
    // an icon on a phone, the word from the small breakpoint up: the name is always on the button
    const text = within(ackButton('DRN-1')).getByText('Acknowledge')
    expect(text).toHaveClass('hidden', 'sm:inline')
  })

  it('hides the alert only after the server confirmed, and refreshes the flights', async () => {
    const pending = deferred<ReturnType<typeof OK>>()
    acknowledge.mockReturnValue(pending.promise)
    const resource = flightsResource([emergency(1), emergency(2)])
    render(<LiveDataNotices flights={resource} missions={missions} />)

    fireEvent.click(ackButton('DRN-1'))

    expect(acknowledge).toHaveBeenCalledWith('MIS-1')
    // not confirmed yet: still visible, busy and disabled
    expect(screen.getByText(/DRN-1 \(MIS-1\)/)).toBeInTheDocument()
    const busy = screen.getByRole('button', { name: 'Acknowledging emergency for DRN-1' })
    expect(busy).toBeDisabled()
    expect(busy).toHaveAttribute('aria-busy', 'true')

    await act(async () => pending.resolve(OK('MIS-1')))

    expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument()
    expect(screen.getByText(/DRN-2 \(MIS-2\)/)).toBeInTheDocument() // only that one alert
    expect(resource.refresh).toHaveBeenCalledOnce()
  })

  it('sends one request however often the button is pressed while it is pending', async () => {
    const pending = deferred<ReturnType<typeof OK>>()
    acknowledge.mockReturnValue(pending.promise)
    render(<LiveDataNotices flights={flightsResource([emergency(1)])} missions={missions} />)

    const button = ackButton('DRN-1')
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledging emergency for DRN-1' }))
    await act(async () => pending.resolve(OK('MIS-1')))

    expect(acknowledge).toHaveBeenCalledTimes(1)
  })

  it('keeps the alert and shows a recoverable error when the request fails', async () => {
    acknowledge.mockRejectedValueOnce(
      new ApiError('HTTP 500', 500, { message: 'Internal problem.' }),
    )
    const resource = flightsResource([emergency(1)])
    render(<LiveDataNotices flights={resource} missions={missions} />)

    fireEvent.click(ackButton('DRN-1'))

    const alerts = await screen.findAllByRole('alert')
    expect(
      alerts.some((a) =>
        /Could not acknowledge this alert: Internal problem\./.test(a.textContent ?? ''),
      ),
    ).toBe(true)
    expect(screen.getByText(/DRN-1 \(MIS-1\)/)).toBeInTheDocument() // never hidden on failure
    expect(ackButton('DRN-1')).toBeEnabled() // and it can be tried again
    expect(resource.refresh).not.toHaveBeenCalled()

    acknowledge.mockResolvedValueOnce(OK('MIS-1'))
    fireEvent.click(ackButton('DRN-1'))

    await waitFor(() => expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument())
    expect(screen.queryByText(/Could not acknowledge/)).not.toBeInTheDocument()
  })

  it('does not bring an acknowledged alert back when an older flights answer arrives', async () => {
    acknowledge.mockResolvedValue(OK('MIS-1'))
    const stale = flightsResource([emergency(1), emergency(2)]) // requested before the confirmation
    const { rerender } = render(<LiveDataNotices flights={stale} missions={missions} />)

    fireEvent.click(ackButton('DRN-1'))
    await waitFor(() => expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument())

    // the stale answer still says "not acknowledged"; later polls repeat it
    rerender(
      <LiveDataNotices
        flights={flightsResource([emergency(1), emergency(2)])}
        missions={missions}
      />,
    )
    rerender(
      <LiveDataNotices
        flights={flightsResource([emergency(1), emergency(2)])}
        missions={missions}
      />,
    )

    expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument()
    expect(screen.getByText(/DRN-2 \(MIS-2\)/)).toBeInTheDocument()
  })

  it('shows no alert the server already reports as acknowledged, as after a page reload', () => {
    render(
      <LiveDataNotices
        flights={flightsResource([emergency(1, '2026-11-12T10:05:00Z'), emergency(2)])}
        missions={missions}
      />,
    )

    expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument()
    expect(screen.getByText(/DRN-2 \(MIS-2\)/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Acknowledge emergency for DRN-1/ })).toBeNull()
  })

  it('counts only the alerts that are not acknowledged', () => {
    const many = Array.from({ length: MAX_EMERGENCY_ALERTS + 2 }, (_, i) =>
      emergency(i + 1, i === 0 ? '2026-11-12T10:05:00Z' : null),
    )

    render(<LiveDataNotices flights={flightsResource(many)} missions={missions} />)

    // 5 emergencies, 1 acknowledged: 4 open = 3 rows + 1 more
    expect(screen.getByText(/1 more simulated emergencies/)).toBeInTheDocument()
    expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument()
    expect(screen.getByText(/DRN-2 \(MIS-2\)/)).toBeInTheDocument()
  })

  it('brings the next hidden alert up once one is acknowledged', async () => {
    acknowledge.mockResolvedValue(OK('MIS-1'))
    const many = Array.from({ length: MAX_EMERGENCY_ALERTS + 1 }, (_, i) => emergency(i + 1))
    render(<LiveDataNotices flights={flightsResource(many)} missions={missions} />)
    expect(screen.queryByText(/DRN-4 \(MIS-4\)/)).not.toBeInTheDocument()

    fireEvent.click(ackButton('DRN-1'))

    expect(await screen.findByText(/DRN-4 \(MIS-4\)/)).toBeInTheDocument()
    expect(screen.queryByText(/more simulated emergencies/)).not.toBeInTheDocument()
  })

  it('leaves the other alerts and the details toggles alone', async () => {
    acknowledge.mockResolvedValue(OK('MIS-1'))
    render(
      <LiveDataNotices
        flights={flightsResource([emergency(1), emergency(2)])}
        missions={missions}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Show details for DRN-2' }))

    fireEvent.click(ackButton('DRN-1'))

    await waitFor(() => expect(screen.queryByText(/DRN-1 \(MIS-1\)/)).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Hide details for DRN-2' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('does not disturb the other notices', () => {
    const resource = flightsResource([emergency(1)], { stale: true })
    render(
      <LiveDataNotices
        flights={resource}
        missions={missions}
        fleetStale
        onRefreshFleet={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Refresh flights' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh fleet data' })).toBeInTheDocument()
    expect(ackButton('DRN-1')).toBeEnabled()
  })
})
