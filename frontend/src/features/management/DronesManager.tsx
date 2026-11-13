import { useMemo, useState } from 'react'

import { createDrone, deleteDrone, updateDrone } from '../../api/drones'
import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import { DRONE_STATUS_DISPLAY } from '../drones/droneStatus'
import { ConfirmDelete } from './ConfirmDelete'
import { LINK_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from './formStyles'
import { DroneForm } from './DroneForm'
import { useAction } from './useAction'

interface DronesManagerProps {
  drones: readonly Drone[]
  hubs: readonly Hub[]
  missions: readonly Mission[]
  /** Called after a successful change so the polled data is re-read at once. */
  onChanged: () => void
}

type Mode =
  | { kind: 'none' }
  | { kind: 'create' }
  | { kind: 'edit'; id: string }
  | { kind: 'delete'; id: string }

const ACTIVE_MISSION_STATUSES = new Set(['ASSIGNED', 'IN_FLIGHT'])

/**
 * Drone administration (Feature 011 API). The row actions follow the backend rules as hints taken
 * from the polled drones and missions: a drone can be edited or put into maintenance only while
 * IDLE or in MAINTENANCE with no active mission, and deleted only with no missions at all. The
 * backend still decides, and its message is shown when it refuses. There is no "retire" action:
 * the API offers maintenance as the way to take a drone out of service.
 */
export function DronesManager({ drones, hubs, missions, onChanged }: DronesManagerProps) {
  const [mode, setMode] = useState<Mode>({ kind: 'none' })
  const deletion = useAction()
  const maintenance = useAction()
  const hubNames = useMemo(() => new Map(hubs.map((hub) => [hub.id, hub.name])), [hubs])
  const activeMissionDrones = useMemo(
    () =>
      new Set(missions.filter((m) => ACTIVE_MISSION_STATUSES.has(m.status)).map((m) => m.droneId)),
    [missions],
  )
  const anyMissionDrones = useMemo(() => new Set(missions.map((m) => m.droneId)), [missions])

  const canChange = (drone: Drone) =>
    (drone.status === 'IDLE' || drone.status === 'MAINTENANCE') &&
    !activeMissionDrones.has(drone.id)
  const canDelete = (drone: Drone) =>
    drone.status !== 'IN_FLIGHT' && drone.status !== 'CHARGING' && !anyMissionDrones.has(drone.id)
  const changeReason = (drone: Drone) =>
    activeMissionDrones.has(drone.id)
      ? 'Has an active mission'
      : 'Only idle or maintenance drones can be changed'
  const deleteReason = (drone: Drone) =>
    anyMissionDrones.has(drone.id)
      ? 'Has mission history'
      : 'A drone in flight or charging cannot be deleted'

  const close = () => {
    deletion.clearError()
    setMode({ kind: 'none' })
  }
  const done = () => {
    onChanged()
    close()
  }

  const editing = mode.kind === 'edit' ? drones.find((drone) => drone.id === mode.id) : undefined
  const deleting = mode.kind === 'delete' ? drones.find((drone) => drone.id === mode.id) : undefined

  // Close an open form or confirmation whose row has disappeared (see OrdersManager).
  const targetMissing = (mode.kind === 'edit' || mode.kind === 'delete') && !editing && !deleting
  if (targetMissing) setMode({ kind: 'none' }) // adjusting state while rendering is allowed

  const open = (next: Mode) => {
    deletion.clearError()
    maintenance.clearError()
    setMode(next)
  }

  async function toggleMaintenance(drone: Drone) {
    const next = drone.status === 'MAINTENANCE' ? 'IDLE' : 'MAINTENANCE'
    if (await maintenance.run(() => updateDrone(drone.id, { status: next }))) onChanged()
  }

  return (
    <section aria-label="Drones management" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Drones ({drones.length})</h3>
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={hubs.length === 0 || mode.kind === 'create'}
          onClick={() => open({ kind: 'create' })}
        >
          New drone
        </button>
      </div>

      {mode.kind === 'create' && (
        <DroneForm hubs={hubs} onCreate={createDrone} onDone={done} onCancel={close} />
      )}
      {editing && (
        <DroneForm
          key={editing.id}
          hubs={hubs}
          drone={editing}
          canReassign={editing.status === 'IDLE'}
          onUpdate={(changes) => updateDrone(editing.id, changes)}
          onDone={done}
          onCancel={close}
        />
      )}
      {deleting && (
        <ConfirmDelete
          subject={`drone ${deleting.id}`}
          consequence="Only a drone with no missions can be deleted; the backend refuses otherwise. To take a drone out of service without deleting it, set it to maintenance."
          busy={deletion.busy}
          error={deletion.error}
          onCancel={close}
          onConfirm={async () => {
            if (await deletion.run(() => deleteDrone(deleting.id))) done()
          }}
        />
      )}
      {maintenance.error && (
        <p role="alert" className="text-sm text-status-critical">
          {maintenance.error}
        </p>
      )}

      {drones.length === 0 ? (
        <p className="text-sm text-fg-muted">No drones yet. Create one to get started.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-fg-muted">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Drone
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Current Hub
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Battery
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Status
                </th>
                <th scope="col" className="py-1 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {drones.map((drone) => {
                const display = DRONE_STATUS_DISPLAY[drone.status]
                const changeable = canChange(drone)
                const deletable = canDelete(drone)
                const inMaintenance = drone.status === 'MAINTENANCE'
                return (
                  <tr key={drone.id} className="border-t border-line">
                    <td className="py-1.5 pr-3 font-mono text-xs">{drone.id}</td>
                    <td className="py-1.5 pr-3">{hubNames.get(drone.hubId) ?? drone.hubId}</td>
                    <td className="py-1.5 pr-3">{drone.batteryPct}%</td>
                    <td className="py-1.5 pr-3">
                      <StatusIndicator tone={display.tone} label={display.label} />
                    </td>
                    <td className="py-1.5">
                      <div className="flex gap-3">
                        <button
                          type="button"
                          className={LINK_BUTTON_CLASS}
                          disabled={!changeable}
                          title={changeable ? undefined : changeReason(drone)}
                          aria-label={`Edit drone ${drone.id}`}
                          onClick={() => {
                            open({ kind: 'edit', id: drone.id })
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className={LINK_BUTTON_CLASS}
                          disabled={!changeable || maintenance.busy}
                          title={changeable ? undefined : changeReason(drone)}
                          aria-label={`${inMaintenance ? 'Return to service' : 'Set to maintenance'}: drone ${drone.id}`}
                          onClick={() => void toggleMaintenance(drone)}
                        >
                          {inMaintenance ? 'Return to service' : 'Set to maintenance'}
                        </button>
                        <button
                          type="button"
                          className={LINK_BUTTON_CLASS}
                          disabled={!deletable}
                          title={deletable ? undefined : deleteReason(drone)}
                          aria-label={`Delete drone ${drone.id}`}
                          onClick={() => {
                            open({ kind: 'delete', id: drone.id })
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
