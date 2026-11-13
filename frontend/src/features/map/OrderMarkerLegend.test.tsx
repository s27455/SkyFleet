import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { OrderMarkerLegend } from './OrderMarkerLegend'

describe('OrderMarkerLegend', () => {
  it('names each delivery state in words, not only colour', () => {
    render(<OrderMarkerLegend />)

    const legend = screen.getByRole('region', { name: 'Delivery marker legend' })
    expect(
      within(legend)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['Waiting', 'In delivery', 'Delivered', 'Cancelled'])
  })

  it('can be hidden on narrow screens only', () => {
    render(<OrderMarkerLegend hideOnNarrow />)

    expect(
      screen.getByRole('region', { name: 'Delivery marker legend', hidden: true }),
    ).toHaveClass('hidden', 'sm:block')
  })
})
