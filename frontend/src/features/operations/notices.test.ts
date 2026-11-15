import { describe, expect, it } from 'vitest'

import type { Flight } from '../../types/flight'
import { buildNotices } from './notices'

const NOTICE_BASE = {
  rainWarningActive: false,
  lprActive: false,
  flightsUnavailable: false,
  flightsStale: false,
  fleetStale: false,
  workerStoppedWhileFlying: false,
}

const emergency = (missionId: string, acknowledgedAt: string | null): Flight =>
  ({
    missionId,
    droneId: `DRN-${missionId}`,
    emergency: {
      reason: 'DRONE_FAILURE',
      at: '2026-11-15T10:00:00Z',
      position: [18.6, 54.4],
      acknowledgedAt,
    },
  }) as unknown as Flight

describe('buildNotices and acknowledgements (Feature 022)', () => {
  it('keeps an acknowledged emergency in the Events notices: acknowledging only hides the overlay', () => {
    const notices = buildNotices({
      ...NOTICE_BASE,
      emergencies: [emergency('A', '2026-11-15T10:05:00Z'), emergency('B', null)],
    })

    expect(notices.map((notice) => notice.id)).toEqual(['emergency-A', 'emergency-B'])
  })

  it('still reports rain and the LPR helicopter next to emergencies', () => {
    const notices = buildNotices({
      ...NOTICE_BASE,
      emergencies: [emergency('A', null)],
      rainWarningActive: true,
      lprActive: true,
    })

    expect(notices.map((notice) => notice.id)).toEqual(['emergency-A', 'rain', 'lpr'])
  })
})
