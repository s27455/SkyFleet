import type { StatusTone } from '../../components/ui/StatusIndicator'
import type { HealthLevel } from './deriveTelemetry'

export const LEVEL_DISPLAY: Record<HealthLevel, { tone: StatusTone; label: string }> = {
  nominal: { tone: 'ok', label: 'Nominal' },
  attention: { tone: 'warning', label: 'Attention' },
  critical: { tone: 'critical', label: 'Critical' },
}

export const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

export const power = (watts: number) =>
  watts >= 100 ? `${integer.format(watts)} W` : `${watts.toFixed(1)} W`
