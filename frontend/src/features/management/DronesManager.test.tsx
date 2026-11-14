import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { toDrone } from '../../api/drones'
import { DRONE_RESPONSES } from '../../test/droneFixtures'
import { jsonResponse } from '../../test/hubFixtures'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import { DronesManager } from './DronesManager'

const HUBS: Hub[] = [
  {
    id: 'hub-galeria-baltycka',
    name: 'Galeria Bałtycka',
    address: 'Grunwaldzka 141',
    coordinates: [18.6, 54.38],
    droneCapacity: 50,
  },
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    address: 'Targ Sienny 7',
    coordinates: [18.64, 54.35],
    droneCapacity: 50,
  },
]

const base = DRONE_RESPONSES[0]
const DRONES: Drone[] = [
  toDrone({ ...base, id: 'DRN-001', hub_id: 'hub-galeria-baltycka' }), // free, idle
  toDrone({ ...base, id: 'DRN-002', hub_id: 'hub-galeria-baltycka' }), // active mission
  toDrone({ ...base, id: 'DRN-003', status: 'IN_FLIGHT' }),
  toDrone({ ...base, id: 'DRN-004', status: 'MAINTENANCE' }),
  toDrone({ ...base, id: 'DRN-005' }), // mission history only
  toDrone({ ...base, id: 'DRN-006', status: 'CHARGING' }),
]

const mission = (droneId: string, status: Mission['status']): Mission => ({
  id: `MIS-${droneId}`,
  orderId: 'ORD-001',
  purpose: 'DELIVERY',
  droneId,
  originHubId: 'hub-galeria-baltycka',
  returnHubId: 'hub-galeria-baltycka',
  status,
  totalKm: 3,
})
const MISSIONS = [mission('DRN-002', 'ASSIGNED'), mission('DRN-005', 'COMPLETED')]

function renderManager(drones: Drone[] = DRONES) {
  const onChanged = vi.fn()
  render(<DronesManager drones={drones} hubs={HUBS} missions={MISSIONS} onChanged={onChanged} />)
  return { onChanged }
}

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const button = (name: string) => screen.getByRole('button', { name })

describe('DronesManager', () => {
  it('follows the backend rules when enabling row actions', () => {
    renderManager()

    // idle, no missions: everything allowed
    expect(button('Edit drone DRN-001')).toBeEnabled()
    expect(button('Set to maintenance: drone DRN-001')).toBeEnabled()
    expect(button('Delete drone DRN-001')).toBeEnabled()
    // active mission: no change, no delete
    expect(button('Edit drone DRN-002')).toBeDisabled()
    expect(button('Delete drone DRN-002')).toBeDisabled()
    // in flight and charging: nothing
    expect(button('Edit drone DRN-003')).toBeDisabled()
    expect(button('Delete drone DRN-003')).toBeDisabled()
    expect(button('Delete drone DRN-006')).toBeDisabled()
    // maintenance can return to service
    expect(button('Return to service: drone DRN-004')).toBeEnabled()
    // history only: can be changed but not deleted
    expect(button('Edit drone DRN-005')).toBeEnabled()
    expect(button('Delete drone DRN-005')).toBeDisabled()
  })

  it('shows an empty state', () => {
    renderManager([])

    expect(screen.getByText(/No drones yet/)).toBeInTheDocument()
  })

  it('creates a drone from id, Hub and battery', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(base, 201)))
    const { onChanged } = renderManager()

    fireEvent.click(button('New drone'))
    fireEvent.change(screen.getByLabelText(/Drone id/), { target: { value: 'DRN-100' } })
    fireEvent.change(screen.getByLabelText('Current Hub'), {
      target: { value: 'hub-forum-gdansk' },
    })
    fireEvent.change(screen.getByLabelText('Battery (%)'), { target: { value: '60' } })
    fireEvent.click(button('Create drone'))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/drones$/)
    expect(JSON.parse(String(init?.body))).toEqual({
      id: 'DRN-100',
      hub_id: 'hub-forum-gdansk',
      battery_pct: 60,
    })
  })

  it('shows the backend message when the Hub is full or the id is taken', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ detail: { code: 'HUB_FULL', message: "Hub 'x' has no free place" } }, 409),
      ),
    )
    const { onChanged } = renderManager()

    fireEvent.click(button('New drone'))
    fireEvent.change(screen.getByLabelText(/Drone id/), { target: { value: 'DRN-100' } })
    fireEvent.click(button('Create drone'))

    expect(await screen.findByRole('alert')).toHaveTextContent("Hub 'x' has no free place")
    expect(onChanged).not.toHaveBeenCalled()
    expect(screen.getByRole('form', { name: 'Create drone' })).toBeInTheDocument()
  })

  it('checks battery and id locally without calling the backend', () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({})))
    renderManager()

    fireEvent.click(button('New drone'))
    fireEvent.click(button('Create drone'))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a drone id')

    fireEvent.change(screen.getByLabelText(/Drone id/), { target: { value: 'DRN-100' } })
    fireEvent.change(screen.getByLabelText('Battery (%)'), { target: { value: '101' } })
    fireEvent.click(button('Create drone'))
    expect(screen.getByRole('alert')).toHaveTextContent('whole number from 0 to 100')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends one create request however often the button is clicked', async () => {
    let release: (response: Response) => void = () => undefined
    const fetchMock = stubFetch(() => new Promise<Response>((resolve) => (release = resolve)))
    renderManager()

    fireEvent.click(button('New drone'))
    fireEvent.change(screen.getByLabelText(/Drone id/), { target: { value: 'DRN-100' } })
    const submit = button('Create drone')
    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    release(jsonResponse(base, 201))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Saving…' })).toBeNull())
  })

  it('edits only the changed fields', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(base)))
    const { onChanged } = renderManager()

    fireEvent.click(button('Edit drone DRN-001'))
    fireEvent.change(screen.getByLabelText('Battery (%)'), { target: { value: '55' } })
    fireEvent.click(button('Save changes'))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/drones\/DRN-001$/)
    expect(init?.method).toBe('PATCH')
    expect(JSON.parse(String(init?.body))).toEqual({ battery_pct: 55 })
  })

  it('refuses an unchanged edit locally', () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({})))
    renderManager()

    fireEvent.click(button('Edit drone DRN-001'))
    fireEvent.click(button('Save changes'))

    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has changed.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('only allows changing the Hub of an idle drone', () => {
    renderManager()

    fireEvent.click(button('Edit drone DRN-004')) // in maintenance

    expect(screen.getByLabelText('Current Hub')).toBeDisabled()
  })

  it('moves a drone to maintenance and back with a single PATCH', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(base)))
    const { onChanged } = renderManager()

    fireEvent.click(button('Set to maintenance: drone DRN-001'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    fireEvent.click(button('Return to service: drone DRN-004'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2))

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      status: 'MAINTENANCE',
    })
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ status: 'IDLE' })
  })

  it('shows the backend refusal when a status change is rejected', async () => {
    stubFetch(() =>
      Promise.resolve(jsonResponse({ detail: { code: 'HUB_FULL', message: 'Hub is full' } }, 409)),
    )
    const { onChanged } = renderManager()

    fireEvent.click(button('Return to service: drone DRN-004'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Hub is full')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('requires confirmation before deleting, then deletes and refreshes', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(new Response(null, { status: 204 })))
    const { onChanged } = renderManager()

    fireEvent.click(button('Delete drone DRN-001'))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('DRN-001')
    fireEvent.click(button('Delete permanently'))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('shows the backend refusal when a delete is rejected', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          { detail: { code: 'DRONE_HAS_HISTORY', message: 'Drone has mission history' } },
          409,
        ),
      ),
    )
    const { onChanged } = renderManager()

    fireEvent.click(button('Delete drone DRN-001'))
    fireEvent.click(button('Delete permanently'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Drone has mission history')
    expect(onChanged).not.toHaveBeenCalled()
  })
})
