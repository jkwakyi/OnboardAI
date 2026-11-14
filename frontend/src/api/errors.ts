/**
 * What a failed request means to the person who made it (ON-38).
 *
 * The backend answers with `{"detail": "..."}` — FastAPI's own shape, and
 * the one the Login API and Auth Check both use. That detail is written for
 * a person, so where there is one it is what gets shown; where there is
 * not, the status code decides.
 *
 * Nothing here invents a field. The contracts do not define an error body,
 * so this reads the framework's and falls back to the status.
 */

/** A request that reached the backend and came back refused. */
export class ApiError extends Error {
  readonly status: number
  /** Seconds to wait, from Retry-After, when the backend sent one. */
  readonly retryAfterSeconds: number | null

  constructor(status: number, message: string, retryAfterSeconds: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfterSeconds = retryAfterSeconds
  }

  /** The session is gone, rather than the request being wrong. */
  get isUnauthorised(): boolean {
    return this.status === 401
  }
}

/** A request that never got an answer: offline, DNS, the server is down. */
export class NetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

export const NETWORK_MESSAGE =
  'The server could not be reached. Check that the backend is running and try again.'

/**
 * What to say when the backend sent a status and no usable detail.
 *
 * 401 is deliberately not "your email or password is wrong": Auth Check
 * returns 401 for an expired or missing token on any request, and telling
 * somebody their password is wrong when their session merely ran out sends
 * them looking for the wrong problem.
 */
const BY_STATUS: Record<number, string> = {
  400: 'That request was not valid.',
  401: 'Your session has ended. Please sign in again.',
  403: 'Your role does not have access to that.',
  404: 'That was not found.',
  413: 'That file is too large.',
  415: 'That file type is not accepted.',
  422: 'That request was not valid.',
  429: 'Too many attempts. Please wait and try again.',
  500: 'Something went wrong on the server. Please try again.',
}

export const UNKNOWN_MESSAGE = 'Something went wrong. Please try again.'

export function messageForStatus(status: number): string {
  return BY_STATUS[status] ?? UNKNOWN_MESSAGE
}

/**
 * Read the backend's message out of a response body.
 *
 * FastAPI's 422 carries `detail` as a list of validation objects rather
 * than a string. Those name request fields, which means nothing to an
 * employee, so a list falls through to the status message.
 */
export function detailFrom(body: unknown): string | null {
  if (body === null || typeof body !== 'object') return null
  const detail = (body as { detail?: unknown }).detail
  return typeof detail === 'string' && detail.trim() !== '' ? detail : null
}
