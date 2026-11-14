import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { RelocateDroneControl } from './RelocateDroneControl'

const HUBS: Hub[] = [
  {
    id: 'hub-galeria-baltycka',
    name: 'Galeria Bałtycka',
    address: 'a',
    coordinates: [18.6, 54.38],
    droneCapacity: 50,
  },
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    address: 'b',
    coordinates: [18.64, 54.35],
    droneCapacity: 50,
  },
]

const DRONE = {
  id: 'DRN-010',
  hubId: 'hub-galeria-baltycka',
  status: 'IDLE',
  batteryPct: 100,
  coordinates: [18.6, 54.38],
} as unknown as Drone

const PLAN = {
  drone_id: 'DRN-010',
  eligible: true,
  reasons: [],
  origin_hub_id: 'hub-galeria-baltycka',
  destination_hub_id: 'hub-forum-gdansk',
  distance_km: 4.6,
  distance_budget_km: 14,
  required_battery_pct: 43,
  expected_battery_use_pct: 23,
  drone_battery_pct: 100,
  destination_docked_drones: 3,
  destination_capacity: 50,
  warnings: ['2 order(s) are waiting for pickup at the source Hub.'],
}

const STARTED = {
  mission_id: 'MIS-RELOC001',
  drone_id: 'DRN-010',
  origin_hub_id: 'hub-galeria-baltycka',
  destination_hub_id: 'hub-forum-gdansk',
  started_at: '2026-11-12T10:00:00Z',
  distance_km: 4.6,
}

function stubBackend(
  plan: unknown = PLAN,
  relocate: () => Response = () => jsonResponse(STARTED, 201),
) {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
    Promise.resolve(init?.method === 'POST' ? relocate() : jsonResponse(plan)),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const openAndChoose = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Relocate DRN-010' }))
  fireEvent.change(screen.getByLabelText('Destination Hub'), {
    target: { value: 'hub-forum-gdansk' },
  })
  await screen.findByText(/4\.6 km/)
}

describe('RelocateDroneControl', () => {
  it('is disabled with the reason when the drone cannot be relocated', () => {
    render(
      <RelocateDroneControl
        drone={DRONE}
        hubs={HUBS}
        unavailableReason="Only an idle drone docked at a Hub can be relocated (this drone is charging)."
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Relocate DRN-010' })).toBeDisabled()
    expect(screen.getByText(/this drone is charging/)).toBeInTheDocument()
  })

  it('offers only the other Hubs and previews the chosen one before anything starts', async () => {
    const fetchMock = stubBackend()
    render(<RelocateDroneControl drone={DRONE} hubs={HUBS} onChanged={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Relocate DRN-010' }))
    const options = screen.getAllByRole('option').map((option) => option.textContent)
    expect(options).toEqual(['Choose a Hub…', 'Forum Gdańsk'])
    fireEvent.change(screen.getByLabelText('Destination Hub'), {
      target: { value: 'hub-forum-gdansk' },
    })

    expect(await screen.findByText(/4\.6 km/)).toHaveTextContent('Galeria Bałtycka → Forum Gdańsk')
    expect(screen.getByText(/2 order\(s\) are waiting/)).toBeInTheDocument()
    expect(screen.getByText(/3 of 50 places taken/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true)
    expect(screen.getByRole('button', { name: 'Start relocation' })).toBeEnabled()
  })

  it('starts the relocation, confirms it and asks for a refresh', async () => {
    const fetchMock = stubBackend()
    const onChanged = vi.fn()
    render(<RelocateDroneControl drone={DRONE} hubs={HUBS} onChanged={onChanged} />)
    await openAndChoose()

    fireEvent.click(screen.getByRole('button', { name: 'Start relocation' }))

    expect(
      await screen.findByText(/Relocation started: DRN-010 is flying to Forum Gdańsk/),
    ).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledTimes(1)
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(screen.queryByLabelText('Destination Hub')).not.toBeInTheDocument()
  })

  it('does not allow starting an ineligible relocation and lists why', async () => {
    stubBackend({
      ...PLAN,
      eligible: false,
      reasons: [{ code: 'INSUFFICIENT_BATTERY', message: 'Drone battery is 30%; it needs more.' }],
    })
    render(<RelocateDroneControl drone={DRONE} hubs={HUBS} onChanged={vi.fn()} />)

    await openAndChoose()

    expect(screen.getByText('Drone battery is 30%; it needs more.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start relocation' })).toBeDisabled()
  })

  it('shows why a refused start was refused and still refreshes', async () => {
    const onChanged = vi.fn()
    stubBackend(PLAN, () =>
      jsonResponse(
        {
          detail: {
            code: 'RELOCATION_NOT_ELIGIBLE',
            message: 'x',
            plan: { reasons: [{ code: 'DESTINATION_FULL', message: 'The Hub is full.' }] },
          },
        },
        409,
      ),
    )
    render(<RelocateDroneControl drone={DRONE} hubs={HUBS} onChanged={onChanged} />)
    await openAndChoose()

    fireEvent.click(screen.getByRole('button', { name: 'Start relocation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The Hub is full.')
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/Relocation started/)).not.toBeInTheDocument()
  })

  it('says so when the preview cannot be read', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ detail: 'x' }, 500))),
    )
    render(<RelocateDroneControl drone={DRONE} hubs={HUBS} onChanged={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Relocate DRN-010' }))
    fireEvent.change(screen.getByLabelText('Destination Hub'), {
      target: { value: 'hub-forum-gdansk' },
    })

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not be checked'))
    expect(screen.getByRole('button', { name: 'Start relocation' })).toBeDisabled()
  })

  it('shows nothing for a drone that is in flight', () => {
    render(
      <RelocateDroneControl
        drone={{ ...DRONE, status: 'IN_FLIGHT' }}
        hubs={HUBS}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.queryByRole('region', { name: 'Relocate drone' })).not.toBeInTheDocument()
  })
})
