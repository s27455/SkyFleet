import type { StatusTone } from '../../components/ui/StatusIndicator'
import type { DroneStatus } from '../../types/drone'

/** Backend status as readable text (always shown as text, never by colour alone). */
export const DRONE_STATUS_DISPLAY: Record<DroneStatus, { tone: StatusTone; label: string }> = {
  IDLE: { tone: 'neutral', label: 'Idle' },
  IN_FLIGHT: { tone: 'ok', label: 'In flight' },
  CHARGING: { tone: 'warning', label: 'Charging' },
  MAINTENANCE: { tone: 'warning', label: 'Maintenance' },
}
