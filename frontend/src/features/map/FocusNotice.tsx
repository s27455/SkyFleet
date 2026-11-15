import { useEffect } from 'react'

/** A message that the map could not be moved, with a number that is new for every click. */
export interface FocusNoticeData {
  seq: number
  text: string
}

/** How long the message stays; it is only a hint, so it goes away by itself. */
export const FOCUS_NOTICE_MS = 5000

interface FocusNoticeProps {
  notice: FocusNoticeData | null
  onDismiss: () => void
}

/**
 * A small status line for "this entity has no usable location" (Feature 023). The camera stays
 * where it is. It is announced politely to assistive technology, never steals focus, and can be
 * closed; a new notice (even with the same text) starts its own timer.
 */
export function FocusNotice({ notice, onDismiss }: FocusNoticeProps) {
  const seq = notice?.seq
  useEffect(() => {
    if (seq === undefined) return
    const timer = setTimeout(onDismiss, FOCUS_NOTICE_MS)
    return () => clearTimeout(timer)
  }, [seq, onDismiss])

  if (!notice) return null
  return (
    <div
      role="status"
      className="flex items-start justify-between gap-2 rounded-lg border border-line bg-surface p-2 text-xs text-fg-muted shadow-lg sm:p-3 sm:text-sm"
    >
      <p>{notice.text}</p>
      <button
        type="button"
        aria-label="Dismiss location message"
        onClick={onDismiss}
        className="inline-flex min-h-10 min-w-10 shrink-0 items-center justify-center rounded-md hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  )
}
