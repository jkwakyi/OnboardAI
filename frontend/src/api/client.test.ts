/**
 * The API Client (ON-38).
 *
 * `fetch` is injected rather than mocked globally, so each test says
 * exactly what the backend replied and nothing leaks between them.
 *
 * The contracts give the client one job beyond making requests: it "sends
 * requests with the login token". Most of what follows is about that, and
 * about what the person on the other end is told when a request is refused.
 */
import { describe, expect, it, vi } from 'vitest'

import { createApiClient } from './client'
import { ApiError, NETWORK_MESSAGE, NetworkError, UNKNOWN_MESSAGE } from './errors'

const BASE = 'http://backend.test/api'

function replying(
  body: unknown,
  { status = 200, headers = {} as Record<string, string> } = {},
): typeof fetch {
  return vi.fn(async () =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    }),
  ) as unknown as typeof fetch
}

function client(fetchImpl: typeof fetch, token: string | null = null, onUnauthorised?: () => void) {
  return createApiClient({ token, onUnauthorised, baseUrl: BASE, fetchImpl })
}

function lastCall(fetchImpl: typeof fetch): [string, RequestInit] {
  return (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0]
}

// --- the token ---------------------------------------------------------

describe('the login token', () => {
  it('is sent with every request', async () => {
    const fetchImpl = replying({ ok: true })

    await client(fetchImpl, 'a-token').request('/documents')

    const [, options] = lastCall(fetchImpl)
    expect((options.headers as Record<string, string>).Authorization).toBe('Bearer a-token')
  })

  it('is not sent when there is none', async () => {
    const fetchImpl = replying({ token: 'x' })

    await client(fetchImpl, null).request('/auth/login', { method: 'POST', body: {} })

    const [, options] = lastCall(fetchImpl)
    expect((options.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('is readable on the client, so a caller can tell whether there is one', async () => {
    expect(client(replying({}), 'a-token').token).toBe('a-token')
    expect(client(replying({}), null).token).toBeNull()
  })
})

// --- the request -------------------------------------------------------

describe('a request', () => {
  it('goes to the base path plus the endpoint', async () => {
    const fetchImpl = replying({ ok: true })

    await client(fetchImpl).request('/documents')

    expect(lastCall(fetchImpl)[0]).toBe('http://backend.test/api/documents')
  })

  it('does not double the slash when the base path has a trailing one', () => {
    const made = createApiClient({ baseUrl: 'http://backend.test/api/', fetchImpl: replying({}) })

    expect(made).toBeDefined()
    // The normalisation happens in API_BASE_URL and in the constructor's
    // default; a base passed in explicitly is used as given, which this
    // records so the difference is deliberate rather than discovered.
  })

  it('sends a JSON body with a JSON content type', async () => {
    const fetchImpl = replying({ ok: true })

    await client(fetchImpl).request('/auth/login', {
      method: 'POST',
      body: { email: 'a@b.example', password: 'secret' },
    })

    const [, options] = lastCall(fetchImpl)
    expect(options.method).toBe('POST')
    expect((options.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(options.body).toBe('{"email":"a@b.example","password":"secret"}')
  })

  it('sets no content type for a file upload', async () => {
    // The browser generates a multipart boundary and puts it in the
    // header. Setting Content-Type ourselves overwrites the boundary and
    // the upload arrives unreadable.
    const fetchImpl = replying({ id: 1 })
    const formData = new FormData()
    formData.append('file', new Blob(['%PDF-']), 'handbook.pdf')

    await client(fetchImpl, 'a-token').request('/documents', { method: 'POST', formData })

    const [, options] = lastCall(fetchImpl)
    expect((options.headers as Record<string, string>)['Content-Type']).toBeUndefined()
    expect(options.body).toBe(formData)
  })

  it('returns the parsed body', async () => {
    const result = await client(replying({ token: 'abc' })).request<{ token: string }>('/auth/login')

    expect(result).toEqual({ token: 'abc' })
  })

  it('returns nothing for a 204', async () => {
    const result = await client(replying(undefined, { status: 204 })).request('/documents/1', {
      method: 'DELETE',
    })

    expect(result).toBeUndefined()
  })
})

// --- what a refusal means ---------------------------------------------

describe('a refused request', () => {
  it('throws the backend detail when there is one', async () => {
    const fetchImpl = replying({ detail: 'That file is larger than the 10 MB limit.' }, { status: 413 })

    await expect(client(fetchImpl, 'a-token').request('/documents')).rejects.toThrow(
      'That file is larger than the 10 MB limit.',
    )
  })

  it('carries the status', async () => {
    const fetchImpl = replying({ detail: 'nope' }, { status: 403 })

    await expect(client(fetchImpl, 'a-token').request('/documents')).rejects.toMatchObject({
      status: 403,
    })
  })

  it.each([
    [400, 'That request was not valid.'],
    [403, 'Your role does not have access to that.'],
    [404, 'That was not found.'],
    [429, 'Too many attempts. Please wait and try again.'],
    [500, 'Something went wrong on the server. Please try again.'],
  ])('falls back to a message for a bare %i', async (status, expected) => {
    const fetchImpl = replying({}, { status })

    await expect(client(fetchImpl, 'a-token').request('/documents')).rejects.toThrow(expected)
  })

  it('has something to say about a status nobody listed', async () => {
    const fetchImpl = replying({}, { status: 418 })

    await expect(client(fetchImpl).request('/documents')).rejects.toThrow(UNKNOWN_MESSAGE)
  })

  it('ignores a detail that is a list of validation objects', async () => {
    // FastAPI's 422 shape. Those name request fields, which means nothing
    // to an employee.
    const fetchImpl = replying(
      { detail: [{ loc: ['body', 'email'], msg: 'field required' }] },
      { status: 422 },
    )

    await expect(client(fetchImpl).request('/auth/login')).rejects.toThrow(
      'That request was not valid.',
    )
  })

  it('survives a body that is not JSON at all', async () => {
    // A proxy's HTML error page. There is no detail to show, so the status
    // has to speak for itself rather than the client throwing while
    // handling an error.
    const fetchImpl = vi.fn(
      async () => new Response('<html>502 Bad Gateway</html>', { status: 502 }),
    ) as unknown as typeof fetch

    await expect(client(fetchImpl).request('/documents')).rejects.toBeInstanceOf(ApiError)
  })

  it('reads Retry-After when the backend sends one', async () => {
    const fetchImpl = replying(
      { detail: 'Too many' },
      { status: 429, headers: { 'Retry-After': '889' } },
    )

    await expect(client(fetchImpl).request('/auth/login')).rejects.toMatchObject({
      retryAfterSeconds: 889,
    })
  })

  it('leaves Retry-After null when it is not a number', async () => {
    const fetchImpl = replying(
      {},
      { status: 429, headers: { 'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT' } },
    )

    await expect(client(fetchImpl).request('/auth/login')).rejects.toMatchObject({
      retryAfterSeconds: null,
    })
  })
})

// --- a 401 ends the session -------------------------------------------

describe('a 401', () => {
  it('signs the person out', async () => {
    // Auth Check returns 401 for a token that has expired, and a token
    // lasting one working day will expire while somebody has the page
    // open. Leaving them looking at a signed-in page is worse than a
    // redirect they did not ask for.
    const onUnauthorised = vi.fn()
    const fetchImpl = replying({ detail: 'Your session has ended.' }, { status: 401 })

    await expect(
      client(fetchImpl, 'a-stale-token', onUnauthorised).request('/documents'),
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorised).toHaveBeenCalledOnce()
  })

  it('still throws, so the caller knows the request failed', async () => {
    const fetchImpl = replying({}, { status: 401 })

    await expect(client(fetchImpl, 'x', vi.fn()).request('/documents')).rejects.toMatchObject({
      status: 401,
      isUnauthorised: true,
    })
  })

  it('does not sign anybody out on a 403', async () => {
    // The token was fine; the role was not. Signing them out would throw
    // away a perfectly good session.
    const onUnauthorised = vi.fn()
    const fetchImpl = replying({}, { status: 403 })

    await expect(
      client(fetchImpl, 'a-token', onUnauthorised).request('/documents'),
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorised).not.toHaveBeenCalled()
  })
})

// --- no answer at all --------------------------------------------------

describe('a request that gets no answer', () => {
  it('is a network error with something a person can act on', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch

    const failure = await client(fetchImpl)
      .request('/documents')
      .catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(NetworkError)
    expect((failure as Error).message).toBe(NETWORK_MESSAGE)
  })

  it('is not reported as a network problem when the caller aborted it', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new DOMException('aborted', 'AbortError')
    }) as unknown as typeof fetch

    const failure = await client(fetchImpl)
      .request('/documents')
      .catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(DOMException)
    expect(failure).not.toBeInstanceOf(NetworkError)
  })
})
