import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CHARGE_WARNING } from '../../api/copilot'
import { jsonResponse } from '../../test/hubFixtures'
import { CopilotTab } from './CopilotTab'
import { useCopilot } from './useCopilot'

afterEach(() => vi.unstubAllGlobals())

const TOKEN = 'unit-test-token-' + 'x'.repeat(30)
const SNAPSHOT = {
  captured_at: '2026-11-15T14:03:07Z',
  data_status: 'complete',
  truncated: false,
  limitations: [] as string[],
  omitted: { drones: 0, hubs: 0, active_incidents: 0, recovered_alerts: 0 },
  named_drones: [] as { id: string; exists: boolean; listed: boolean }[],
}
const ANSWER = { answer: 'Two drones are charging.', answer_cut_off: false, snapshot: SNAPSHOT }

interface Stub {
  available?: boolean | 'fail'
  ask?: (init: RequestInit) => Promise<Response>
}

/** A fake backend that counts the status probes and the questions separately. */
function stubBackend(options: Stub = {}) {
  const calls = { status: vi.fn(), ask: vi.fn() }
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith('/api/ai/copilot/status')) {
        calls.status()
        if (options.available === 'fail') return Promise.reject(new TypeError('network'))
        return Promise.resolve(jsonResponse({ available: options.available ?? true }))
      }
      if (url.endsWith('/api/ai/copilot/ask')) {
        calls.ask(url, init)
        return options.ask
          ? options.ask(init as RequestInit)
          : Promise.resolve(jsonResponse(ANSWER))
      }
      throw new Error(`unexpected request: ${url}`)
    }),
  )
  return { calls, options }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

/** Like `App`: the state lives above the tab, and the tab can be hidden and shown again. */
function Harness() {
  const copilot = useCopilot()
  const [shown, setShown] = useState(true)
  return (
    <div>
      <button type="button" onClick={() => setShown((value) => !value)}>
        toggle tab
      </button>
      {shown && <CopilotTab copilot={copilot} />}
    </div>
  )
}

const tokenInput = () => screen.getByLabelText('Access token')
const questionInput = () => screen.getByLabelText('Question') as HTMLInputElement
const askButton = () => screen.getByRole('button', { name: /^(Ask|Asking…)$/ })

async function ready() {
  await screen.findByLabelText('Access token')
}

async function enterToken() {
  fireEvent.change(tokenInput(), { target: { value: TOKEN } })
  fireEvent.click(screen.getByRole('button', { name: 'Use token' }))
  await screen.findByText(/Access token set/)
}

async function ask(question = 'How many drones are charging?') {
  fireEvent.change(questionInput(), { target: { value: question } })
  fireEvent.click(askButton())
}

const pause = (ms = 40) => new Promise((done) => setTimeout(done, ms))

describe('Copilot tab: nothing is sent by itself', () => {
  it('asks only whether it is available when first shown, and sends no question', async () => {
    const { calls } = stubBackend()
    render(<Harness />)

    await ready()

    expect(calls.status).toHaveBeenCalledTimes(1)
    expect(calls.ask).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'toggle tab' })) // hide ...
    fireEvent.click(screen.getByRole('button', { name: 'toggle tab' })) // ... and show again
    await ready()
    expect(calls.status).toHaveBeenCalledTimes(1) // not probed again
    await pause()
    expect(calls.ask).not.toHaveBeenCalled()
  })

  it('states the read-only nature of the assistant', async () => {
    stubBackend()
    render(<Harness />)
    await ready()

    expect(screen.getByText('Read-only AI Copilot — cannot control drones')).toBeInTheDocument()
  })

  it('explains an unavailable Copilot and offers no way to send anything', async () => {
    const { calls } = stubBackend({ available: false })
    render(<Harness />)

    expect(await screen.findByText(/disabled or not configured on this server/)).toBeInTheDocument()

    expect(screen.queryByLabelText('Question')).toBeNull()
    expect(screen.queryByLabelText('Access token')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Ask' })).toBeNull()
    expect(calls.ask).not.toHaveBeenCalled()
  })

  it('offers to check again when the backend cannot be reached', async () => {
    const { calls, options } = stubBackend({ available: 'fail' })
    render(<Harness />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')

    options.available = true
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))

    await ready()
    expect(calls.status).toHaveBeenCalledTimes(2) // a status probe is harmless to repeat
    expect(calls.ask).not.toHaveBeenCalled()
  })
})

describe('Copilot tab: the access token', () => {
  it('is a password field and is kept only in memory', async () => {
    stubBackend()
    const { container } = render(<Harness />)
    await ready()
    expect(tokenInput()).toHaveAttribute('type', 'password')
    expect(tokenInput()).toHaveAttribute('autocomplete', 'off')

    await enterToken()

    expect(screen.queryByLabelText('Access token')).toBeNull() // the field is gone ...
    expect(container.innerHTML).not.toContain(TOKEN) // ... and the value is nowhere in the page
    fireEvent.click(screen.getByRole('button', { name: 'Forget token' }))
    expect(await screen.findByLabelText('Access token')).toHaveValue('')
  })

  it('never reaches storage, cookies or the page', async () => {
    stubBackend()
    render(<Harness />)
    await ready()
    await enterToken()
    await ask()
    await screen.findByTestId('copilot-answer')

    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(document.cookie).toBe('')
    expect(document.documentElement.outerHTML).not.toContain(TOKEN)
    expect(window.location.href).not.toContain(TOKEN)
  })

  it('keeps Ask disabled until there is a token and a question', async () => {
    stubBackend()
    render(<Harness />)
    await ready()
    fireEvent.change(questionInput(), { target: { value: 'Which drones need attention?' } })
    expect(askButton()).toBeDisabled() // no token yet
    expect(screen.getByText(/Enter the access token first/)).toBeInTheDocument()

    await enterToken()
    expect(askButton()).toBeEnabled()
    fireEvent.change(questionInput(), { target: { value: '   ' } })
    expect(askButton()).toBeDisabled() // a blank question
  })

  it('limits the question to 500 characters and counts them', async () => {
    stubBackend()
    render(<Harness />)
    await ready()

    expect(questionInput()).toHaveAttribute('maxlength', '500')
    fireEvent.change(questionInput(), { target: { value: 'abc' } })
    expect(screen.getByText(/3\/500 characters/)).toBeInTheDocument()
  })
})

describe('Copilot tab: asking', () => {
  it('sends ONE request with the token in the Authorization header and shows the answer', async () => {
    const { calls } = stubBackend()
    render(<Harness />)
    await ready()
    await enterToken()

    await ask('How many drones are charging?')

    expect(await screen.findByTestId('copilot-answer')).toHaveTextContent(
      'Two drones are charging.',
    )
    expect(calls.ask).toHaveBeenCalledTimes(1)
    const [url, init] = calls.ask.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`)
    expect(url).not.toContain(TOKEN)
    expect(JSON.parse(String(init.body))).toEqual({ question: 'How many drones are charging?' })
    expect(screen.getByText('Snapshot taken').closest('p')).toHaveTextContent(
      'Snapshot taken 2026-11-15 14:03:07 UTC — complete.',
    )
  })

  it('shows model output as plain text: markup and links stay inert', async () => {
    const hostile =
      '<img src=x onerror="window.__pwned=true"><script>window.__pwned=true</script>' +
      '<b>bold</b> [click](javascript:alert(1)) http://evil.test <a href="http://evil.test">x</a>'
    stubBackend({
      ask: () => Promise.resolve(jsonResponse({ ...ANSWER, answer: hostile })),
    })
    const { container } = render(<Harness />)
    await ready()
    await enterToken()

    await ask()

    const shown = await screen.findByTestId('copilot-answer')
    expect(shown.textContent).toBe(hostile) // the text, exactly, as text
    expect(container.querySelector('img, script, b, a[href], iframe, [onerror]')).toBeNull()
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined()
  })

  it('sends one request however many times it is submitted while pending', async () => {
    const pending = deferred<Response>()
    const { calls } = stubBackend({ ask: () => pending.promise })
    render(<Harness />)
    await ready()
    await enterToken()
    fireEvent.change(questionInput(), { target: { value: 'Which drones need attention?' } })

    const form = questionInput().closest('form') as HTMLFormElement
    fireEvent.click(askButton())
    fireEvent.click(askButton()) // a double click ...
    fireEvent.submit(form) // ... Enter in the field ...
    fireEvent.submit(form) // ... and again

    expect(calls.ask).toHaveBeenCalledTimes(1)
    expect(askButton()).toBeDisabled()
    expect(askButton()).toHaveTextContent('Asking…')
    expect(questionInput()).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(/never retried automatically/)

    pending.resolve(jsonResponse(ANSWER))
    expect(await screen.findByTestId('copilot-answer')).toBeInTheDocument()
    expect(calls.ask).toHaveBeenCalledTimes(1)
    expect(askButton()).toBeEnabled()

    fireEvent.click(askButton()) // asking again is the operator's own, deliberate act
    await waitFor(() => expect(calls.ask).toHaveBeenCalledTimes(2))
  })

  it('keeps the draft, the answer and even a request still on its way across tab switches', async () => {
    const pending = deferred<Response>()
    const { calls } = stubBackend({ ask: () => pending.promise })
    render(<Harness />)
    await ready()
    await enterToken()
    await ask('Where is DRN-007?')
    const toggle = () => fireEvent.click(screen.getByRole('button', { name: 'toggle tab' }))

    toggle() // the tab disappears while the request is in flight
    pending.resolve(jsonResponse({ ...ANSWER, answer: 'DRN-007 is docked.' }))
    await pause()
    toggle() // and comes back

    expect(await screen.findByTestId('copilot-answer')).toHaveTextContent('DRN-007 is docked.')
    expect(calls.ask).toHaveBeenCalledTimes(1) // nothing was sent again
    expect(screen.getByText(/Access token set/)).toBeInTheDocument() // the token was kept too
    fireEvent.change(questionInput(), { target: { value: 'a half-written follow-up' } })
    toggle()
    toggle()
    expect(questionInput().value).toBe('a half-written follow-up')
  })
})

describe('Copilot tab: what the snapshot says', () => {
  it('flags degraded and truncated data and every limitation, omission and named drone', async () => {
    stubBackend({
      ask: () =>
        Promise.resolve(
          jsonResponse({
            ...ANSWER,
            answer_cut_off: true,
            snapshot: {
              ...SNAPSHOT,
              data_status: 'degraded',
              truncated: true,
              limitations: ['WORKER_NOT_RUNNING', 'DRONES_OMITTED:7', 'SOMETHING_NEW:x'],
              omitted: { drones: 7, hubs: 0, active_incidents: 1, recovered_alerts: 0 },
              named_drones: [
                { id: 'DRN-099', exists: false, listed: false },
                { id: 'DRN-044', exists: true, listed: false },
                { id: 'DRN-003', exists: true, listed: true },
              ],
            },
          }),
        ),
    })
    render(<Harness />)
    await ready()
    await enterToken()

    await ask()

    await screen.findByTestId('copilot-answer')
    expect(screen.getByText(/Degraded data:/)).toBeInTheDocument()
    expect(screen.getByText(/Truncated snapshot:/)).toBeInTheDocument()
    expect(screen.getByText(/simulation worker is not running/)).toBeInTheDocument()
    expect(
      screen.getByText(/Drones are not in the snapshot \(the count follows\): 7/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Unrecognised limitation: SOMETHING_NEW:x/)).toBeInTheDocument()
    expect(screen.getByText('7 drones are not in the snapshot.')).toBeInTheDocument()
    expect(screen.getByText('1 active incidents are not in the snapshot.')).toBeInTheDocument()
    expect(screen.getByText('DRN-099 is not in the fleet.')).toBeInTheDocument()
    expect(screen.getByText(/DRN-044 was not included in the snapshot/)).toBeInTheDocument()
    expect(screen.queryByText(/DRN-003 was not/)).toBeNull() // a named drone that was listed
    expect(screen.getByText(/cut short at the length limit/)).toBeInTheDocument()
    expect(screen.queryByText(/complete\./)).toBeNull() // never "complete" with warnings
  })
})

describe('Copilot tab: failures', () => {
  const FAILURES: [string, number, Record<string, unknown>, RegExp][] = [
    ['unauthorised', 401, { code: 'UNAUTHORIZED' }, /access token was not accepted/],
    ['throttled', 429, { code: 'AUTH_THROTTLED', retry_after_seconds: 30 }, /Too many failed/],
    [
      'rate limited',
      429,
      { code: 'RATE_LIMITED', retry_after_seconds: 12 },
      /AI requests are limited/,
    ],
    ['budget', 409, { code: 'BUDGET_EXHAUSTED' }, /budget is exhausted/],
    ['halted', 409, { code: 'AI_HALTED' }, /stopped itself/],
    ['disabled', 503, { code: 'AI_DISABLED' }, /disabled on this server/],
    ['snapshot', 503, { code: 'CONTEXT_UNAVAILABLE' }, /no AI request was made/],
    ['too large', 413, { code: 'CONTEXT_TOO_LARGE' }, /size limit/],
    ['invalid', 422, { code: 'INVALID_QUESTION' }, /not accepted/],
    ['origin', 403, { code: 'ORIGIN_NOT_ALLOWED' }, /origin check failed/],
    [
      'provider rejected',
      502,
      { code: 'PROVIDER_UNAVAILABLE', charge_possible: false },
      /No charge is expected/,
    ],
  ]

  it.each(FAILURES)(
    'explains a %s failure and does not warn about a charge',
    async (_n, status, detail, text) => {
      const { calls } = stubBackend({
        ask: () =>
          Promise.resolve(jsonResponse({ detail: { ...detail, message: 'SERVER TEXT' } }, status)),
      })
      render(<Harness />)
      await ready()
      await enterToken()

      await ask()

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(text)
      expect(alert).not.toHaveTextContent('SERVER TEXT')
      expect(screen.queryByText(CHARGE_WARNING)).toBeNull()
      await pause()
      expect(calls.ask).toHaveBeenCalledTimes(1) // never retried
    },
  )

  it('shows how long to wait', async () => {
    stubBackend({
      ask: () =>
        Promise.resolve(
          jsonResponse(
            { detail: { code: 'RATE_LIMITED', message: 'x', retry_after_seconds: 12 } },
            429,
          ),
        ),
    })
    render(<Harness />)
    await ready()
    await enterToken()
    await ask()

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 12 s.')
  })

  it('forgets a token the server did not accept so it is entered again', async () => {
    stubBackend({
      ask: () =>
        Promise.resolve(jsonResponse({ detail: { code: 'UNAUTHORIZED', message: 'x' } }, 401)),
    })
    render(<Harness />)
    await ready()
    await enterToken()

    await ask()

    await screen.findByRole('alert')
    expect(await screen.findByLabelText('Access token')).toHaveValue('')
    expect(askButton()).toBeDisabled()
  })

  const AMBIGUOUS: [string, () => Promise<Response>][] = [
    [
      'the provider outcome is unclear',
      () =>
        Promise.resolve(
          jsonResponse(
            { detail: { code: 'PROVIDER_UNAVAILABLE', message: 'x', charge_possible: true } },
            502,
          ),
        ),
    ],
    ['the connection is lost', () => Promise.reject(new TypeError('network'))],
    ['a success cannot be read', () => Promise.resolve(new Response('not json', { status: 200 }))],
    [
      'a proxy answers with an error page',
      () => Promise.resolve(new Response('Bad Gateway', { status: 502 })),
    ],
  ]

  it.each(AMBIGUOUS)(
    'warns that it may have been charged when %s, and never retries',
    async (_n, handler) => {
      const { calls } = stubBackend({ ask: handler })
      render(<Harness />)
      await ready()
      await enterToken()

      await ask()

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(CHARGE_WARNING)
      expect(alert).toHaveTextContent(/not be retried automatically/)
      await pause(150) // long enough for any automatic retry to have fired
      expect(calls.ask).toHaveBeenCalledTimes(1)
      expect(askButton()).toBeEnabled() // only the operator can ask again
    },
  )
})
