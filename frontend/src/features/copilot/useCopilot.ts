import { useCallback, useRef, useState } from 'react'

import { askCopilot, getCopilotStatus, toCopilotFailure } from '../../api/copilot'
import type { CopilotAnswer, CopilotFailure } from '../../types/copilot'

export type Availability = 'unknown' | 'checking' | 'available' | 'unavailable' | 'error'

export type CopilotView =
  | { phase: 'idle' }
  | { phase: 'pending'; question: string }
  | { phase: 'answered'; question: string; result: CopilotAnswer }
  | { phase: 'failed'; question: string; failure: CopilotFailure }

export interface CopilotController {
  availability: Availability
  /** Asks the server whether the Copilot can answer at all (once; never a model call). */
  checkAvailability: () => void
  hasToken: boolean
  /** Keeps the operator token in memory only: never stored, never put in a URL. */
  setToken: (token: string) => void
  forgetToken: () => void
  draft: string
  setDraft: (draft: string) => void
  view: CopilotView
  pending: boolean
  /** Sends ONE question. Ignored while another is pending: there is no queue and no retry. */
  ask: (question: string) => void
}

/**
 * The Copilot's whole state, meant to live ABOVE the Operations tabs (in `App`) so that switching
 * tabs, or a map selection that switches them, never loses a draft, an answer or a request that is
 * still on its way (which is charged whether or not anybody is looking).
 *
 * What it never does: fetch anything on mount, retry anything, abort a request, or keep the token
 * anywhere but in memory (a ref for the request and state for the "token set" display; the value
 * itself is never exposed to the components).
 */
export function useCopilot(): CopilotController {
  const [availability, setAvailability] = useState<Availability>('unknown')
  const [hasToken, setHasToken] = useState(false)
  const [draft, setDraft] = useState('')
  const [view, setView] = useState<CopilotView>({ phase: 'idle' })
  const tokenRef = useRef('')
  const inFlightRef = useRef(false)
  const statusRequestedRef = useRef(false)

  const checkAvailability = useCallback(() => {
    if (statusRequestedRef.current) return
    statusRequestedRef.current = true
    setAvailability('checking')
    getCopilotStatus().then(
      (available) => setAvailability(available ? 'available' : 'unavailable'),
      () => {
        statusRequestedRef.current = false // a status probe is harmless to repeat
        setAvailability('error')
      },
    )
  }, [])

  const setToken = useCallback((token: string) => {
    tokenRef.current = token
    setHasToken(token !== '')
  }, [])

  const forgetToken = useCallback(() => setToken(''), [setToken])

  const ask = useCallback(
    (question: string) => {
      const text = question.trim()
      // the ref (not state) is the guard: two clicks in the same tick must still send one request
      if (inFlightRef.current || text === '' || tokenRef.current === '') return
      inFlightRef.current = true
      setView({ phase: 'pending', question: text })
      askCopilot(text, tokenRef.current)
        .then((result) => setView({ phase: 'answered', question: text, result }))
        .catch((error: unknown) => {
          const failure = toCopilotFailure(error)
          setView({ phase: 'failed', question: text, failure })
          if (failure.code === 'UNAUTHORIZED') setToken('') // enter it again
        })
        .finally(() => {
          inFlightRef.current = false
        })
    },
    [setToken],
  )

  return {
    availability,
    checkAvailability,
    hasToken,
    setToken,
    forgetToken,
    draft,
    setDraft,
    view,
    pending: view.phase === 'pending',
    ask,
  }
}
