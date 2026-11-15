import { useCallback, useRef, useState } from 'react'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import type { FocusNoticeData } from '../map/FocusNotice'
import { type FocusKind, type FocusRequest, resolveFocusTarget } from '../map/focusTarget'
import type { OperationsTab } from './tabs'

/** Only one Hub, drone or order is selected at a time, so only one detail panel can be open. */
type Selection =
  { kind: 'hub'; id: string } | { kind: 'drone'; id: string } | { kind: 'order'; id: string }

interface SelectionData {
  hubs: readonly Hub[]
  drones: readonly Drone[]
  orders: readonly Order[]
  /** The orders are known (loaded), so a selected order missing from them really is gone. */
  ordersReady: boolean
}

/**
 * Which Hub, drone or order is selected, the drone inspector above it, the Operations tab that
 * follows the selection, and the one-shot "fly the map there" command of the list clicks
 * (Feature 023). It owns state only; the data comes from the caller.
 */
export function useSelection({ hubs, drones, orders, ordersReady }: SelectionData) {
  const [selection, setSelection] = useState<Selection | null>(null)
  // The inspector opens above the selected drone's panel; the selection itself is never touched.
  const [inspectedDroneId, setInspectedDroneId] = useState<string | null>(null)
  // The Operations panel follows the selection (even while it is closed); the operator can still
  // switch tabs by hand without touching the selection.
  const [operationsTab, setOperationsTab] = useState<OperationsTab>('orders')

  const selectHub = useCallback((id: string) => {
    setSelection({ kind: 'hub', id })
    setOperationsTab('hubs')
  }, [])
  const selectDrone = useCallback((id: string) => {
    setSelection({ kind: 'drone', id })
    setOperationsTab('drones')
  }, [])
  const selectOrder = useCallback((id: string) => {
    setSelection({ kind: 'order', id })
    setOperationsTab('orders')
  }, [])
  const clearSelection = useCallback(() => {
    setInspectedDroneId(null)
    setSelection(null)
  }, [])
  const inspectDrone = useCallback((id: string) => setInspectedDroneId(id), [])
  const closeInspector = useCallback(() => setInspectedDroneId(null), [])

  // Feature 023: a click in an Operations list also moves the map camera there, once. A marker click
  // keeps the plain select above and never moves the camera. Every click gets a new `seq`, so
  // clicking the same row again flies again; a re-render or a data refresh keeps the same request
  // and moves nothing. An entity without a usable location leaves the camera alone and says so.
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null)
  const [focusNotice, setFocusNotice] = useState<FocusNoticeData | null>(null)
  const focusSeq = useRef(0)
  const dismissFocusNotice = useCallback(() => setFocusNotice(null), [])
  const locate = useCallback(
    (kind: FocusKind, id: string) => {
      const { label, position } = resolveFocusTarget(kind, id, { hubs, drones, orders })
      focusSeq.current += 1
      const seq = focusSeq.current
      if (position === null) {
        setFocusNotice({ seq, text: `The location of ${label} is not available.` })
        return
      }
      setFocusNotice(null)
      setFocusRequest({ kind, id, position, seq })
    },
    [hubs, drones, orders],
  )
  const focusHub = useCallback(
    (id: string) => {
      selectHub(id)
      locate('hub', id)
    },
    [selectHub, locate],
  )
  const focusDrone = useCallback(
    (id: string) => {
      selectDrone(id)
      locate('drone', id)
    },
    [selectDrone, locate],
  )
  const focusOrder = useCallback(
    (id: string) => {
      selectOrder(id)
      locate('order', id)
    },
    [selectOrder, locate],
  )

  const selectedHub =
    selection?.kind === 'hub' ? hubs.find((hub) => hub.id === selection.id) : undefined
  const selectedDrone =
    selection?.kind === 'drone' ? drones.find((drone) => drone.id === selection.id) : undefined
  const selectedOrder =
    selection?.kind === 'order' ? orders.find((order) => order.id === selection.id) : undefined
  // An order can leave the active list while selected (its delivered window ended). Drop the
  // selection then, once the orders are known, so no stale selection lingers. Adjusting state while
  // rendering is allowed.
  if (selection?.kind === 'order' && ordersReady && !selectedOrder) {
    setSelection(null)
  }
  // The inspector exists only for a drone that is still selected and still in the data.
  const inspectorOpen = selectedDrone !== undefined && inspectedDroneId === selectedDrone.id

  return {
    hasSelection: selection !== null,
    selectedHub,
    selectedDrone,
    selectedOrder,
    // The id of the selected entity of one kind, for marker and list highlighting.
    selectedHubId: selection?.kind === 'hub' ? selection.id : null,
    selectedDroneId: selection?.kind === 'drone' ? selection.id : null,
    selectedOrderId: selection?.kind === 'order' ? selection.id : null,
    selectHub,
    selectDrone,
    selectOrder,
    clearSelection,
    inspectorOpen,
    inspectDrone,
    closeInspector,
    operationsTab,
    setOperationsTab,
    focusRequest,
    focusNotice,
    dismissFocusNotice,
    focusHub,
    focusDrone,
    focusOrder,
  }
}
