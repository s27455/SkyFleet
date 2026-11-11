import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Hub } from '../../types/hub'
import { HubDetailPanel } from './HubDetailPanel'

const HUB: Hub = {
  id: 'hub-test',
  name: 'Test Mall',
  city: 'Gdynia',
  coordinates: [18.5, 54.5],
  status: 'operational',
  droneCapacity: 50,
}

describe('HubDetailPanel', () => {
  it('shows hub identity and the maximum drone capacity', () => {
    render(<HubDetailPanel hub={HUB} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: 'Test Mall' })).toBeInTheDocument()
    expect(screen.getByText('Gdynia')).toBeInTheDocument()
    expect(screen.getByText('Maximum drone capacity').nextElementSibling).toHaveTextContent('50')
  })

  it('labels the status as illustrative mock data and shows no occupancy', () => {
    render(<HubDetailPanel hub={HUB} onClose={() => {}} />)

    expect(screen.getByText(/Operational \(illustrative\)/)).toBeInTheDocument()
    expect(screen.getByText(/Mock data — not a live measurement/)).toBeInTheDocument()
    expect(screen.queryByText(/occupancy/i)).not.toBeInTheDocument()
  })

  it('closes via the close button', () => {
    const onClose = vi.fn()
    render(<HubDetailPanel hub={HUB} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close hub details' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes on Escape', () => {
    const onClose = vi.fn()
    render(<HubDetailPanel hub={HUB} onClose={onClose} />)

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledOnce()
  })
})
