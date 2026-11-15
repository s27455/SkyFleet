import { useEffect, useId, useState } from 'react'

import { CHARGE_WARNING } from '../../api/copilot'
import type { CopilotAnswer, CopilotFailure } from '../../types/copilot'
import { describeLimitation } from './limitationText'
import type { CopilotController } from './useCopilot'

const MAX_QUESTION_CHARS = 500

/** `2026-11-15T14:03:07Z` as `2026-11-15 14:03:07 UTC`; anything else is shown as it came. */
function formatCapturedAt(iso: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})Z$/.exec(iso)
  return match ? `${match[1]} ${match[2]} UTC` : iso
}

const OMITTED_LABELS = {
  drones: 'drones',
  hubs: 'Hubs',
  activeIncidents: 'active incidents',
  recoveredAlerts: 'recovered alerts',
} as const

function SnapshotNotes({ snapshot }: { snapshot: CopilotAnswer['snapshot'] }) {
  const omitted = (Object.keys(OMITTED_LABELS) as (keyof typeof OMITTED_LABELS)[]).filter(
    (key) => snapshot.omitted[key] > 0,
  )
  const missingNamed = snapshot.namedDrones.filter((drone) => !drone.exists)
  const unlistedNamed = snapshot.namedDrones.filter((drone) => drone.exists && !drone.listed)
  const clean =
    snapshot.dataStatus === 'complete' &&
    !snapshot.truncated &&
    snapshot.limitations.length === 0 &&
    omitted.length === 0 &&
    missingNamed.length === 0 &&
    unlistedNamed.length === 0
  return (
    <div className="mt-2 flex flex-col gap-1 border-t border-line pt-2 text-xs">
      <p>
        <span className="font-medium">Snapshot taken</span> {formatCapturedAt(snapshot.capturedAt)}
        {clean && <span className="text-fg-muted"> — complete.</span>}
      </p>
      {snapshot.dataStatus === 'degraded' && (
        <p className="rounded border border-status-warning bg-status-warning/15 px-2 py-1">
          <span className="font-medium">Degraded data:</span> read the notes below before trusting
          any number in the answer.
        </p>
      )}
      {snapshot.truncated && (
        <p className="rounded border border-status-warning bg-status-warning/15 px-2 py-1">
          <span className="font-medium">Truncated snapshot:</span> some entries were left out to fit
          the request size limit.
        </p>
      )}
      {(snapshot.limitations.length > 0 ||
        omitted.length > 0 ||
        missingNamed.length > 0 ||
        unlistedNamed.length > 0) && (
        <ul className="list-disc pl-4 text-fg-muted">
          {snapshot.limitations.map((code) => (
            <li key={code}>{describeLimitation(code)}</li>
          ))}
          {omitted.map((key) => (
            <li key={key}>
              {snapshot.omitted[key]} {OMITTED_LABELS[key]} are not in the snapshot.
            </li>
          ))}
          {missingNamed.map((drone) => (
            <li key={`missing-${drone.id}`}>{drone.id} is not in the fleet.</li>
          ))}
          {unlistedNamed.map((drone) => (
            <li key={`unlisted-${drone.id}`}>
              {drone.id} was not included in the snapshot, so the answer cannot describe it.
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Answer({ question, result }: { question: string; result: CopilotAnswer }) {
  return (
    <article
      aria-label="Copilot answer"
      className="rounded border border-line bg-surface-raised p-2"
    >
      <p className="text-[11px] break-words text-fg-muted">You asked: {question}</p>
      {/* Model output is untrusted: a text node only, so markup in it is shown, never run. */}
      <p data-testid="copilot-answer" className="mt-1 break-words whitespace-pre-wrap">
        {result.answer}
      </p>
      {result.answerCut && (
        <p className="mt-1 text-xs text-status-warning">
          The answer was cut short at the length limit.
        </p>
      )}
      <SnapshotNotes snapshot={result.snapshot} />
      <p className="mt-2 text-[11px] text-fg-muted">
        AI-generated text based on the snapshot only. It may be wrong and it never acts.
      </p>
    </article>
  )
}

function Failure({ failure }: { failure: CopilotFailure }) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-1 rounded border border-status-critical bg-status-critical/10 p-2"
    >
      <p>{failure.message}</p>
      {failure.retryAfterSeconds !== null && <p>Try again in {failure.retryAfterSeconds} s.</p>}
      {failure.chargePossible && <p className="font-medium">{CHARGE_WARNING}</p>}
    </div>
  )
}

function TokenControl({ copilot }: { copilot: CopilotController }) {
  const id = useId()
  const [value, setValue] = useState('')
  if (copilot.hasToken) {
    return (
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-fg-muted">Access token set (kept in memory only).</span>
        <button
          type="button"
          onClick={copilot.forgetToken}
          className="min-h-8 rounded border border-line px-2 hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
        >
          Forget token
        </button>
      </div>
    )
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        const token = value.trim()
        if (token === '') return
        copilot.setToken(token)
        setValue('')
      }}
      className="flex flex-col gap-1"
    >
      <label htmlFor={`${id}-token`} className="text-xs text-fg-muted">
        Access token
      </label>
      <div className="flex gap-2">
        <input
          id={`${id}-token`}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby={`${id}-token-help`}
          className="min-h-9 min-w-0 flex-1 rounded border border-line bg-surface-raised px-2 focus-visible:outline-2 focus-visible:outline-accent"
        />
        <button
          type="submit"
          disabled={value.trim() === ''}
          className="min-h-9 rounded border border-line px-3 hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50"
        >
          Use token
        </button>
      </div>
      <p id={`${id}-token-help`} className="text-[11px] text-fg-muted">
        Set by whoever runs the server. It stays in memory only: reloading the page clears it.
      </p>
    </form>
  )
}

function QuestionForm({ copilot }: { copilot: CopilotController }) {
  const id = useId()
  const { draft, pending, hasToken } = copilot
  const canAsk = hasToken && !pending && draft.trim() !== ''
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        copilot.ask(draft)
      }}
      className="flex flex-col gap-1"
    >
      <label htmlFor={`${id}-question`} className="text-xs text-fg-muted">
        Question
      </label>
      <div className="flex gap-2">
        <input
          id={`${id}-question`}
          type="text"
          maxLength={MAX_QUESTION_CHARS}
          value={draft}
          disabled={pending}
          onChange={(event) => copilot.setDraft(event.target.value)}
          placeholder="e.g. Which drones need attention?"
          aria-describedby={`${id}-count`}
          className="min-h-9 min-w-0 flex-1 rounded border border-line bg-surface-raised px-2 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={!canAsk}
          aria-busy={pending}
          className="min-h-9 rounded border border-line bg-surface-raised px-3 font-medium hover:bg-line focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50"
        >
          {pending ? 'Asking…' : 'Ask'}
        </button>
      </div>
      <p id={`${id}-count`} className="text-[11px] text-fg-muted">
        {draft.length}/{MAX_QUESTION_CHARS} characters. One question at a time; each is sent once
        and never retried automatically.
        {!hasToken && ' Enter the access token first.'}
      </p>
    </form>
  )
}

function Result({ copilot }: { copilot: CopilotController }) {
  const { view } = copilot
  return (
    <div aria-live="polite" className="flex flex-col gap-2">
      {view.phase === 'pending' && (
        <p role="status" className="text-fg-muted">
          Waiting for the answer. The question is sent once and is never retried automatically.
        </p>
      )}
      {view.phase === 'answered' && <Answer question={view.question} result={view.result} />}
      {view.phase === 'failed' && <Failure failure={view.failure} />}
    </div>
  )
}

/**
 * The Copilot tab of the Operations panel (Feature 026). Its state lives in `useCopilot`, owned by
 * `App`, so this component can be unmounted and remounted freely. Nothing is sent when it appears:
 * it only asks whether the Copilot is available (no model call), and a question is sent only when
 * the operator submits one.
 */
export function CopilotTab({ copilot }: { copilot: CopilotController }) {
  const { availability, checkAvailability } = copilot
  useEffect(() => {
    checkAvailability()
  }, [checkAvailability])

  return (
    <section aria-label="AI Copilot" className="flex flex-col gap-3 p-3 text-sm">
      <p className="text-xs font-medium">Read-only AI Copilot — cannot control drones</p>
      {(availability === 'unknown' || availability === 'checking') && (
        <p role="status" className="text-fg-muted">
          Checking whether the AI Copilot is available…
        </p>
      )}
      {availability === 'error' && (
        <div role="alert" className="flex items-center justify-between gap-2">
          <span>Could not reach the backend to check the AI Copilot.</span>
          <button
            type="button"
            onClick={copilot.checkAvailability}
            className="min-h-8 rounded border border-line px-2 hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
          >
            Check again
          </button>
        </div>
      )}
      {availability === 'unavailable' && (
        <p role="status" className="text-fg-muted">
          The AI Copilot is disabled or not configured on this server, so no question can be sent.
          It is enabled deliberately in the server configuration.
        </p>
      )}
      {availability === 'available' && (
        <>
          <TokenControl copilot={copilot} />
          <QuestionForm copilot={copilot} />
          <Result copilot={copilot} />
        </>
      )}
    </section>
  )
}
