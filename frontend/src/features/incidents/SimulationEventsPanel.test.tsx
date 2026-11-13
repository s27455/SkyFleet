import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SimulationEventsPanel } from './SimulationEventsPanel'

afterEach(() => vi.unstubAllGlobals())

describe('SimulationEventsPanel', () => {
  it('shows the four scenarios as named, disabled controls with their future feature', () => {
    render(<SimulationEventsPanel />)

    const expected: [string, string][] = [
      ['Cancel order', '018B'],
      ['Drone failure', '018C'],
      ['Recipient unavailable', '018D'],
      ['LPR transit', '018E'],
    ]
    for (const [label, feature] of expected) {
      const button = screen.getByRole('button', { name: new RegExp(label) })
      expect(button).toBeDisabled()
      expect(button).toHaveTextContent(`Coming in ${feature}`)
    }
  })

  it('shows Random incidents off, disabled and honestly explained', () => {
    render(<SimulationEventsPanel />)

    const toggle = screen.getByRole('switch', { name: 'Random incidents' })
    expect(toggle).toBeDisabled()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Available when incident scenarios are enabled.')).toBeInTheDocument()
  })

  it('never calls the backend', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<SimulationEventsPanel />)

    expect(fetchMock).not.toHaveBeenCalled()
  })
})
