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
    annotations,
    selectedPart,
  }: {
    running: boolean
    wheelZoom: boolean
    apiRef: { current: unknown }
    onPartSelect?: (part: string | null) => void
    annotations?: Record<string, { label: string; level: string }>
    selectedPart?: string | null
  }) => {
    if (canvasState.throwOnRender) throw new Error('boom')
    apiRef.current = { orbit: vi.fn(), zoom: vi.fn(), reset: vi.fn() }
    return (
      <button
        type="button"
        data-testid="canvas"
        data-running={running}
        data-wheel={wheelZoom}
        data-selected={selectedPart ?? ''}
        data-annotations={JSON.stringify(annotations ?? null)}
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

  it('passes the annotations and the selection on to the scene', async () => {
    stubWebGL(true)
    const annotations = { battery: { label: 'Battery', level: 'critical' as const } }
    render(<Drone3DViewer annotations={annotations} selectedPart="battery" />)

    const canvas = await screen.findByTestId('canvas')
    expect(canvas).toHaveAttribute('data-selected', 'battery')
    expect(JSON.parse(canvas.getAttribute('data-annotations')!)).toEqual(annotations)
  })

  it('says what a click does only when parts can be selected', async () => {
    stubWebGL(true)
    const { unmount } = render(<Drone3DViewer onPartSelect={() => {}} />)
    await screen.findByTestId('canvas')
    expect(screen.getByText(/click a part to inspect it/)).toBeInTheDocument()
    unmount()

    render(<Drone3DViewer />)
    await screen.findByTestId('canvas')
    expect(screen.queryByText(/click a part to inspect it/)).not.toBeInTheDocument()
  })

  describe('part labels', () => {
    const ANNOTATIONS = {
      'motor-fl': { label: 'M1', level: 'nominal' as const },
      'motor-fr': { label: 'M2', level: 'attention' as const },
      'motor-rr': { label: 'M3', level: 'nominal' as const },
      'motor-rl': { label: 'M4', level: 'critical' as const },
      battery: { label: 'Battery', level: 'nominal' as const },
    }

    it('has no labels without annotations', async () => {
      stubWebGL(true)
      render(<Drone3DViewer onPartSelect={() => {}} />)
      await screen.findByTestId('canvas')

      expect(screen.queryByLabelText(/^(M\d|Battery),/)).not.toBeInTheDocument()
    })

    it('labels each part and states its level in words, in M1..M4 then battery order', async () => {
      stubWebGL(true)
      render(<Drone3DViewer annotations={ANNOTATIONS} onPartSelect={() => {}} />)
      await screen.findByTestId('canvas')

      const labels = screen.getAllByLabelText(/^(M\d|Battery),/)
      expect(labels.map((label) => label.getAttribute('aria-label'))).toEqual([
        'M1, Nominal',
        'M2, Attention',
        'M3, Nominal',
        'M4, Critical',
        'Battery, Nominal',
      ])
      // Colour is not the only cue: a non-nominal level is written next to the label.
      expect(screen.getByLabelText('M4, Critical')).toHaveTextContent('M4· Critical')
      expect(screen.getByLabelText('M3, Nominal')).toHaveTextContent(/^M3$/)
    })

    it('reports the part of a clicked label and shows which one is selected', async () => {
      stubWebGL(true)
      const onPartSelect = vi.fn()
      render(
        <Drone3DViewer
          annotations={ANNOTATIONS}
          selectedPart="motor-fr"
          onPartSelect={onPartSelect}
        />,
      )
      await screen.findByTestId('canvas')

      fireEvent.click(screen.getByLabelText('Battery, Nominal'))
      expect(onPartSelect).toHaveBeenCalledWith('battery')
      expect(screen.getByLabelText('M2, Attention')).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByLabelText('M1, Nominal')).toHaveAttribute('aria-pressed', 'false')
    })

    it('shows labels that cannot be pressed when nothing handles a selection', async () => {
      stubWebGL(true)
      render(<Drone3DViewer annotations={ANNOTATIONS} />)
      await screen.findByTestId('canvas')

      expect(screen.getByLabelText('M1, Nominal')).toBeDisabled()
    })

    it('has no labels in the WebGL fallback: the list is the way to select', () => {
      stubWebGL(false)
      render(<Drone3DViewer annotations={ANNOTATIONS} onPartSelect={() => {}} />)

      expect(screen.getByText('3D view unavailable')).toBeInTheDocument()
      expect(screen.queryByLabelText(/^(M\d|Battery),/)).not.toBeInTheDocument()
    })
  })
})
