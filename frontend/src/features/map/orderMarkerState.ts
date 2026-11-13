import type { OrderStatus } from '../../types/order'

/** What a destination marker tells the operator. Styling lives apart, in `ORDER_MARKER_STATES`. */
export type OrderMarkerState =
  'pending' | 'in_progress' | 'delivered' | 'cancelled' | 'interrupted' | 'other'

/**
 * Backend order status to marker state, written out for every status (Feature 017B). Only the
 * order status decides: an order whose mission is merely assigned is still READY_FOR_PICKUP and
 * stays "waiting" until takeoff. When the backend adds a status, TypeScript flags this table.
 */
const STATE_BY_STATUS: Record<OrderStatus, OrderMarkerState> = {
  CREATED: 'pending',
  AWAITING_HANDOVER: 'pending',
  READY_FOR_PICKUP: 'pending',
  OUT_FOR_DELIVERY: 'in_progress',
  DELIVERED: 'delivered',
  CANCELLED: 'cancelled',
}

/** A status this build does not know (a newer backend) is shown neutrally, never guessed. */
export function orderMarkerState(status: string, interrupted = false): OrderMarkerState {
  // A drone failure (Feature 018C) interrupts a delivery without changing the order status, so the
  // interruption comes from the flight. A cancelled or delivered order keeps its own state.
  if (interrupted && status === 'OUT_FOR_DELIVERY') return 'interrupted'
  return Object.hasOwn(STATE_BY_STATUS, status) ? STATE_BY_STATUS[status as OrderStatus] : 'other'
}

export interface OrderMarkerStyle {
  /** Short text for the legend and the marker's accessible name (never colour alone). */
  label: string
  /** Fill and outline classes of the diamond when the marker is not selected. */
  diamondClasses: readonly string[]
  /** Legend swatch fill. */
  swatchClass: string
}

export const ORDER_MARKER_STATES: Record<OrderMarkerState, OrderMarkerStyle> = {
  pending: {
    label: 'Waiting',
    diamondClasses: ['bg-status-neutral', 'border-fg'],
    swatchClass: 'bg-status-neutral',
  },
  in_progress: {
    label: 'In delivery',
    diamondClasses: ['bg-status-active', 'border-fg'],
    swatchClass: 'bg-status-active',
  },
  delivered: {
    label: 'Delivered',
    diamondClasses: ['bg-status-ok', 'border-fg'],
    swatchClass: 'bg-status-ok',
  },
  cancelled: {
    label: 'Cancelled',
    diamondClasses: ['bg-status-critical', 'border-fg'],
    swatchClass: 'bg-status-critical',
  },
  interrupted: {
    label: 'Interrupted',
    diamondClasses: ['bg-status-warning', 'border-status-critical'],
    swatchClass: 'bg-status-warning',
  },
  other: {
    label: 'Other',
    diamondClasses: ['bg-surface', 'border-fg-muted'],
    swatchClass: 'bg-surface',
  },
}
