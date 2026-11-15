import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { CHARGE_WARNING, askCopilot, getCopilotStatus, toCopilotFailure } from './copilot'

afterEach(() => vi.unstubAllGlobals())

const SNAPSHOT = {
  captured_at: '2026-11-15T14:03:07Z',
  data_status: 'complete',
  truncated: false,
  limitations: [],
  omitted: { drones: 0, hubs: 0, active_incidents: 0, recovered_alerts: 0 },
  named_drones: [],
}
const ANSWER = { answer: 'Two drones are charging.', answer_cut_off: false, snapshot: SNAPSHOT }
const TOKEN = 'unit-test-token-' + 'x'.repeat(30)

function stubFetch(response: Response | Promise<Response>) {
  const fetchMock = vi.fn(() => Promise.resolve(response))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getCopilotStatus', () => {
  it('reads the generic availability flag', async () => {
    stubFetch(jsonResponse({ available: true }))
    expect(await getCopilotStatus()).toBe(true)
    stubFetch(jsonResponse({ available: false }))
    expect(await getCopilotStatus()).toBe(false)
  })

  it('rejects anything that is not a boolean flag', async () => {
    for (const payload of [{ available: 'yes' }, {}, null, 'available', { available: 1 }]) {
      stubFetch(jsonResponse(payload))
      await expect(getCopilotStatus()).rejects.toBeInstanceOf(ApiError)
    }
  })

  it('does not send credentials', async () => {
    const fetchMock = stubFetch(jsonResponse({ available: true }))
    await getCopilotStatus()
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url.endsWith('/api/ai/copilot/status')).toBe(true)
    expect(init.headers).toBeUndefined()
  })
})

describe('askCopilot', () => {
  it('sends one POST with the token only in the Authorization header', async () => {
    const fetchMock = stubFetch(jsonResponse(ANSWER))

    await askCopilot('How many drones are charging?', TOKEN)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url.endsWith('/api/ai/copilot/ask')).toBe(true)
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    })
    expect(init.body).toBe(JSON.stringify({ question: 'How many drones are charging?' }))
    expect(url).not.toContain(TOKEN) // never in the URL ...
    expect(String(init.body)).not.toContain(TOKEN) // ... nor in the body
  })

  it('maps the response to camelCase and keeps the server facts', async () => {
    stubFetch(
      jsonResponse({
        answer: 'a',
        answer_cut_off: true,
        snapshot: {
          ...SNAPSHOT,
          data_status: 'degraded',
          truncated: true,
          limitations: ['WORKER_NOT_RUNNING', 'DRONES_OMITTED:7'],
          omitted: { drones: 7, hubs: 1, active_incidents: 2, recovered_alerts: 3 },
          named_drones: [{ id: 'DRN-044', exists: true, listed: false }],
        },
      }),
    )

    expect(await askCopilot('q', TOKEN)).toEqual({
      answer: 'a',
      answerCut: true,
      snapshot: {
        capturedAt: '2026-11-15T14:03:07Z',
        dataStatus: 'degraded',
        truncated: true,
        limitations: ['WORKER_NOT_RUNNING', 'DRONES_OMITTED:7'],
        omitted: { drones: 7, hubs: 1, activeIncidents: 2, recoveredAlerts: 3 },
        namedDrones: [{ id: 'DRN-044', exists: true, listed: false }],
      },
    })
  })

  const BROKEN: [string, unknown][] = [
    ['not an object', 'text'],
    ['no answer', { ...ANSWER, answer: undefined }],
    ['answer not text', { ...ANSWER, answer: 5 }],
    ['no cut-off flag', { ...ANSWER, answer_cut_off: 'no' }],
    ['no snapshot', { ...ANSWER, snapshot: null }],
    ['bad status', { ...ANSWER, snapshot: { ...SNAPSHOT, data_status: 'fine' } }],
    ['bad time', { ...ANSWER, snapshot: { ...SNAPSHOT, captured_at: '' } }],
    ['bad truncated', { ...ANSWER, snapshot: { ...SNAPSHOT, truncated: 'no' } }],
    ['limitation not text', { ...ANSWER, snapshot: { ...SNAPSHOT, limitations: [1] } }],
    ['no omitted', { ...ANSWER, snapshot: { ...SNAPSHOT, omitted: undefined } }],
    [
      'negative count',
      { ...ANSWER, snapshot: { ...SNAPSHOT, omitted: { ...SNAPSHOT.omitted, drones: -1 } } },
    ],
    [
      'fractional count',
      { ...ANSWER, snapshot: { ...SNAPSHOT, omitted: { ...SNAPSHOT.omitted, hubs: 1.5 } } },
    ],
    [
      'bad named drone',
      { ...ANSWER, snapshot: { ...SNAPSHOT, named_drones: [{ id: 'DRN-001', exists: 'yes' }] } },
    ],
  ]

  it.each(BROKEN)('rejects a response with %s', async (_name, payload) => {
    stubFetch(jsonResponse(payload))
    await expect(askCopilot('q', TOKEN)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('toCopilotFailure', () => {
  const fail = (status: number | undefined, detail?: unknown) =>
    toCopilotFailure(new ApiError('failed', status, detail))

  it('uses its own fixed text for every server code, never the server text', () => {
    const codes = [
      'ORIGIN_NOT_ALLOWED',
      'AI_DISABLED',
      'AI_MISCONFIGURED',
      'UNAUTHORIZED',
      'AUTH_THROTTLED',
      'INVALID_QUESTION',
      'CONTEXT_TOO_LARGE',
      'RATE_LIMITED',
      'BUDGET_EXHAUSTED',
      'AI_HALTED',
      'PROVIDER_UNAVAILABLE',
      'ACCOUNTING_UNAVAILABLE',
      'CONTEXT_UNAVAILABLE',
      'INTERNAL_ERROR',
    ]
    for (const code of codes) {
      const failure = fail(409, { code, message: '<b>SERVER TEXT</b> Authorization: Bearer abc' })
      expect(failure.code).toBe(code)
      expect(failure.message).not.toContain('SERVER TEXT')
      expect(failure.message.length).toBeGreaterThan(10)
      expect(failure.chargePossible).toBe(false)
    }
  })

  it('reads the retry delay', () => {
    expect(fail(429, { code: 'RATE_LIMITED', retry_after_seconds: 12 }).retryAfterSeconds).toBe(12)
    expect(fail(429, { code: 'RATE_LIMITED' }).retryAfterSeconds).toBeNull()
  })

  it('says a provider rejection is not charged and an unclear outcome may be', () => {
    const rejected = fail(502, { code: 'PROVIDER_UNAVAILABLE', charge_possible: false })
    const unclear = fail(502, { code: 'PROVIDER_UNAVAILABLE', charge_possible: true })

    expect(rejected.chargePossible).toBe(false)
    expect(rejected.message).toContain('No charge is expected')
    expect(unclear.chargePossible).toBe(true)
    expect(unclear.message).toBe('The outcome of the request is unknown.')
  })

  it('treats a lost connection, an unreadable success and a non-Copilot 5xx as possibly charged', () => {
    expect(fail(undefined)).toMatchObject({ code: 'CONNECTION_LOST', chargePossible: true })
    expect(fail(200)).toMatchObject({ code: 'CONNECTION_LOST', chargePossible: true })
    expect(fail(502, 'Bad Gateway')).toMatchObject({ code: 'UNKNOWN', chargePossible: true })
    expect(fail(500, { code: 'SOMETHING_ELSE' })).toMatchObject({ chargePossible: true })
    expect(toCopilotFailure(new Error('boom'))).toMatchObject({
      code: 'UNKNOWN',
      chargePossible: true,
    })
  })

  it('does not call an ordinary rejection possibly charged', () => {
    expect(fail(404)).toMatchObject({ code: 'UNKNOWN', chargePossible: false })
    expect(fail(422, [{ loc: ['body', 'question'], msg: 'x' }])).toMatchObject({
      chargePossible: false,
    })
  })

  it('has one warning text for every possibly charged request', () => {
    expect(CHARGE_WARNING).toContain('may have been charged')
    expect(CHARGE_WARNING).toContain('not be retried automatically')
    expect(CHARGE_WARNING).toContain('ledger')
  })
})
