import { StatusIndicator, type StatusTone } from '../../components/ui/StatusIndicator'
import { type BackendHealth, useBackendHealth } from './useBackendHealth'

const DISPLAY: Record<BackendHealth, { tone: StatusTone; label: string }> = {
  checking: { tone: 'neutral', label: 'Connecting to backend…' },
  connected: { tone: 'ok', label: 'Backend connected' },
  unreachable: { tone: 'critical', label: 'Backend unreachable' },
}

export function BackendStatus() {
  const { tone, label } = DISPLAY[useBackendHealth()]

  return (
    <div role="status" aria-live="polite">
      <StatusIndicator tone={tone} label={label} />
    </div>
  )
}
