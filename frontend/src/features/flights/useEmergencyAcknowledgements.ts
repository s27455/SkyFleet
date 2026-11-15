import { useCallback, useRef, useState } from 'react'

import { acknowledgeEmergency } from '../../api/acknowledgements'
import { describeApiError } from '../../api/client'

const withMember = (set: ReadonlySet<string>, id: string) => new Set(set).add(id)
const withoutMember = (set: ReadonlySet<string>, id: string) => {
  const next = new Set(set)
  next.delete(id)
  return next
}

/**
 * Acknowledging emergency alerts (Feature 022), one request per alert.
 *
 * An alert is only reported `confirmed` after the backend confirmed the acknowledgement, never
 * before. `confirmed` is kept for the life of the page on purpose: a flights answer that was
 * requested before the confirmation can still arrive afterwards and say "not acknowledged", and it
 * must not bring the alert back. The server remains the source of truth across reloads, through
 * `emergency.acknowledgedAt` of the flights it returns. While a request is pending a second click
 * does nothing, and a failure leaves the alert visible with a message to try again.
 * `onConfirmed` must be a stable reference (the polled resource's `refresh` is).
 */
export function useEmergencyAcknowledgements(onConfirmed: () => void) {
  const [confirmed, setConfirmed] = useState<ReadonlySet<string>>(new Set())
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set())
  const [failed, setFailed] = useState<ReadonlyMap<string, string>>(new Map())
  // Checked synchronously, so two quick clicks cannot both start a request.
  const inFlight = useRef(new Set<string>())

  const acknowledge = useCallback(
    async (missionId: string) => {
      if (inFlight.current.has(missionId)) return
      inFlight.current.add(missionId)
      setPending((previous) => withMember(previous, missionId))
      setFailed((previous) => {
        const next = new Map(previous)
        next.delete(missionId)
        return next
      })
      try {
        await acknowledgeEmergency(missionId)
        setConfirmed((previous) => withMember(previous, missionId))
        onConfirmed() // read the flights again: the server now reports it as acknowledged
      } catch (error) {
        setFailed((previous) => new Map(previous).set(missionId, describeApiError(error)))
      } finally {
        inFlight.current.delete(missionId)
        setPending((previous) => withoutMember(previous, missionId))
      }
    },
    [onConfirmed],
  )

  return { confirmed, pending, failed, acknowledge }
}
