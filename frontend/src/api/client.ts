/**
 * The API Client (ON-38).
 *
 * The contracts give it one job beyond making requests: "The API Client
 * sends requests with the login token". So the token is held here, in one
 * place, and attached to every request — rather than being passed into each
 * call by whoever happens to be making it, which is how one call ends up
 * without it.
 *
 * `onUnauthorised` is the other half of the same idea. Auth Check returns
 * 401 for a token that has expired, and a token issued for one working day
 * will expire while somebody has the page open. Signing them out from here
 * means every page gets that behaviour without asking for it, instead of
 * each page discovering it separately.
 */
import { ApiError, NETWORK_MESSAGE, NetworkError, detailFrom, messageForStatus } from './errors'
import { uploadWithProgress, type UploadOptions } from './upload'

/**
 * Where the backend is.
 *
 * Vite replaces `import.meta.env.VITE_API_BASE_URL` at build time, so this
 * is baked into the bundle rather than read at runtime — which is why the
 * default has to be the one that works for a teammate who has not set it.
 */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'
).replace(/\/+$/, '')

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  /** Sent as JSON. For an upload, pass `formData` instead. */
  body?: unknown
  /** Sent as multipart/form-data, with no Content-Type of our own. */
  formData?: FormData
  signal?: AbortSignal
}

export interface ApiClient {
  request: <T>(path: string, options?: RequestOptions) => Promise<T>
  /**
   * POST a file and watch it go out.
   *
   * Separate from `request` because it is the one call that cannot be made
   * with `fetch`: there is no upload-progress event there, so a page built
   * on it could only show a spinner. `upload.ts` explains the rest.
   */
  upload: <T>(path: string, formData: FormData, options?: UploadOptions) => Promise<T>
  /** The token this client is sending, or null. */
  token: string | null
}

export function createApiClient({
  token = null,
  onUnauthorised,
  baseUrl = API_BASE_URL,
  fetchImpl = globalThis.fetch,
  uploadImpl = uploadWithProgress,
}: {
  token?: string | null
  /** Called when the backend says the token is no longer good. */
  onUnauthorised?: () => void
  baseUrl?: string
  fetchImpl?: typeof fetch
  /** For tests, which have no real XMLHttpRequest to drive. */
  uploadImpl?: typeof uploadWithProgress
} = {}): ApiClient {
  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, formData, signal } = options

    const headers: Record<string, string> = {}
    if (token !== null) {
      headers.Authorization = `Bearer ${token}`
    }
    // Only for a JSON body. Setting it for FormData would override the
    // boundary the browser generates and the upload would arrive unreadable.
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json'
    }

    let response: Response
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers,
        body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
        signal,
      })
    } catch (failure) {
      // An aborted request is the caller's own doing, not a network
      // problem, and must not be reported as one.
      if (failure instanceof DOMException && failure.name === 'AbortError') throw failure
      throw new NetworkError(NETWORK_MESSAGE)
    }

    if (response.status === 401) {
      // Before reading the body: whatever it says, the session is over,
      // and leaving a signed-out person looking at a signed-in page is
      // worse than a redirect they did not ask for.
      onUnauthorised?.()
    }

    if (!response.ok) {
      throw new ApiError(
        response.status,
        detailFrom(await readBody(response)) ?? messageForStatus(response.status),
        retryAfterFrom(response),
      )
    }

    if (response.status === 204) {
      return undefined as T
    }

    const parsed = await readBody(response)
    if (parsed === undefined) {
      throw new ApiError(response.status, 'The server sent a reply that could not be read.')
    }
    return parsed as T
  }

  function upload<T>(path: string, formData: FormData, options: UploadOptions = {}): Promise<T> {
    return uploadImpl<T>({
      url: `${baseUrl}${path}`,
      formData,
      token,
      onUnauthorised,
      ...options,
    })
  }

  return { request, upload, token }
}

/** The body as JSON, or undefined if it is not JSON at all. */
async function readBody(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown
  } catch {
    // A proxy's HTML error page, or an empty body. Either way there is no
    // detail to show and the status has to speak for itself.
    return undefined
  }
}

function retryAfterFrom(response: Response): number | null {
  const header = response.headers.get('Retry-After')
  if (header === null) return null
  const seconds = Number.parseInt(header, 10)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}
