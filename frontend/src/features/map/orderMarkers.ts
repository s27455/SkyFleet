import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY } from '../orders/orderStatus'
import { type PixelOffset, computeRingOffsets } from './droneMarkers'
import { ORDER_MARKER_STATES, orderMarkerState } from './orderMarkerState'

const ORDER_MARKER_SIZE_PX = 24

/** Ring offsets for destination markers that share an exact point (display only). */
export function computeOrderOffsets(
  orders: readonly Order[],
  hubs: readonly Hub[],
): ReadonlyMap<string, PixelOffset> {
  return computeRingOffsets(orders, hubs, ORDER_MARKER_SIZE_PX)
}

/** The status text comes first and the marker state follows, so the colour is also in words. */
export function orderMarkerLabel(order: Order, interrupted = false) {
  const state = ORDER_MARKER_STATES[orderMarkerState(order.status, interrupted)].label
  // An unknown status (a newer backend) is shown as the raw text instead of failing.
  const statusText = Object.hasOwn(ORDER_STATUS_DISPLAY, order.status)
    ? ORDER_STATUS_DISPLAY[order.status].label
    : order.status
  const reason =
    interrupted && order.status === 'OUT_FOR_DELIVERY'
      ? ', delivery interrupted by drone failure'
      : ''
  return `Order ${order.id} destination, ${statusText} (${state})${reason}, ${order.packageWeightKg} kg`
}

// The button is a transparent 24px target with a visible focus ring; the diamond inside is the mark.
// z-5 keeps destinations below Hub (z-10) and drone (z-20) markers.
const ORDER_MARKER_CLASS =
  'z-5 flex size-6 cursor-pointer items-center justify-center bg-transparent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
const DIAMOND_CLASS = 'size-3 rotate-45 border-2 shadow'
// Selection keeps the state colour and adds a ring: a second, non-colour cue.
const DIAMOND_SELECTED_CLASSES = ['ring-4', 'ring-accent']

const ALL_STATE_CLASSES = Object.values(ORDER_MARKER_STATES).flatMap(
  (style) => style.diamondClasses,
)

export function createOrderMarkerElement(order: Order, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = ORDER_MARKER_CLASS
  element.dataset.markerKind = 'order'
  const diamond = document.createElement('span')
  diamond.dataset.orderDiamond = ''
  diamond.setAttribute('aria-hidden', 'true')
  diamond.className = DIAMOND_CLASS
  element.appendChild(diamond)
  element.addEventListener('click', onClick)
  updateOrderMarkerElement(element, order)
  setOrderMarkerSelected(element, false)
  return element
}

/**
 * Applies the order's current state to an existing element: its colour, `data-order-state` and
 * accessible name. The element itself is kept, so keyboard focus and the click handler survive a
 * status change.
 */
export function updateOrderMarkerElement(element: HTMLElement, order: Order, interrupted = false) {
  const state = orderMarkerState(order.status, interrupted)
  const diamond = element.querySelector<HTMLElement>('[data-order-diamond]')
  diamond?.classList.remove(...ALL_STATE_CLASSES)
  diamond?.classList.add(...ORDER_MARKER_STATES[state].diamondClasses)
  element.dataset.orderState = state
  element.setAttribute('aria-label', orderMarkerLabel(order, interrupted))
}

/** Updates the existing element in place so keyboard focus survives a selection change. */
export function setOrderMarkerSelected(element: HTMLElement, selected: boolean) {
  const diamond = element.querySelector<HTMLElement>('[data-order-diamond]')
  if (selected) diamond?.classList.add(...DIAMOND_SELECTED_CLASSES)
  else diamond?.classList.remove(...DIAMOND_SELECTED_CLASSES)
  element.setAttribute('aria-pressed', String(selected))
}
