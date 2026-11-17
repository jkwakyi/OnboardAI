/**
 * The Chat API client (ON-48).
 *
 * Thin, and worth its own tests for one reason: it has to resolve for the
 * HR fallback rather than reject. The fallback is a `200` and the page
 * draws it as a normal turn in the conversation; a client that treated it
 * as a failure would turn the assistant's most important behaviour into
 * an error message.
 */
import { expect, it, vi } from 'vitest'

import { createApiClient } from './client'
import { ApiError, NetworkError } from './errors'
import { MAX_QUESTION_CHARACTERS, askQuestion } from './chat'

const ANSWERED = {
  id: 12,
  answer: 'Eighteen days.',
  citations: [{ section_id: 475, heading: '4.1 PAID TIME OFF', document: 'handbook.txt' }],
  fallback: false,
}

const FELL_BACK = {
  id: 13,
  answer: 'I could not find an answer to that in the approved HR documents.',
  citations: [],
  fallback: true,
}

function respond(body: unknown, status = 200) {
  return vi.fn(
    async () =>
      ({
        ok: status >= 200 && status < 300,
        status,
        headers: { get: () => null },
        json: async () => body,
      }) as unknown as Response,
  )
}

function clientWith(fetchImpl: typeof fetch, token: string | null = 'a-token') {
  return createApiClient({ token, baseUrl: 'http://backend.test/api', fetchImpl })
}

it('posts the question to the ask endpoint', async () => {
  const fetchImpl = respond(ANSWERED)

  await askQuestion(clientWith(fetchImpl as unknown as typeof fetch), 'How much PTO?')

  const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toBe('http://backend.test/api/chat/ask')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({ question: 'How much PTO?' })
})

it('sends the login token, because Auth Check wants one', async () => {
  const fetchImpl = respond(ANSWERED)

  await askQuestion(clientWith(fetchImpl as unknown as typeof fetch), 'How much PTO?')

  const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer a-token')
})

it('returns the answer with its citations', async () => {
  const answer = await askQuestion(
    clientWith(respond(ANSWERED) as unknown as typeof fetch),
    'How much PTO?',
  )

  expect(answer).toEqual(ANSWERED)
})

it('resolves for the HR fallback rather than treating it as a failure', async () => {
  /**
   * The one that matters. A timeout, a provider error, invalid output
   * from the model and no good match are all `200` with `fallback: true`
   * — the contracts are explicit that none of them is an error for the
   * employee. Rejecting here would make the page show them all in red.
   */
  const answer = await askQuestion(
    clientWith(respond(FELL_BACK) as unknown as typeof fetch),
    'What is the airspeed velocity of an unladen swallow?',
  )

  expect(answer.fallback).toBe(true)
  expect(answer.answer).toContain('could not find an answer')
})

it('rejects when the server refuses the question', async () => {
  await expect(
    askQuestion(
      clientWith(respond({ detail: 'The question cannot be blank.' }, 422) as unknown as typeof fetch),
      '',
    ),
  ).rejects.toBeInstanceOf(ApiError)
})

it('rejects when the server cannot be reached', async () => {
  const fetchImpl = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))

  await expect(
    askQuestion(clientWith(fetchImpl as unknown as typeof fetch), 'How much PTO?'),
  ).rejects.toBeInstanceOf(NetworkError)
})

it('passes an abort signal through', async () => {
  const fetchImpl = respond(ANSWERED)
  const controller = new AbortController()

  await askQuestion(clientWith(fetchImpl as unknown as typeof fetch), 'How much PTO?', {
    signal: controller.signal,
  })

  const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect(init.signal).toBe(controller.signal)
})

it('mirrors the backend LLM Gateway question limit', () => {
  /**
   * The literal. The backend's `MAX_QUESTION_CHARACTERS` is 2000, the two
   * have no shared source to read it from, and comparing the constant
   * with itself would let both drift together and still pass.
   */
  expect(MAX_QUESTION_CHARACTERS).toBe(2000)
})
