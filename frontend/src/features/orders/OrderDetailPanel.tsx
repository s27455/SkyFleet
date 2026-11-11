import { type ReactNode, useEffect } from 'react'

import { DETAIL_PANEL_CLASS } from '../../components/ui/detailPanel'
import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY, formatUtcTimestamp } from './orderStatus'

interface OrderDetailPanelProps {
  order: Order
  /** The origin Hub if the Hub data is available; otherwise the Hub id is shown as is. */
  hub?: Hub
  /** True when the destination marker is spread on screen because orders share this location. */
  markerSpread: boolean
  onClose: () => void
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

export function OrderDetailPanel({ order, hub, markerSpread, onClose }: OrderDetailPanelProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const status = ORDER_STATUS_DISPLAY[order.status]
  const [longitude, latitude] = order.coordinates

  return (
    <aside aria-label={`Order details: ${order.id}`} className={DETAIL_PANEL_CLASS}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{order.id}</h2>
          <p className="text-sm text-fg-muted">Delivery order</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close order details"
          className="-mt-1 -mr-1 inline-flex size-10 items-center justify-center rounded-md text-fg-muted hover:bg-surface-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <Row label="Status">
          <StatusIndicator tone={status.tone} label={status.label} />
        </Row>
        <Row label="Package weight">
          <span className="font-mono tabular-nums">{order.packageWeightKg} kg</span>
        </Row>
        <Row label="Origin Hub">{hub ? hub.name : order.originHubId}</Row>
        <Row label="Destination">{order.destinationAddress}</Row>
        <Row label="Destination position">
          <span className="font-mono text-xs tabular-nums">
            {latitude.toFixed(6)}, {longitude.toFixed(6)}
          </span>
        </Row>
        <Row label="Created">{formatUtcTimestamp(order.createdAt)}</Row>
        <Row label="Updated">{formatUtcTimestamp(order.updatedAt)}</Row>
      </dl>

      <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
        Simulation data: the destination is illustrative, not a verified customer address.
        {markerSpread &&
          ' Markers at the same location are spread slightly on screen; the position above is the real stored one.'}
      </p>
    </aside>
  )
}
