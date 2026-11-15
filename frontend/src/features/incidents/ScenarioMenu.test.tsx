import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import type { Order } from '../../types/order'
import type { RandomIncidentsStatus } from '../../types/randomIncidents'
import type { PolledResource } from '../data/usePolledResource'
import { ScenarioMenu } from './ScenarioMenu'

afterEach(() => vi.unstubAllGlobals())

const ORDER: Order = {
  id: 'ORD-001',
  originHubId: 'hub-galeria-baltycka',
  destinationAddress: 'ul. Grunwaldzka 82, Gdańsk',
  coordinates: [18.5972, 54.3768],
  packageWeightKg: 0.8,
  status: 'READY_FOR_PICKUP',
  deliveredAt: null,
  cancelledAt: null,
  deliveryFailedAt: null,
  createdAt: '2026-11-11T21:53:08Z',
  updatedAt: '2026-11-11T21:53:08Z',
}

const STATUS_ON = {
  enabled: true,
  worker_running: true,
  last_check_at: null,
  last_outcome: null,
}

function readyStatus(enabled: boolean): PolledResource<RandomIncidentsStatus> {
  return {
    state: {
      status: 'ready',
      data: { enabled, workerRunning: true, lastCheckAt: null, lastOutcome: null },
    },
    stale: false,
    receivedAt: null,
    retry: vi.fn(),
    refresh: vi.fn(),
  }
}

const trigger = () => screen.getByRole('button', { name: /Scenarios/ })
// A hidden element has no accessible name, so it is found by its label attribute.
const menu = () => document.querySelector('[aria-label="Scenarios menu"]') as HTMLElement

describe('ScenarioMenu', () => {
  it('is closed by default and opens and closes with its button', () => {
    render(<ScenarioMenu />)

    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(menu()).toHaveAttribute('hidden')
    expect(screen.queryByRole('button', { name: /LPR helicopter/ })).toBeNull()

    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: /LPR helicopter/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /Activate Rain Warning/ })).toBeVisible()

    fireEvent.click(trigger())
    expect(menu()).toHaveAttribute('hidden')
  })

  it('has a bounded, scrollable menu', () => {
    render(<ScenarioMenu />)

    expect(menu()).toHaveClass('overflow-y-auto')
    expect(menu().className).toMatch(/max-h-\[60dvh\]/)
  })

  it('closes on Escape and returns the focus to the button', () => {
    render(<ScenarioMenu />)
    fireEvent.click(trigger())

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(trigger()).toHaveFocus()
  })

  it('closes on an outside click but not on a click inside', () => {
    render(
      <div>
        <button type="button">outside</button>
        <ScenarioMenu />
      </div>,
    )
    fireEvent.click(trigger())

    fireEvent.pointerDown(screen.getByRole('button', { name: /LPR helicopter/ }))
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')

    fireEvent.pointerDown(screen.getByRole('button', { name: 'outside' }))
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not close on Escape or an outside click while a cancellation awaits confirmation', () => {
    render(
      <div>
        <button type="button">outside</button>
        <ScenarioMenu selectedOrder={ORDER} />
      </div>,
    )
    fireEvent.click(trigger())
    fireEvent.click(screen.getByRole('button', { name: /Cancel ORD-001/ }))
    expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toBeVisible()

    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.pointerDown(screen.getByRole('button', { name: 'outside' }))

    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toBeVisible()
  })

  it('keeps a pending confirmation when the button closes and reopens the menu', () => {
    render(<ScenarioMenu selectedOrder={ORDER} />)
    fireEvent.click(trigger())
    fireEvent.click(screen.getByRole('button', { name: /Cancel ORD-001/ }))

    fireEvent.click(trigger()) // close
    fireEvent.click(trigger()) // reopen

    expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toBeVisible()
  })

  it('can be dismissed again once the confirmation was kept or answered', () => {
    render(<ScenarioMenu selectedOrder={ORDER} />)
    fireEvent.click(trigger())
    fireEvent.click(screen.getByRole('button', { name: /Cancel ORD-001/ }))
    fireEvent.click(screen.getByRole('button', { name: /keep/i }))

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('still runs an existing scenario and shows its feedback inside the menu', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve(jsonResponse({}, 200)))
    vi.stubGlobal('fetch', fetchMock)
    const onRainWarningChanged = vi.fn()
    render(<ScenarioMenu onRainWarningChanged={onRainWarningChanged} />)
    fireEvent.click(trigger())

    fireEvent.click(screen.getByRole('button', { name: /Activate Rain Warning/ }))

    await waitFor(() => expect(onRainWarningChanged).toHaveBeenCalledTimes(1))
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/rain-warning\/activate$/)
  })

  it('shows the Random incidents switch inside the menu when the status is provided', () => {
    render(<ScenarioMenu randomIncidents={readyStatus(false)} />)

    expect(menu()).toContainElement(
      screen.getByRole('switch', { name: 'Random incidents', hidden: true }),
    )
    fireEvent.click(trigger())

    const toggle = screen.getByRole('switch', { name: 'Random incidents' })
    expect(toggle).toBeEnabled()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByText('Available when incident scenarios are enabled.')).toBeNull()
  })

  it('shows the switch as ON when the backend says so, and keeps the manual scenarios', () => {
    render(<ScenarioMenu randomIncidents={readyStatus(true)} />)
    fireEvent.click(trigger())

    expect(screen.getByRole('switch', { name: 'Random incidents' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('button', { name: /LPR helicopter/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Activate Rain Warning/ })).toBeEnabled()
  })

  it('toggles Random incidents through the API and keeps the menu open', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse({ ...STATUS_ON })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const resource = readyStatus(false)
    render(<ScenarioMenu randomIncidents={resource} />)
    fireEvent.click(trigger())

    fireEvent.click(screen.getByRole('switch', { name: 'Random incidents' }))

    await waitFor(() => expect(resource.refresh).toHaveBeenCalledTimes(1))
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/incidents\/random\/enable$/)
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    // The switch still follows the status it was given, not the click.
    expect(screen.getByRole('switch', { name: 'Random incidents' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('marks the button while a rain warning is active', () => {
    const { container, rerender } = render(<ScenarioMenu />)
    expect(container.querySelector('.bg-status-warning')).toBeNull()

    rerender(<ScenarioMenu rainWarningActive />)
    expect(container.querySelector('.bg-status-warning')).not.toBeNull()
  })
})
