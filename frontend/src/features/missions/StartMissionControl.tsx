import { useEffect, useRef, useState } from 'react'

import { StartMissionError } from '../../api/missions'
import type { Mission } from '../../types/mission'
import { TAKEOFFS_SUSPENDED_REASON, useTakeoffsSuspended } from '../weather/TakeoffGate'

interface StartMissionControlProps {
  /** An `ASSIGNED` mission: the backend validates and performs the start. */
  mission: Mission
  /** The planned return Hub's name, if the Hub data is available. */
  returnHubName?: string
  /** Starts the mission; rejects with a `StartMissionError` whose message can be shown as is. */
  onStart: (missionId: string) => Promise<void>
}

/**
 * Temporary demonstration control: it starts one already assigned mission and nothing else (it
 * neither picks a drone nor assigns an order). Automatic dispatch will later start missions through
 * the same backend action, so this control is never a required step.
 */
export function StartMissionControl({ mission, returnHubName, onStart }: StartMissionControlProps) {
  const suspended = useTakeoffsSuspended()
  const [pending, setPending] = useState(false)
  // After a successful start the button stays off until the mission is no longer ASSIGNED (the
  // panel then drops this control), so a slow refresh can never invite a second, refused click.
  const [started, setStarted] = useState(false)
  const [error, setError] = useState<StartMissionError | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const start = async () => {
    setPending(true)
    setError(null)
    try {
      await onStart(mission.id)
      if (mounted.current) setStarted(true)
    } catch (caught) {
      if (!mounted.current) return
      setError(
        caught instanceof StartMissionError
          ? caught
          : new StartMissionError('UNKNOWN', 'The mission could not be started.'),
      )
    } finally {
      if (mounted.current) setPending(false)
    }
  }

  return (
    <section
      aria-label={`Mission ${mission.id}`}
      className="mt-3 border-t border-line pt-3 text-sm"
    >
      <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">
        Mission assigned
      </h3>
      <p className="mt-1">
        <span className="font-mono">{mission.id}</span> · {mission.totalKm.toFixed(1)} km planned ·
        returns to {returnHubName ?? mission.returnHubId}
      </p>
      <p className="mt-1 text-xs text-fg-muted">
        The return Hub is planned, not reserved. Starting is a temporary demonstration action.
      </p>
      <button
        type="button"
        onClick={start}
        disabled={pending || started || suspended}
        aria-label={`Start mission ${mission.id}`}
        className="mt-2 inline-flex min-h-10 items-center rounded-md border border-line bg-surface-raised px-3 font-medium hover:bg-line focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-60"
      >
        {pending ? 'Starting…' : started ? 'Mission started' : 'Start mission'}
      </button>
      {suspended && !started && (
        <p className="mt-1 text-xs text-fg-muted">
          {TAKEOFFS_SUSPENDED_REASON} The mission stays assigned.
        </p>
      )}
      {error && (
        <div role="alert" className="mt-2 rounded-md border border-line bg-canvas p-2 text-xs">
          <p>{error.message}</p>
          {error.reasons.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {error.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
