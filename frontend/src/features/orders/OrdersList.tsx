import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY } from './orderStatus'

interface OrdersListProps {
  orders: readonly Order[]
  hubs: readonly Hub[]
  selectedOrderId: string | null
  onSelectOrder: (orderId: string) => void
}

/**
 * Every order as a selectable row (the Orders tab of the Operations panel). It is also the
 * always-available way to reach any order, whatever its marker looks like on the map. Rows stay in
 * the backend's order (by creation time, then id). Scrolling belongs to the panel around it.
 */
export function OrdersList({ orders, hubs, selectedOrderId, onSelectOrder }: OrdersListProps) {
  const hubNames = new Map(hubs.map((hub) => [hub.id, hub.name]))

  if (orders.length === 0) return <p className="p-3 text-xs text-fg-muted">No orders yet.</p>

  return (
    <ul aria-label="Orders">
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
                {hubNames.get(order.originHubId) ?? order.originHubId} → {order.destinationAddress}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
