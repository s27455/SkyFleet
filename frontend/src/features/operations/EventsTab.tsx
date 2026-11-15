import { EventTimeline } from '../events/EventTimeline'
import type { OperationalNotice } from './notices'

const TONE_CLASS = {
  critical: 'border-status-critical',
  warning: 'border-status-warning',
  info: 'border-line',
} as const

export type ActivitySubject = { kind: 'drone' | 'order'; id: string }

interface EventsTabProps {
  notices: readonly OperationalNotice[]
  /** The selected drone or order, whose recorded activity is shown; null when neither is selected. */
  activity: ActivitySubject | null
  activityRefreshKey: number
}

/**
 * Current alerts and the recorded activity of the selected drone or order. It is not a history of
 * all simulation events: the API offers events per order, drone, mission or type, not globally.
 * The always-visible alerts over the map are unaffected by this tab.
 */
export function EventsTab({ notices, activity, activityRefreshKey }: EventsTabProps) {
  return (
    <div className="p-3 text-sm">
      <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">
        Current alerts
      </h3>
      {notices.length === 0 ? (
        <p className="mt-1 text-xs text-fg-muted">No active alerts.</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {notices.map((notice) => (
            <li
              key={notice.id}
              className={`rounded border-l-4 bg-surface-raised px-2 py-1 text-xs ${TONE_CLASS[notice.tone]}`}
            >
              {notice.text}
            </li>
          ))}
        </ul>
      )}

      {activity === null ? (
        <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
          Select a drone or an order to see its recorded activity here.
        </p>
      ) : activity.kind === 'drone' ? (
        <EventTimeline
          key={`drone-${activity.id}`}
          droneId={activity.id}
          refreshKey={activityRefreshKey}
        />
      ) : (
        <EventTimeline
          key={`order-${activity.id}`}
          orderId={activity.id}
          refreshKey={activityRefreshKey}
        />
      )}
    </div>
  )
}
