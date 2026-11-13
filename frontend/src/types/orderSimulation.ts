/** Mirrors `OrderSimulationStatus` in backend/app/orders/schemas.py (`GET /api/orders/simulation/status`). */
export interface OrderSimulationStatusResponse {
  enabled: boolean
  worker_running: boolean
  last_check_at: string | null
  last_outcome: string | null
  outstanding_orders: number
  max_outstanding_orders: number
}

/** What the server is actually doing; the UI never assumes it. */
export interface OrderSimulationStatus {
  /** True only while the mode is ON and the simulation worker (the loop's owner) is alive. */
  enabled: boolean
  workerRunning: boolean
  /** ISO 8601 time of the last automatic generation attempt, or null if there has been none. */
  lastCheckAt: string | null
  /** A short summary of the last attempt (an order created, or why not), written by the backend. */
  lastOutcome: string | null
  /** Every READY_FOR_PICKUP order, however it was created. */
  outstandingOrders: number
  /** Automatic generation pauses while `outstandingOrders` is at this limit. */
  maxOutstandingOrders: number
}
