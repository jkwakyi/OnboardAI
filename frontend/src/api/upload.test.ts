/**
 * The upload transport (ON-42).
 *
 * What matters here is that it behaves *identically* to `client.ts` for
 * everything except progress. Two ways of reaching the backend that
 * disagree about what a 401 means, or about which message a 413 gets, is
 * two sets of behaviour for a page to discover separately.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FakeXhr } from '../test/fakeXhr'
import { ApiError, NETWORK_MESSAGE, NetworkError } from './errors'
import { uploadWithProgress } from './upload'

function form(): FormData {
  const data = new FormData()
  data.append('file', new File(['hello'], 'handbook.txt', { type: 'text/plain' }))
  return data
}

function start<T>(
  xhr: FakeXhr,
  overrides: Partial<Parameters<typeof uploadWithProgress>[0]> = {},
): Promise<T> {
  return uploadWithProgress<T>({
    url: 'http://backend.test/api/documents',
    formData: form(),
    token: 'a-token',
    xhr: xhr as unknown as XMLHttpRequest,
    ...overrides,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('sending the request', () => {
  it('posts to the url it was given', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(201, { id: 1 })
    await settled

    expect(xhr.sent.method).toBe('POST')
    expect(xhr.sent.url).toBe('http://backend.test/api/documents')
  })

  it('sends the login token', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(201, { id: 1 })
    await settled

    expect(xhr.sent.headers.Authorization).toBe('Bearer a-token')
  })

  it('sends no Authorization header when there is no token', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr, { token: null })
    xhr.respond(201, { id: 1 })
    await settled

    expect(xhr.sent.headers).not.toHaveProperty('Authorization')
  })

  it('sets no Content-Type of its own', async () => {
    // The browser sets multipart/form-data *and the boundary it
    // generated*. Setting the header by hand drops the boundary, and the
    // server then cannot parse a request that looks well formed from here.
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(201, { id: 1 })
    await settled

    expect(Object.keys(xhr.sent.headers)).toEqual(['Authorization'])
  })

  it('sends the form data itself', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(201, { id: 1 })
    await settled

    expect(xhr.sent.body).toBeInstanceOf(FormData)
  })
})

describe('progress', () => {
  it('reports how far the body has got, as a percentage', async () => {
    const xhr = new FakeXhr()
    const seen: number[] = []
    const settled = start(xhr, { onProgress: (percent) => seen.push(percent) })

    xhr.progress(25, 200)
    xhr.progress(100, 200)
    xhr.respond(201, { id: 1 })
    await settled

    expect(seen).toEqual([12.5, 50])
  })

  it('says nothing when the browser cannot measure the body', async () => {
    // Rather than reporting 0%, which would sit there looking stalled.
    const xhr = new FakeXhr()
    const onProgress = vi.fn()
    const settled = start(xhr, { onProgress })

    xhr.immeasurableProgress()
    xhr.respond(201, { id: 1 })
    await settled

    expect(onProgress).not.toHaveBeenCalled()
  })

  it('never reports more than 100', async () => {
    const xhr = new FakeXhr()
    const seen: number[] = []
    const settled = start(xhr, { onProgress: (percent) => seen.push(percent) })

    // Chrome has been known to report loaded > total for a chunked body.
    xhr.progress(150, 100)
    xhr.respond(201, { id: 1 })
    await settled

    expect(seen).toEqual([100])
  })
})

describe('what comes back', () => {
  it('resolves with the parsed body', async () => {
    const xhr = new FakeXhr()
    const settled = start<{ id: number; filename: string }>(xhr)
    xhr.respond(201, { id: 3, filename: 'handbook.txt' })

    await expect(settled).resolves.toEqual({ id: 3, filename: 'handbook.txt' })
  })

  it('rejects with the backend’s own message', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(415, { detail: 'Only PDF and TXT documents are accepted.' })

    await expect(settled).rejects.toThrow('Only PDF and TXT documents are accepted.')
  })

  it('falls back to the status when there is no usable detail', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(413, {})

    await expect(settled).rejects.toThrow('That file is too large.')
  })

  it('carries the status on the error', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respond(422, { detail: 'That document contains no readable text.' })

    await expect(settled).rejects.toMatchObject({ status: 422 })
  })

  it('reads Retry-After when the backend sends one', async () => {
    const xhr = new FakeXhr()
    xhr.responseHeaders = { 'Retry-After': '30' }
    const settled = start(xhr)
    xhr.respond(429, {})

    await expect(settled).rejects.toMatchObject({ retryAfterSeconds: 30 })
  })

  it('copes with a reply that is not JSON', async () => {
    // A proxy's HTML error page. There is no detail to show, so the
    // status has to speak for itself.
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respondWithGarbage(500, '<html>Bad Gateway</html>')

    await expect(settled).rejects.toThrow('Something went wrong on the server. Please try again.')
  })

  it('refuses a success with an unreadable body', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.respondWithGarbage(201, 'not json')

    await expect(settled).rejects.toThrow('The server sent a reply that could not be read.')
  })

  it('treats any 2xx as success', async () => {
    const xhr = new FakeXhr()
    const settled = start<{ ok: boolean }>(xhr)
    xhr.respond(200, { ok: true })

    await expect(settled).resolves.toEqual({ ok: true })
  })
})

describe('when the session has ended', () => {
  it('signs out on a 401, before reading the body', async () => {
    const onUnauthorised = vi.fn()
    const xhr = new FakeXhr()
    const settled = start(xhr, { onUnauthorised })
    xhr.respondWithGarbage(401, 'not json at all')

    await expect(settled).rejects.toThrow(ApiError)
    expect(onUnauthorised).toHaveBeenCalledTimes(1)
  })

  it('does not sign out on any other refusal', async () => {
    const onUnauthorised = vi.fn()
    const xhr = new FakeXhr()
    const settled = start(xhr, { onUnauthorised })
    xhr.respond(413, { detail: 'too big' })

    await expect(settled).rejects.toThrow(ApiError)
    expect(onUnauthorised).not.toHaveBeenCalled()
  })
})

describe('when it never arrives', () => {
  it('is a network error, not an API error', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.networkFailure()

    await expect(settled).rejects.toThrow(NetworkError)
    await expect(settled).rejects.toThrow(NETWORK_MESSAGE)
  })

  it('treats a timeout the same way', async () => {
    const xhr = new FakeXhr()
    const settled = start(xhr)
    xhr.timeout()

    await expect(settled).rejects.toThrow(NetworkError)
  })
})

describe('aborting', () => {
  it('rejects with an AbortError the caller can recognise', async () => {
    const controller = new AbortController()
    const xhr = new FakeXhr()
    const settled = start(xhr, { signal: controller.signal })

    controller.abort()

    await expect(settled).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('aborts the request itself, rather than only the promise', async () => {
    // Otherwise the bytes keep going out after the page has moved on,
    // which on a large file is the whole cost of the upload.
    const controller = new AbortController()
    const xhr = new FakeXhr()
    const aborted = vi.spyOn(xhr, 'abort')
    const settled = start(xhr, { signal: controller.signal })

    controller.abort()
    await expect(settled).rejects.toMatchObject({ name: 'AbortError' })

    expect(aborted).toHaveBeenCalled()
  })

  it('never starts when the signal is already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const xhr = new FakeXhr()
    const opened = vi.spyOn(xhr, 'open')

    await expect(start(xhr, { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(opened).not.toHaveBeenCalled()
  })

  it('stops listening to the signal once it has finished', async () => {
    // A signal that outlives the request - one held by a page across
    // several uploads - would otherwise accumulate a listener per upload,
    // and each one would try to reject a promise that already settled.
    const controller = new AbortController()
    const xhr = new FakeXhr()
    const settled = start(xhr, { signal: controller.signal })
    xhr.respond(201, { id: 1 })
    await settled

    const abortedAfterwards = vi.spyOn(xhr, 'abort')
    controller.abort()

    expect(abortedAfterwards).not.toHaveBeenCalled()
  })
})
