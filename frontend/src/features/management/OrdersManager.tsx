import { useMemo, useState } from 'react'

import { createOrder, deleteOrder, updateOrder } from '../../api/orders'
import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY } from '../orders/orderStatus'
import { ConfirmDelete } from './ConfirmDelete'
import { LINK_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from './formStyles'
import { OrderForm } from './OrderForm'
import { useAction } from './useAction'

interface OrdersManagerProps {
  orders: readonly Order[]
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

/**
 * Orders administration (Feature 012 API). Edit and Delete are offered only for a READY_FOR_PICKUP
 * order that no mission references; that is a hint taken from the polled missions, and the backend
 * still decides, with its message shown when it refuses.
 */
export function OrdersManager({ orders, hubs, missions, onChanged }: OrdersManagerProps) {
  const [mode, setMode] = useState<Mode>({ kind: 'none' })
  const deletion = useAction()
  const hubNames = useMemo(() => new Map(hubs.map((hub) => [hub.id, hub.name])), [hubs])
  const ordersWithMissions = useMemo(
    () => new Set(missions.map((mission) => mission.orderId)),
    [missions],
  )

  const isEligible = (order: Order) =>
    order.status === 'READY_FOR_PICKUP' && !ordersWithMissions.has(order.id)
  const close = () => {
    deletion.clearError()
    setMode({ kind: 'none' })
  }
  const done = () => {
    onChanged()
    close()
  }

  const editing = mode.kind === 'edit' ? orders.find((order) => order.id === mode.id) : undefined
  const deleting = mode.kind === 'delete' ? orders.find((order) => order.id === mode.id) : undefined

  // The row an open form or confirmation belongs to may disappear (a refresh after a change, or a
  // deletion elsewhere). Close it instead of leaving a hidden mode that could reopen later.
  const targetMissing = (mode.kind === 'edit' || mode.kind === 'delete') && !editing && !deleting
  if (targetMissing) setMode({ kind: 'none' }) // adjusting state while rendering is allowed

  const open = (next: Mode) => {
    deletion.clearError()
    setMode(next)
  }

  return (
    <section aria-label="Orders management" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Orders ({orders.length})</h3>
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={hubs.length === 0 || mode.kind === 'create'}
          onClick={() => open({ kind: 'create' })}
        >
          New order
        </button>
      </div>

      {mode.kind === 'create' && (
        <OrderForm hubs={hubs} onSubmit={createOrder} onDone={done} onCancel={close} />
      )}
      {editing && (
        <OrderForm
          key={editing.id}
          hubs={hubs}
          order={editing}
          onSubmit={(input) => updateOrder(editing.id, input)}
          onDone={done}
          onCancel={close}
        />
      )}
      {deleting && (
        <ConfirmDelete
          subject={`order ${deleting.id}`}
          consequence="Only an order with no missions can be deleted; the backend refuses otherwise and nothing else is removed."
          busy={deletion.busy}
          error={deletion.error}
          onCancel={close}
          onConfirm={async () => {
            if (await deletion.run(() => deleteOrder(deleting.id))) done()
          }}
        />
      )}

      {orders.length === 0 ? (
        <p className="text-sm text-fg-muted">No orders yet. Create one to get started.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-fg-muted">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Order
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Origin Hub
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Delivery address
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Weight
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
              {orders.map((order) => {
                const eligible = isEligible(order)
                const display = ORDER_STATUS_DISPLAY[order.status]
                const reason = ordersWithMissions.has(order.id)
                  ? 'Has a mission'
                  : 'Only orders ready for pickup can be changed'
                return (
                  <tr key={order.id} className="border-t border-line">
                    <td className="py-1.5 pr-3 font-mono text-xs">{order.id}</td>
                    <td className="py-1.5 pr-3">
                      {hubNames.get(order.originHubId) ?? order.originHubId}
                    </td>
                    <td className="py-1.5 pr-3">{order.destinationAddress}</td>
                    <td className="py-1.5 pr-3">{order.packageWeightKg} kg</td>
                    <td className="py-1.5 pr-3">
                      <StatusIndicator tone={display.tone} label={display.label} />
                    </td>
                    <td className="py-1.5">
                      <div className="flex gap-3">
                        <button
                          type="button"
                          className={LINK_BUTTON_CLASS}
                          disabled={!eligible}
                          title={eligible ? undefined : reason}
                          aria-label={`Edit order ${order.id}`}
                          onClick={() => open({ kind: 'edit', id: order.id })}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className={LINK_BUTTON_CLASS}
                          disabled={!eligible}
                          title={eligible ? undefined : reason}
                          aria-label={`Delete order ${order.id}`}
                          onClick={() => open({ kind: 'delete', id: order.id })}
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
