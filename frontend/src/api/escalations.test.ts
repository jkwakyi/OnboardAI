/**
 * The Escalations API client (ON-20).
 *
 * Thin, and worth its own tests for one thing: it must send which answer
 * is being escalated and nothing else. The question in HR's inbox is the
 * one the server reads out of the chat log, and a client that sent its
 * own text would be the thing that broke that.
 */
import { expect, it, vi } from 'vitest'

import { createApiClient } from './client'
import { ApiError, NetworkError } from './errors'
import { sendToHr } from './escalations'

const ESCALATION = {
  id: 4,
  chat_log_id: 13,
  question: 'Am I paid for jury duty?',
  status: 'open',
  created_at: '2026-11-17T12:00:00Z',
}

function respond(body: unknown, status = 201) {
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

it('posts to the escalations endpoint', async () => {
  const fetchImpl = respond(ESCALATION)

  await sendToHr(clientWith(fetchImpl as unknown as typeof fetch), 13)

  const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toBe('http://backend.test/api/escalations')
  expect(init.method).toBe('POST')
})

it('sends which answer is being escalated, and nothing else', async () => {
  const fetchImpl = respond(ESCALATION)

  await sendToHr(clientWith(fetchImpl as unknown as typeof fetch), 13)

  const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect(JSON.parse(init.body as string)).toEqual({ chat_log_id: 13 })
})

it('sends the login token, because Auth Check wants one', async () => {
  const fetchImpl = respond(ESCALATION)

  await sendToHr(clientWith(fetchImpl as unknown as typeof fetch), 13)

  const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer a-token')
})

it('returns the open escalation the backend saved', async () => {
  const saved = await sendToHr(clientWith(respond(ESCALATION) as unknown as typeof fetch), 13)

  expect(saved).toEqual(ESCALATION)
  expect(saved.status).toBe('open')
})

it('rejects when the answer is not the caller’s to escalate', async () => {
  await expect(
    sendToHr(
      clientWith(
        respond({ detail: 'That answer could not be found.' }, 404) as unknown as typeof fetch,
      ),
      13,
    ),
  ).rejects.toBeInstanceOf(ApiError)
})

it('rejects when the question was answered', async () => {
  const refusal = sendToHr(
    clientWith(
      respond(
        { detail: 'That question was answered, so there is nothing to send to HR.' },
        409,
      ) as unknown as typeof fetch,
    ),
    13,
  )

  await expect(refusal).rejects.toMatchObject({ status: 409 })
})

it('rejects when the server cannot be reached', async () => {
  const fetchImpl = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))

  await expect(
    sendToHr(clientWith(fetchImpl as unknown as typeof fetch), 13),
  ).rejects.toBeInstanceOf(NetworkError)
})

it('passes an abort signal through', async () => {
  const fetchImpl = respond(ESCALATION)
  const controller = new AbortController()

  await sendToHr(clientWith(fetchImpl as unknown as typeof fetch), 13, {
    signal: controller.signal,
  })

  const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
  expect(init.signal).toBe(controller.signal)
})
