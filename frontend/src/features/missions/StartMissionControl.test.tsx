import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StartMissionError } from '../../api/missions'
import type { Mission } from '../../types/mission'
import { StartMissionControl } from './StartMissionControl'

const MISSION: Mission = {
  id: 'MIS-AAAA0001',
  orderId: 'ORD-001',
  droneId: 'DRN-010',
  originHubId: 'hub-a',
  returnHubId: 'hub-a',
  status: 'ASSIGNED',
  totalKm: 1.372,
}

const button = () => screen.getByRole('button', { name: 'Start mission MIS-AAAA0001' })

function deferred() {
  let resolve!: () => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('StartMissionControl', () => {
  it('describes the mission and says its return Hub is planned, not reserved', () => {
    render(
      <StartMissionControl mission={MISSION} returnHubName="Galeria Bałtycka" onStart={vi.fn()} />,
    )

    const region = screen.getByRole('region', { name: 'Mission MIS-AAAA0001' })
    expect(region).toHaveTextContent('1.4 km planned')
    expect(region).toHaveTextContent('returns to Galeria Bałtycka')
    expect(region).toHaveTextContent('planned, not reserved')
    expect(region).toHaveTextContent('temporary demonstration')
  })

  it('falls back to the Hub id when the name is not known', () => {
    render(<StartMissionControl mission={MISSION} onStart={vi.fn()} />)

    expect(screen.getByRole('region')).toHaveTextContent('returns to hub-a')
  })

  it('starts the mission once, whatever the number of clicks', async () => {
    const start = deferred()
    const onStart = vi.fn(() => start.promise)
    render(<StartMissionControl mission={MISSION} onStart={onStart} />)

    fireEvent.click(button())
    fireEvent.click(button()) // a double click: the button is already off
    fireEvent.click(button())

    expect(onStart).toHaveBeenCalledTimes(1)
    expect(onStart).toHaveBeenCalledWith('MIS-AAAA0001')
    expect(button()).toBeDisabled()
    expect(button()).toHaveTextContent('Starting…')
    start.resolve()
    await waitFor(() => expect(button()).toHaveTextContent('Mission started'))
  })

  it('stays off after a successful start, so a slow refresh cannot invite a refused second click', async () => {
    const onStart = vi.fn(() => Promise.resolve())
    render(<StartMissionControl mission={MISSION} onStart={onStart} />)

    fireEvent.click(button())

    await waitFor(() => expect(button()).toHaveTextContent('Mission started'))
    expect(button()).toBeDisabled()
    fireEvent.click(button())
    expect(onStart).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    [
      'the worker is not running',
      new StartMissionError('WORKER_UNAVAILABLE', 'The simulation worker is not running.'),
    ],
    [
      'the mission can no longer start',
      new StartMissionError(
        'NOT_STARTABLE',
        'This mission can no longer be started (it is IN_FLIGHT).',
      ),
    ],
    ['the mission is gone', new StartMissionError('NOT_FOUND', 'This mission no longer exists.')],
    [
      'the backend is unreachable',
      new StartMissionError('UNREACHABLE', 'The backend is unreachable, so nothing was started.'),
    ],
  ])('shows why the start was refused when %s, and can be tried again', async (_name, error) => {
    const onStart = vi.fn(() => Promise.reject(error))
    render(<StartMissionControl mission={MISSION} onStart={onStart} />)

    fireEvent.click(button())

    expect(await screen.findByRole('alert')).toHaveTextContent(error.message)
    expect(button()).toBeEnabled()
    expect(button()).toHaveTextContent('Start mission')
  })

  it('lists the reasons the backend gave', async () => {
    const error = new StartMissionError('NOT_ELIGIBLE', 'No longer eligible:', [
      'Battery is 10%.',
      'Order is not ready.',
    ])
    render(<StartMissionControl mission={MISSION} onStart={() => Promise.reject(error)} />)

    fireEvent.click(button())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Battery is 10%.')
    expect(alert).toHaveTextContent('Order is not ready.')
  })

  it('shows a generic message for an unexpected failure', async () => {
    render(
      <StartMissionControl mission={MISSION} onStart={() => Promise.reject(new Error('boom'))} />,
    )

    fireEvent.click(button())

    expect(await screen.findByRole('alert')).toHaveTextContent('The mission could not be started.')
  })

  it('clears an old error when it is tried again', async () => {
    const onStart = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(new StartMissionError('UNKNOWN', 'First failure.'))
      .mockResolvedValue(undefined)
    render(<StartMissionControl mission={MISSION} onStart={onStart} />)

    fireEvent.click(button())
    expect(await screen.findByRole('alert')).toHaveTextContent('First failure.')
    fireEvent.click(button())

    await waitFor(() => expect(button()).toHaveTextContent('Mission started'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not touch its state when it was removed while the start was running', async () => {
    const start = deferred()
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = render(
      <StartMissionControl mission={MISSION} onStart={() => start.promise} />,
    )
    fireEvent.click(button())

    unmount()
    start.reject(new StartMissionError('UNKNOWN', 'late failure'))
    await Promise.resolve()
    await Promise.resolve()

    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })
})
