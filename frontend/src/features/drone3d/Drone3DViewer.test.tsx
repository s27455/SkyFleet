import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Drone3DViewer } from './Drone3DViewer'

// jsdom has no WebGL, so the heavy canvas is replaced by a stand-in that exposes its props.
const canvasState = vi.hoisted(() => ({ throwOnRender: false }))
vi.mock('./DroneCanvas', () => ({
  default: ({
    running,
    wheelZoom,
    apiRef,
    onPartSelect,
  }: {
    running: boolean
    wheelZoom: boolean
    apiRef: { current: unknown }
    onPartSelect?: (part: string) => void
  }) => {
    if (canvasState.throwOnRender) throw new Error('boom')
    apiRef.current = { orbit: vi.fn(), zoom: vi.fn(), reset: vi.fn() }
    return (
      <button
        type="button"
        data-testid="canvas"
        data-running={running}
        data-wheel={wheelZoom}
        onClick={() => onPartSelect?.('battery')}
      >
        canvas
      </button>
    )
  },
}))

function stubWebGL(available: boolean) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((): unknown =>
    available ? { getExtension: () => null } : null) as never)
}

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('reduce'),
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

describe('Drone3DViewer', () => {
  beforeEach(() => {
    canvasState.throwOnRender = false
    stubReducedMotion(false)
  })
  afterEach(() => vi.restoreAllMocks())

  it('shows a readable fallback when WebGL is unavailable', () => {
    stubWebGL(false)
    render(<Drone3DViewer />)
    expect(screen.getByText('3D view unavailable')).toBeInTheDocument()
    expect(screen.queryByTestId('canvas')).not.toBeInTheDocument()
  })

  it('loads the canvas lazily and animates by default', async () => {
    stubWebGL(true)
    render(<Drone3DViewer />)
    expect(await screen.findByTestId('canvas')).toHaveAttribute('data-running', 'true')
    expect(screen.getByRole('button', { name: 'Reset view' })).toBeInTheDocument()
  })

  it('does not animate when asked not to, or when the user prefers reduced motion', async () => {
    stubWebGL(true)
    const { unmount } = render(<Drone3DViewer animate={false} />)
    expect(await screen.findByTestId('canvas')).toHaveAttribute('data-running', 'false')
    unmount()

    stubReducedMotion(true)
    render(<Drone3DViewer animate />)
    expect(await screen.findByTestId('canvas')).toHaveAttribute('data-running', 'false')
  })

  it('enables wheel zoom only while focused', async () => {
    stubWebGL(true)
    render(<Drone3DViewer />)
    const canvas = await screen.findByTestId('canvas')
    const group = screen.getByRole('group')
    expect(canvas).toHaveAttribute('data-wheel', 'false')
    fireEvent.focus(group)
    await waitFor(() => expect(canvas).toHaveAttribute('data-wheel', 'true'))
    fireEvent.blur(group)
    await waitFor(() => expect(canvas).toHaveAttribute('data-wheel', 'false'))
  })

  it('handles keyboard controls on the viewer without swallowing other keys', async () => {
    stubWebGL(true)
    render(<Drone3DViewer />)
    await screen.findByTestId('canvas')
    const group = screen.getByRole('group')
    expect(fireEvent.keyDown(group, { key: 'ArrowLeft' })).toBe(false) // handled: default prevented
    expect(fireEvent.keyDown(group, { key: 'Tab' })).toBe(true) // ignored: focus can move on
  })

  it('falls back when the canvas fails to render', async () => {
    stubWebGL(true)
    canvasState.throwOnRender = true
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<Drone3DViewer />)
    expect(await screen.findByText('3D view unavailable')).toBeInTheDocument()
  })

  it('reports clicked parts', async () => {
    stubWebGL(true)
    const onPartSelect = vi.fn()
    render(<Drone3DViewer onPartSelect={onPartSelect} />)
    fireEvent.click(await screen.findByTestId('canvas'))
    expect(onPartSelect).toHaveBeenCalledWith('battery')
  })
})
