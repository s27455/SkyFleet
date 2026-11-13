/** The LPR helicopter scenario with the helicopter's position at the response (Feature 018E). */
export interface LprScenario {
  id: string
  /** ISO 8601, as sent by the backend. */
  startedAt: string
  endsAt: string
  /** [longitude, latitude] of the helicopter when the backend answered. */
  position: [longitude: number, latitude: number]
  routeStart: [longitude: number, latitude: number]
  routeEnd: [longitude: number, latitude: number]
  /** Fictional simulation values, in metres per second and metres. */
  speedMs: number
  /** The drawn safety zone; drones stop `holdMarginM` outside it. */
  radiusM: number
  holdMarginM: number
}

export interface LprStatus {
  /** The running scenario, or null when the helicopter is not crossing the area. */
  scenario: LprScenario | null
}
