/** Why a relocation is not possible; mirrors `RelocationReasonCode` in the backend. */
export interface RelocationReason {
  code: string
  message: string
}

/** UI model of `GET /api/drones/{id}/relocation-plan` (Feature 019A): a read-only preview. */
export interface RelocationPlan {
  droneId: string
  eligible: boolean
  reasons: RelocationReason[]
  /** The Hub the drone is docked at now; null when it is not docked. */
  originHubId: string | null
  destinationHubId: string
  distanceKm: number
  requiredBatteryPct: number
  /** Simulation estimate at the empty-flight rate, not certified performance. */
  expectedBatteryUsePct: number
  droneBatteryPct: number
  destinationDockedDrones: number
  destinationCapacity: number
  warnings: string[]
}

/** UI model of `POST /api/drones/{id}/relocate`. */
export interface RelocationStarted {
  missionId: string
  droneId: string
  originHubId: string
  destinationHubId: string
}
