import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FOCUS_NOTICE_MS, FocusNotice } from './FocusNotice'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('FocusNotice', () => {
  it('shows nothing without a notice', () => {
    const { container } = render(<FocusNotice notice={null} onDismiss={() => {}} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('announces the message politely and can be dismissed by button', () => {
    const onDismiss = vi.fn()
    render(
      <FocusNotice
        notice={{ seq: 1, text: 'The location of DRN-1 is not available.' }}
        onDismiss={onDismiss}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('The location of DRN-1 is not available.')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss location message' }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('goes away by itself after a few seconds', () => {
    const onDismiss = vi.fn()
    render(<FocusNotice notice={{ seq: 1, text: 'x' }} onDismiss={onDismiss} />)

    act(() => vi.advanceTimersByTime(FOCUS_NOTICE_MS - 1))
    expect(onDismiss).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('starts a new timer for a new notice, even with the same text', () => {
    const onDismiss = vi.fn()
    const { rerender } = render(
      <FocusNotice notice={{ seq: 1, text: 'same' }} onDismiss={onDismiss} />,
    )

    act(() => vi.advanceTimersByTime(FOCUS_NOTICE_MS - 1000))
    rerender(<FocusNotice notice={{ seq: 2, text: 'same' }} onDismiss={onDismiss} />)
    act(() => vi.advanceTimersByTime(FOCUS_NOTICE_MS - 1000))
    expect(onDismiss).not.toHaveBeenCalled() // the first timer was replaced
    act(() => vi.advanceTimersByTime(1000))
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
