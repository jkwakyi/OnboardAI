/**
 * Uploading a file, with progress (ON-42).
 *
 * This is `XMLHttpRequest` rather than `fetch`, and that is the whole
 * reason the file exists. `fetch` reports nothing about a request body on
 * its way out: there is no upload-progress event and no stream to count,
 * so a page built on it can show a spinner and nothing more. XHR has
 * `upload.onprogress`, which is the only way in a browser today to tell
 * somebody how far a 9 MB PDF has actually got.
 *
 * It lives beside `client.ts` and is wired into the same `ApiClient`
 * rather than being called directly from the page. The contracts give the
 * API Client the job of sending the login token, and a second way of
 * reaching the backend is a second place for that to be forgotten — along
 * with the 401 handling, the error wording and the base path. So the
 * transport differs here and nothing else does: the same `ApiError`, the
 * same `NetworkError`, the same `detailFrom` and `messageForStatus`.
 *
 * What the progress number does *not* cover is worth stating, because it
 * shapes the page. 100% means the last byte left the browser, not that
 * the document is done: the server then extracts its text and splits it
 * into sections before answering (U2 to U3, synchronously, by ON-39's
 * design). So the page shows the percentage while it climbs and then
 * stops claiming to know anything, rather than parking at 100% as though
 * it had finished.
 */
import { ApiError, NETWORK_MESSAGE, NetworkError, detailFrom, messageForStatus } from './errors'

export interface UploadOptions {
  /**
   * Called with 0 to 100 as the body goes out.
   *
   * Only when the browser knows the total. For a request whose length is
   * not computable it is never called at all, which the page must cope
   * with — hence `null` for "uploading, extent unknown" rather than a
   * fake 0.
   */
  onProgress?: (percent: number) => void
  signal?: AbortSignal
}

/**
 * POST `formData` and parse the JSON that comes back.
 *
 * Rejects with `ApiError` for a refusal, `NetworkError` for a request that
 * never arrived, and a `DOMException` named `AbortError` when the caller
 * aborted — the same three outcomes, with the same wording, as a request
 * made through `client.ts`.
 */
export function uploadWithProgress<T>({
  url,
  formData,
  token,
  onUnauthorised,
  onProgress,
  signal,
  xhr = new XMLHttpRequest(),
}: {
  url: string
  formData: FormData
  token: string | null
  onUnauthorised?: () => void
  xhr?: XMLHttpRequest
} & UploadOptions): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted === true) {
      reject(abortError())
      return
    }

    xhr.open('POST', url)
    if (token !== null) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    // No Content-Type. The browser sets multipart/form-data along with the
    // boundary it generated, and setting the header by hand loses the
    // boundary - at which point the server cannot parse a request that
    // looks, from here, perfectly well formed.

    xhr.upload.addEventListener('progress', (event) => {
      // lengthComputable is false for a body the browser cannot measure.
      // Reporting 0% forever would be worse than reporting nothing.
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.min(100, (event.loaded / event.total) * 100))
      }
    })

    function cleanUp(): void {
      signal?.removeEventListener('abort', onAbort)
    }

    function onAbort(): void {
      xhr.abort()
      cleanUp()
      reject(abortError())
    }

    signal?.addEventListener('abort', onAbort)

    xhr.addEventListener('error', () => {
      // XHR gives no detail here, deliberately: distinguishing "offline"
      // from "blocked by CORS" would tell a page something about another
      // origin. Both are "it never arrived".
      cleanUp()
      reject(new NetworkError(NETWORK_MESSAGE))
    })

    xhr.addEventListener('timeout', () => {
      cleanUp()
      reject(new NetworkError(NETWORK_MESSAGE))
    })

    xhr.addEventListener('abort', () => {
      // Only reached when something other than our own signal aborted it.
      cleanUp()
      reject(abortError())
    })

    xhr.addEventListener('load', () => {
      cleanUp()

      if (xhr.status === 401) {
        // Before reading the body, exactly as client.ts does: whatever it
        // says, the session is over.
        onUnauthorised?.()
      }

      const body = parseBody(xhr.responseText)

      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          new ApiError(
            xhr.status,
            detailFrom(body) ?? messageForStatus(xhr.status),
            retryAfterFrom(xhr),
          ),
        )
        return
      }

      if (body === undefined) {
        reject(new ApiError(xhr.status, 'The server sent a reply that could not be read.'))
        return
      }

      resolve(body as T)
    })

    xhr.send(formData)
  })
}

/**
 * The same rejection `fetch` gives for an aborted request, so a caller can
 * check for it one way regardless of which transport ran.
 */
function abortError(): DOMException {
  return new DOMException('The upload was aborted.', 'AbortError')
}

function parseBody(text: string): unknown {
  if (text === '') return undefined
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined
  }
}

function retryAfterFrom(xhr: XMLHttpRequest): number | null {
  const header = xhr.getResponseHeader('Retry-After')
  if (header === null) return null
  const seconds = Number.parseInt(header, 10)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}
