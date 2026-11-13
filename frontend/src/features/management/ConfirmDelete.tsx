import { DANGER_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from './formStyles'

interface ConfirmDeleteProps {
  /** What is about to be deleted, e.g. "order ORD-1234". */
  subject: string
  /** Consequences and limits, in plain words. */
  consequence: string
  busy: boolean
  error: string | null
  onConfirm: () => void
  onCancel: () => void
}

/** Inline confirmation for a permanent deletion; the backend still decides whether it is allowed. */
export function ConfirmDelete({
  subject,
  consequence,
  busy,
  error,
  onConfirm,
  onCancel,
}: ConfirmDeleteProps) {
  return (
    <div
      role="alertdialog"
      aria-label={`Confirm deleting ${subject}`}
      className="flex flex-col gap-2 rounded border border-status-critical p-3 text-sm"
    >
      <p>
        Delete <strong>{subject}</strong> permanently? {consequence}
      </p>
      {error && (
        <p role="alert" className="text-status-critical">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button type="button" className={DANGER_BUTTON_CLASS} disabled={busy} onClick={onConfirm}>
          {busy ? 'Deleting…' : 'Delete permanently'}
        </button>
        <button
          type="button"
          autoFocus
          className={SECONDARY_BUTTON_CLASS}
          disabled={busy}
          onClick={onCancel}
        >
          Keep
        </button>
      </div>
    </div>
  )
}
