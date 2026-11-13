import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ManagementPanel } from './ManagementPanel'

const TABS = [
  { id: 'orders', label: 'Orders', content: <p>orders content</p> },
  { id: 'drones', label: 'Drones', content: <p>drones content</p> },
]

describe('ManagementPanel', () => {
  it('shows the first tab and switches between tabs', () => {
    render(<ManagementPanel tabs={TABS} onClose={vi.fn()} />)

    expect(screen.getByRole('tab', { name: 'Orders' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('orders content')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Drones' }))

    expect(screen.getByText('drones content')).toBeInTheDocument()
    expect(screen.queryByText('orders content')).not.toBeInTheDocument()
  })

  it('closes from the Close button', () => {
    const onClose = vi.fn()
    render(<ManagementPanel tabs={TABS} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape', () => {
    const onClose = vi.fn()
    render(<ManagementPanel tabs={TABS} onClose={onClose} />)

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
