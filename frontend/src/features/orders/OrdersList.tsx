import { useId, useState } from 'react'

import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY } from './orderStatus'

interface OrdersListProps {
  orders: readonly Order[]
  hubs: readonly Hub[]
  selectedOrderId: string | null
  onSelectOrder: (orderId: string) => void
  /**
   * Hides the list on narrow screens (it stays mounted, so its open state survives) while a detail
   * panel is open: the panel and the list together would cover most of a phone-sized map.
   */
  hideOnNarrow?: boolean
}

/**
 * Collapsible list of every order, closed by default so it does not cover the map. It is also the
 * always-available way to reach any order, whatever its marker looks like on the map. Rows stay in
 * the backend's order (by creation time, then id).
 */
export function OrdersList({
  orders,
  hubs,
  selectedOrderId,
  onSelectOrder,
  hideOnNarrow = false,
}: OrdersListProps) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const hubNames = new Map(hubs.map((hub) => [hub.id, hub.name]))

  if (orders.length === 0) return null

  return (
    <section
      aria-label="Orders"
      className={`rounded-lg border border-line bg-surface text-sm shadow-lg ${
        hideOnNarrow ? 'max-sm:hidden' : ''
      }`}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-10 w-full items-center justify-between gap-3 rounded-lg px-3 text-left font-medium hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span>Orders ({orders.length})</span>
        <span aria-hidden="true" className="text-fg-muted">
          {open ? '▴' : '▾'}
        </span>
      </button>

      {open && (
        <ul
          id={listId}
          className="max-h-[28dvh] overflow-y-auto border-t border-line sm:max-h-[50dvh]"
        >
          {orders.map((order) => {
            const selected = order.id === selectedOrderId
            return (
              <li key={order.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelectOrder(order.id)}
                  className={`flex min-h-10 w-full flex-col gap-0.5 border-l-4 px-3 py-2 text-left hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent ${
                    selected ? 'border-accent bg-surface-raised' : 'border-transparent'
                  }`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-mono">{order.id}</span>
                    <span
                      className={
                        order.status === 'CANCELLED'
                          ? 'font-medium text-status-critical'
                          : order.status === 'DELIVERY_FAILED'
                            ? 'font-medium text-status-failed'
                            : 'text-fg-muted'
                      }
                    >
                      {ORDER_STATUS_DISPLAY[order.status].label} · {order.packageWeightKg} kg
                    </span>
                  </span>
                  <span className="text-xs text-fg-muted">
                    {hubNames.get(order.originHubId) ?? order.originHubId} →{' '}
                    {order.destinationAddress}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
