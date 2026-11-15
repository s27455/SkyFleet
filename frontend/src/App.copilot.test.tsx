import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { stubBackend, dockedCount } from './test/appHarness'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

describe('App Copilot', () => {
  const COPILOT_TOKEN = 'app-test-token-' + 'x'.repeat(30)
  const pause = (ms = 30) => new Promise((done) => setTimeout(done, ms))

  async function renderApp() {
    const backend = stubBackend()
    render(<App />)
    await waitFor(() => expect(dockedCount('Centrum Riviera')).toBe('3'))
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))
    return backend
  }

  it('sends no Copilot request on page load, when the panel opens, or on any other tab', async () => {
    const { copilotStatusCalls, copilotAskCalls } = await renderApp()

    for (const name of [/^Drones/, /^Hubs/, /^Orders/, 'Events']) {
      fireEvent.click(screen.getByRole('tab', { name }))
    }
    await pause()

    expect(copilotStatusCalls).not.toHaveBeenCalled() // not even the availability probe
    expect(copilotAskCalls).not.toHaveBeenCalled()
  })

  it('offers the Copilot as the fifth tab and only probes availability when it is shown', async () => {
    const { copilotStatusCalls, copilotAskCalls } = await renderApp()
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      expect.stringMatching(/^Drones \(\d+\)$/),
      'Hubs (4)',
      expect.stringMatching(/^Orders/),
      'Events',
      'Copilot',
    ])

    fireEvent.click(screen.getByRole('tab', { name: 'Copilot' }))

    expect(await screen.findByLabelText('Access token')).toBeInTheDocument()
    expect(screen.getByText('Read-only AI Copilot — cannot control drones')).toBeInTheDocument()
    expect(copilotStatusCalls).toHaveBeenCalledTimes(1)
    expect(copilotAskCalls).not.toHaveBeenCalled()
  })

  it('keeps the conversation when a map selection switches the Operations tab', async () => {
    const { copilotStatusCalls, copilotAskCalls } = await renderApp()
    fireEvent.click(screen.getByRole('tab', { name: 'Copilot' }))
    fireEvent.change(await screen.findByLabelText('Access token'), {
      target: { value: COPILOT_TOKEN },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Use token' }))
    fireEvent.change(await screen.findByLabelText('Question'), {
      target: { value: 'Which drones need attention?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByTestId('copilot-answer')).toHaveTextContent(
      'Two drones are charging.',
    )

    // a click on the map selects a Hub, and the Operations panel follows the selection
    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Riviera' }))
    expect(screen.getByRole('tab', { name: /^Hubs/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByTestId('copilot-answer')).toBeNull() // the tab is not shown ...

    fireEvent.click(screen.getByRole('tab', { name: 'Copilot' }))

    // ... and everything is still there when it comes back, with nothing asked again
    expect(await screen.findByTestId('copilot-answer')).toHaveTextContent(
      'Two drones are charging.',
    )
    expect(screen.getByText(/Access token set/)).toBeInTheDocument()
    expect(copilotAskCalls).toHaveBeenCalledTimes(1)
    expect(copilotStatusCalls).toHaveBeenCalledTimes(1)
    expect(localStorage.length + sessionStorage.length).toBe(0)
  })
})
