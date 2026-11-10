export type StatusTone = 'ok' | 'warning' | 'critical' | 'neutral'

const DOT_CLASS: Record<StatusTone, string> = {
  ok: 'bg-status-ok',
  warning: 'bg-status-warning',
  critical: 'bg-status-critical',
  neutral: 'bg-status-neutral',
}

interface StatusIndicatorProps {
  tone: StatusTone
  label: string
}

/** Coloured dot + text label, so status never relies on colour alone. */
export function StatusIndicator({ tone, label }: StatusIndicatorProps) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-fg-muted">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT_CLASS[tone]}`} />
      {label}
    </span>
  )
}
