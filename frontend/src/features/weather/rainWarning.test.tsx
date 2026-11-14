import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../api/client'
import {
  activateRainWarning,
  clearRainWarning,
  getRainWarning,
  isRainWarningActive,
} from '../../api/incidents'
import { StartMissionError, startMission } from '../../api/missions'
import { RelocateError, relocateDrone } from '../../api/relocation'
import { jsonResponse } from '../../test/hubFixtures'
import type { Drone } from '../../types/drone'
import type { Mission } from '../../types/mission'
import { RelocateDroneControl } from '../drones/RelocateDroneControl'
import { SimulationEventsPanel } from '../incidents/SimulationEventsPanel'
import { StartMissionControl } from '../missions/StartMissionControl'
import { RainWarningBanner } from './RainWarningBanner'
import { TakeoffsSuspendedProvider } from './TakeoffGate'

afterEach(() => vi.unstubAllGlobals())

const WARNING = {
  active: true,
  activated_at: '2026-11-14T10:00:00Z',
  cleared_at: null,
  origin: 'MANUAL',
}
const RAIN_409 = {
  detail: {
    code: 'RAIN_WARNING_ACTIVE',
    message: 'Takeoff is prohibited: a rain warning is active.',
  },
}

describe('rain warning API', () => {
  it('reads the status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(WARNING))),
    )

    expect(await getRainWarning()).toEqual({
      active: true,
      activatedAt: '2026-11-14T10:00:00Z',
      clearedAt: null,
    })
  })

  it('rejects a malformed answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ active: 'yes' }))),
    )

    await expect(getRainWarning()).rejects.toBeInstanceOf(ApiError)
  })

  it('activates and clears with POST and no body', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(WARNING)),
    )
    vi.stubGlobal('fetch', fetchMock)

    await activateRainWarning()
    await clearRainWarning()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/rain-warning\/activate$/)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/incidents\/rain-warning\/clear$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
  })

  it('recognises the stable 409 code only', () => {
    expect(isRainWarningActive(new ApiError('x', 409, RAIN_409.detail))).toBe(true)
    expect(isRainWarningActive(new ApiError('x', 409, { code: 'OTHER' }))).toBe(false)
    expect(isRainWarningActive(new ApiError('x', 500, RAIN_409.detail))).toBe(false)
    expect(isRainWarningActive(new Error('x'))).toBe(false)
  })

  it('explains a refused start and a refused relocation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(RAIN_409, 409))),
    )

    const start = (await startMission('MIS-1').catch((c: unknown) => c)) as StartMissionError
    const relocate = (await relocateDrone('DRN-010', 'hub-x').catch(
      (c: unknown) => c,
    )) as RelocateError

    expect(start.failure).toBe('RAIN_WARNING')
    expect(start.message).toMatch(/rain warning/i)
    expect(relocate).toBeInstanceOf(RelocateError)
    expect(relocate.message).toMatch(/rain warning/i)
  })
})

describe('RainWarningBanner', () => {
  it('shows nothing while the warning is inactive', () => {
    render(<RainWarningBanner active={false} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says takeoffs are suspended, claims no live data, and flags a stale status', () => {
    render(<RainWarningBanner active stale />)

    const banner = screen.getByRole('status', { name: 'Rain warning' })
    expect(banner).toHaveTextContent('New takeoffs suspended (precautionary)')
    expect(banner).toHaveTextContent('Flights in the air continue')
    expect(banner).toHaveTextContent('out of date')
  })
})

describe('Rain Warning control', () => {
  it('activates from the events panel and refreshes afterwards', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve(jsonResponse(WARNING)))
    vi.stubGlobal('fetch', fetchMock)
    const onChanged = vi.fn()
    render(<SimulationEventsPanel onRainWarningChanged={onChanged} />)

    const button = screen.getByRole('button', { name: /Activate Rain Warning/ })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(button)

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/rain-warning\/activate$/)
  })

  it('shows the active state and clears it', async () => {
    const fetchMock = vi.fn((_url: string) =>
      Promise.resolve(jsonResponse({ ...WARNING, active: false })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onChanged = vi.fn()
    render(<SimulationEventsPanel rainWarningActive onRainWarningChanged={onChanged} />)

    const button = screen.getByRole('button', { name: /Clear Rain Warning/ })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button).toHaveTextContent('Active: takeoffs suspended')
    fireEvent.click(button)

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/rain-warning\/clear$/)
  })

  it('shows a failed request and still refreshes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    const onChanged = vi.fn()
    render(<SimulationEventsPanel onRainWarningChanged={onChanged} />)

    fireEvent.click(screen.getByRole('button', { name: /Activate Rain Warning/ }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledTimes(1)
  })
})

const MISSION: Mission = {
  id: 'MIS-AAAA0001',
  orderId: 'ORD-001',
  purpose: 'DELIVERY',
  droneId: 'DRN-010',
  originHubId: 'hub-a',
  returnHubId: 'hub-a',
  status: 'ASSIGNED',
  totalKm: 1.4,
}
const DRONE = {
  id: 'DRN-010',
  hubId: 'hub-a',
  status: 'IDLE',
  batteryPct: 100,
  coordinates: [18.6, 54.38],
} as unknown as Drone

describe('controls that would start a flight', () => {
  it('disables Start mission while takeoffs are suspended and enables it after', () => {
    const view = render(
      <TakeoffsSuspendedProvider value>
        <StartMissionControl mission={MISSION} onStart={vi.fn()} />
      </TakeoffsSuspendedProvider>,
    )

    expect(screen.getByRole('button', { name: 'Start mission MIS-AAAA0001' })).toBeDisabled()
    expect(screen.getByRole('region')).toHaveTextContent('new takeoffs are suspended')
    expect(screen.getByRole('region')).toHaveTextContent('stays assigned')

    view.rerender(
      <TakeoffsSuspendedProvider value={false}>
        <StartMissionControl mission={MISSION} onStart={vi.fn()} />
      </TakeoffsSuspendedProvider>,
    )
    expect(screen.getByRole('button', { name: 'Start mission MIS-AAAA0001' })).toBeEnabled()
  })

  it('disables Relocate and explains why while takeoffs are suspended', () => {
    render(
      <TakeoffsSuspendedProvider value>
        <RelocateDroneControl drone={DRONE} hubs={[]} onChanged={vi.fn()} />
      </TakeoffsSuspendedProvider>,
    )

    expect(screen.getByRole('button', { name: 'Relocate DRN-010' })).toBeDisabled()
    expect(screen.getByText(/new takeoffs are suspended/)).toBeInTheDocument()
  })

  it('leaves the controls unchanged without the provider', () => {
    render(<StartMissionControl mission={MISSION} onStart={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Start mission MIS-AAAA0001' })).toBeEnabled()
  })
})
