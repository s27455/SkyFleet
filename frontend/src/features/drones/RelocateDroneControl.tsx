import { useEffect, useId, useRef, useState } from 'react'

import { getRelocationPlan, RelocateError, relocateDrone } from '../../api/relocation'
import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { RelocationPlan } from '../../types/relocation'
import { INPUT_CLASS, PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { TAKEOFFS_SUSPENDED_REASON, useTakeoffsSuspended } from '../weather/TakeoffGate'

interface RelocateDroneControlProps {
  drone: Drone
  hubs: readonly Hub[]
  /** Why the action is unavailable for this drone right now (a hint; the backend decides). */
  unavailableReason?: string
  /** Called after a start (or a refused start) so the polled data is re-read at once. */
  onChanged: () => void
}

type PlanState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; plan: RelocationPlan }
  | { status: 'error' }

/**
 * Manual relocation (Feature 019A): the operator picks another Hub, sees whether the backend would
 * accept it, and confirms. The backend validates again and starts an empty, timed flight; the
 * drone keeps its current Hub until it lands. Nothing here decides eligibility.
 */
export function RelocateDroneControl({
  drone,
  hubs,
  unavailableReason: reason,
  onChanged,
}: RelocateDroneControlProps) {
  // A rain warning suspends new takeoffs, a relocation included; the backend refuses it anyway.
  const unavailableReason = useTakeoffsSuspended() ? TAKEOFFS_SUSPENDED_REASON : reason
  const selectId = useId()
  const [open, setOpen] = useState(false)
  const [destinationId, setDestinationId] = useState('')
  const [planState, setPlanState] = useState<PlanState>({ status: 'idle' })
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<RelocateError | null>(null)
  const [startedTo, setStartedTo] = useState<string | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  // Preview the chosen destination (read-only). A newer choice cancels the older request.
  useEffect(() => {
    if (!open || destinationId === '') return
    const controller = new AbortController()
    getRelocationPlan(drone.id, destinationId, controller.signal)
      .then((plan) => setPlanState({ status: 'ready', plan }))
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setPlanState({ status: 'error' })
      })
    return () => controller.abort()
  }, [open, destinationId, drone.id])

  const hubName = (id: string | null) => hubs.find((hub) => hub.id === id)?.name ?? id ?? 'a Hub'
  const options = hubs.filter((hub) => hub.id !== drone.hubId)

  const choose = (id: string) => {
    setDestinationId(id)
    setError(null)
    setPlanState(id === '' ? { status: 'idle' } : { status: 'loading' })
  }

  const close = () => {
    setOpen(false)
    setDestinationId('')
    setPlanState({ status: 'idle' })
    setError(null)
  }

  const confirm = async () => {
    setPending(true)
    setError(null)
    try {
      const started = await relocateDrone(drone.id, destinationId)
      if (!mounted.current) return
      setStartedTo(started.destinationHubId)
      close()
    } catch (caught) {
      if (!mounted.current) return
      setError(
        caught instanceof RelocateError
          ? caught
          : new RelocateError('The relocation could not be started.'),
      )
    } finally {
      if (mounted.current) setPending(false)
      onChanged() // show the outcome now, whatever it was: a refused start may mean state changed
    }
  }

  // While the relocation flies the flight section tells the story; keep only the confirmation.
  if (drone.status === 'IN_FLIGHT' && startedTo === null) return null

  const plan = planState.status === 'ready' ? planState.plan : null
  const canConfirm = plan?.eligible === true && !pending

  return (
    <section aria-label="Relocate drone" className="mt-3 border-t border-line pt-3 text-sm">
      <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">Relocate</h3>
      {startedTo !== null && (
        <p role="status" className="mt-1 text-xs">
          Relocation started: {drone.id} is flying to {hubName(startedTo)}. It keeps its current Hub
          until it lands.
        </p>
      )}
      {!open && (
        <>
          <button
            type="button"
            onClick={() => {
              setStartedTo(null)
              setOpen(true)
            }}
            disabled={unavailableReason !== undefined || drone.status === 'IN_FLIGHT'}
            aria-label={`Relocate ${drone.id}`}
            className="mt-2 inline-flex min-h-10 items-center rounded-md border border-line bg-surface-raised px-3 font-medium hover:bg-line focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            Relocate
          </button>
          {unavailableReason !== undefined && (
            <p className="mt-1 text-xs text-fg-muted">{unavailableReason}</p>
          )}
        </>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          <label htmlFor={selectId} className="flex flex-col gap-1 text-xs text-fg-muted">
            Destination Hub
            <select
              id={selectId}
              value={destinationId}
              onChange={(event) => choose(event.target.value)}
              disabled={pending}
              className={INPUT_CLASS}
            >
              <option value="">Choose a Hub…</option>
              {options.map((hub) => (
                <option key={hub.id} value={hub.id}>
                  {hub.name}
                </option>
              ))}
            </select>
          </label>
          {planState.status === 'loading' && (
            <p role="status" className="text-xs text-fg-muted">
              Checking the relocation…
            </p>
          )}
          {planState.status === 'error' && (
            <p role="alert" className="text-xs">
              The relocation could not be checked. Choose the Hub again to retry.
            </p>
          )}
          {plan && (
            <div className="rounded-md border border-line bg-canvas p-2 text-xs">
              <p>
                {hubName(plan.originHubId)} → {hubName(plan.destinationHubId)} ·{' '}
                {plan.distanceKm.toFixed(1)} km · about {Math.round(plan.expectedBatteryUsePct)}%
                battery (estimate; {plan.droneBatteryPct}% now)
              </p>
              <p className="mt-1 text-fg-muted">
                Destination: {plan.destinationDockedDrones} of {plan.destinationCapacity} places
                taken.
              </p>
              {!plan.eligible && (
                <ul className="mt-1 list-disc pl-4">
                  {plan.reasons.map((reason) => (
                    <li key={reason.code}>{reason.message}</li>
                  ))}
                </ul>
              )}
              {plan.warnings.length > 0 && (
                <ul className="mt-1 list-disc pl-4 text-fg-muted">
                  {plan.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {error && (
            <div role="alert" className="rounded-md border border-line bg-canvas p-2 text-xs">
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
          <div className="flex gap-2">
            <button
              type="button"
              onClick={confirm}
              disabled={!canConfirm}
              className={PRIMARY_BUTTON_CLASS}
            >
              {pending ? 'Starting…' : 'Start relocation'}
            </button>
            <button
              type="button"
              onClick={close}
              disabled={pending}
              className={SECONDARY_BUTTON_CLASS}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
