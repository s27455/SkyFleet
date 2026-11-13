import { useState, type FormEvent } from 'react'

import type { OrderInput } from '../../api/orders'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { useAction } from './useAction'
import {
  FIELD_LABEL_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './formStyles'

interface OrderFormProps {
  hubs: readonly Hub[]
  /** The order being edited; omitted when creating. */
  order?: Order
  /** Resolves when the backend accepted the change; a rejection is shown in the form. */
  onSubmit: (input: OrderInput) => Promise<unknown>
  onDone: () => void
  onCancel: () => void
}

function parseNumber(value: string): number | null {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Compact create/edit form. Coordinates are typed explicitly: there is no geocoding. */
export function OrderForm({ hubs, order, onSubmit, onDone, onCancel }: OrderFormProps) {
  const { busy, error, run, clearError } = useAction()
  const [hubId, setHubId] = useState(order?.originHubId ?? hubs[0]?.id ?? '')
  const [address, setAddress] = useState(order?.destinationAddress ?? '')
  const [longitude, setLongitude] = useState(order ? String(order.coordinates[0]) : '')
  const [latitude, setLatitude] = useState(order ? String(order.coordinates[1]) : '')
  const [weight, setWeight] = useState(order ? String(order.packageWeightKg) : '')
  const [localError, setLocalError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    clearError()
    const lng = parseNumber(longitude)
    const lat = parseNumber(latitude)
    const kg = parseNumber(weight)
    if (!hubId) return setLocalError('Choose an origin Hub.')
    if (address.trim() === '') return setLocalError('Enter a delivery address.')
    if (lng === null || lat === null) {
      return setLocalError('Enter the delivery longitude and latitude as numbers.')
    }
    if (kg === null) return setLocalError('Enter the package weight as a number.')
    if (
      order &&
      hubId === order.originHubId &&
      address.trim() === order.destinationAddress &&
      lng === order.coordinates[0] &&
      lat === order.coordinates[1] &&
      kg === order.packageWeightKg
    ) {
      return setLocalError('Nothing has changed.')
    }
    setLocalError(null)
    const ok = await run(() =>
      onSubmit({
        originHubId: hubId,
        destinationAddress: address.trim(),
        longitude: lng,
        latitude: lat,
        packageWeightKg: kg,
      }),
    )
    if (ok) onDone()
  }

  const message = localError ?? error
  return (
    <form
      onSubmit={handleSubmit}
      aria-label={order ? `Edit order ${order.id}` : 'Create order'}
      className="flex flex-col gap-3 rounded border border-line p-3"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className={FIELD_LABEL_CLASS}>
          Origin Hub
          <select
            className={INPUT_CLASS}
            value={hubId}
            disabled={busy}
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
          Delivery address
          <input
            className={INPUT_CLASS}
            value={address}
            disabled={busy}
            maxLength={255}
            onChange={(event) => setAddress(event.target.value)}
          />
        </label>
        <label className={FIELD_LABEL_CLASS}>
          Delivery longitude
          <input
            className={INPUT_CLASS}
            type="number"
            step="any"
            value={longitude}
            disabled={busy}
            onChange={(event) => setLongitude(event.target.value)}
          />
        </label>
        <label className={FIELD_LABEL_CLASS}>
          Delivery latitude
          <input
            className={INPUT_CLASS}
            type="number"
            step="any"
            value={latitude}
            disabled={busy}
            onChange={(event) => setLatitude(event.target.value)}
          />
        </label>
        <label className={FIELD_LABEL_CLASS}>
          Package weight (kg)
          <input
            className={INPUT_CLASS}
            type="number"
            step="any"
            value={weight}
            disabled={busy}
            onChange={(event) => setWeight(event.target.value)}
          />
        </label>
      </div>
      {message && (
        <p role="alert" className="text-sm text-status-critical">
          {message}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className={PRIMARY_BUTTON_CLASS} disabled={busy}>
          {busy ? 'Saving…' : order ? 'Save changes' : 'Create order'}
        </button>
        <button type="button" className={SECONDARY_BUTTON_CLASS} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
