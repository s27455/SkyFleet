import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { okHubs, stubBackend, dockedCount, panels, okMixed } from './test/appHarness'
import { jsonResponse } from './test/hubFixtures'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

describe('App selection', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  async function renderMixed() {
    stubBackend(okHubs, okMixed)
    render(<App />)
    await screen.findByRole('button', { name: 'Drone marker DRN-002' })
    await screen.findAllByRole('button', { name: /^Marker / })
    await waitFor(() => expect(dockedCount('Centrum Riviera')).toBe('2'))
  }

  it("lists a Hub's docked drones and opens a drone from the list", async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(dockedCount('Centrum Riviera')).toBe('3'))

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Riviera' }))
    const hubPanel = screen.getByRole('complementary', { name: 'Hub details: Centrum Riviera' })
    expect(within(hubPanel).getByText('Drones at this Hub (3)')).toBeInTheDocument()
    expect(
      within(hubPanel)
        .getAllByRole('button', { name: /DRN-/ })
        .map((b) => b.textContent),
    ).toEqual(['DRN-004Idle · 100%', 'DRN-005Idle · 90%', 'DRN-006Idle · 80%'])

    fireEvent.click(within(hubPanel).getByRole('button', { name: /DRN-005/ }))

    expect(panels()).toHaveLength(1)
    const panel = screen.getByRole('complementary', { name: 'Drone details: DRN-005' })
    expect(within(panel).getByText('Hub').nextElementSibling).toHaveTextContent('Centrum Riviera')
    expect(within(panel).getByText('Battery').nextElementSibling).toHaveTextContent('90%')
    expect(within(panel).getByText('Status').nextElementSibling).toHaveTextContent('Idle')
    expect(within(panel).getByText('Maximum payload').nextElementSibling).toHaveTextContent('3 kg')
    expect(within(panel).getByText('SkyFleet SF-1 Courier')).toBeInTheDocument()
  })

  it('lists a drone under the Hub where it physically is, not its home Hub', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Handlowe Osowa' }))
    const osowa = screen.getByRole('complementary', { name: 'Hub details: Centrum Handlowe Osowa' })
    expect(within(osowa).getByRole('button', { name: /DRN-004/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Riviera' }))
    const riviera = screen.getByRole('complementary', { name: 'Hub details: Centrum Riviera' })
    expect(within(riviera).queryByRole('button', { name: /DRN-004/ })).not.toBeInTheDocument()
    expect(within(riviera).getByText('Drones at this Hub (2)')).toBeInTheDocument()
  })

  it('says so when no drone is docked at a Hub', async () => {
    stubBackend(okHubs, () => Promise.resolve(jsonResponse([])))
    render(<App />)
    await screen.findByText('No drones are available yet.')

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))

    expect(screen.getByText('No drones are docked here.')).toBeInTheDocument()
  })

  it('replaces the Hub panel when a marker drone is selected', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    expect(panels()).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-002' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Marker Forum Gdańsk' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('replaces the drone panel when a Hub is selected', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('switches between two marker drones with a single panel', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-003' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-003' })).toBeVisible()
  })

  it('closes the drone panel on Escape and with the close button', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(panels()).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-003' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close drone details' }))
    expect(panels()).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Drone marker DRN-003' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })
})
