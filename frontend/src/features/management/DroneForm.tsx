import { useState, type FormEvent } from 'react'

import type { DroneChanges, DroneInput } from '../../api/drones'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { useAction } from './useAction'
import {
  FIELD_LABEL_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './formStyles'

interface DroneFormProps {
  hubs: readonly Hub[]
  /** The drone being edited; omitted when creating. */
  drone?: Drone
  /** Create: called with the new drone's fields. Edit: called with the changed fields only. */
  onCreate?: (input: DroneInput) => Promise<unknown>
  onUpdate?: (changes: DroneChanges) => Promise<unknown>
  /** Whether the Hub can be changed (the backend only moves an IDLE, docked drone). */
  canReassign?: boolean
  onDone: () => void
  onCancel: () => void
}

/** Create a drone (id, Hub, battery) or edit its battery and Hub; the backend checks every rule. */
export function DroneForm({
  hubs,
  drone,
  onCreate,
  onUpdate,
  canReassign = true,
  onDone,
  onCancel,
}: DroneFormProps) {
  const { busy, error, run, clearError } = useAction()
  const [id, setId] = useState('')
  const [hubId, setHubId] = useState(drone?.hubId ?? hubs[0]?.id ?? '')
  const [battery, setBattery] = useState(String(drone?.batteryPct ?? 100))
  const [localError, setLocalError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    clearError()
    const pct = battery.trim() === '' ? NaN : Number(battery)
    if (!Number.isInteger(pct) || pct < 0 || pct > 100) {
      return setLocalError('Battery must be a whole number from 0 to 100.')
    }
    if (!hubId) return setLocalError('Choose a Hub.')

    let action: () => Promise<unknown>
    if (drone) {
      const changes: DroneChanges = {}
      if (pct !== drone.batteryPct) changes.batteryPct = pct
      if (hubId !== drone.hubId) changes.hubId = hubId
      if (Object.keys(changes).length === 0) return setLocalError('Nothing has changed.')
      action = () => onUpdate?.(changes) ?? Promise.resolve()
    } else {
      if (id.trim() === '') return setLocalError('Enter a drone id, for example DRN-013.')
      action = () => onCreate?.({ id: id.trim(), hubId, batteryPct: pct }) ?? Promise.resolve()
    }
    setLocalError(null)
    if (await run(action)) onDone()
  }

  const message = localError ?? error
  return (
    <form
      onSubmit={handleSubmit}
      aria-label={drone ? `Edit drone ${drone.id}` : 'Create drone'}
      className="flex flex-col gap-3 rounded border border-line p-3"
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {!drone && (
          <label className={FIELD_LABEL_CLASS}>
            Drone id (DRN- and digits)
            <input
              className={INPUT_CLASS}
              value={id}
              disabled={busy}
              maxLength={32}
              onChange={(event) => setId(event.target.value)}
            />
          </label>
        )}
        <label className={FIELD_LABEL_CLASS}>
          Assigned Hub
          <select
            className={INPUT_CLASS}
            value={hubId}
            disabled={busy || (drone !== undefined && !canReassign)}
            onChange={(event) => setHubId(event.target.value)}
          >
            {hubs.map((hub) => (
              <option key={hub.id} value={hub.id}>
                {hub.name}
              </option>
            ))}
          </select>
        </label>
        <label className={FIELD_LABEL_CLASS}>
          Battery (%)
          <input
            className={INPUT_CLASS}
            type="number"
            step="1"
            value={battery}
            disabled={busy}
            onChange={(event) => setBattery(event.target.value)}
          />
        </label>
      </div>
      {drone && !canReassign && (
        <p className="text-xs text-fg-muted">
          The Hub can only be changed while the drone is idle at a Hub.
        </p>
      )}
      {message && (
        <p role="alert" className="text-sm text-status-critical">
          {message}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className={PRIMARY_BUTTON_CLASS} disabled={busy}>
          {busy ? 'Saving…' : drone ? 'Save changes' : 'Create drone'}
        </button>
        <button type="button" className={SECONDARY_BUTTON_CLASS} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
