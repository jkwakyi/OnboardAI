/**
 * A drivable stand-in for XMLHttpRequest (ON-42).
 *
 * jsdom ships an XMLHttpRequest that really tries to open a socket, so a
 * test using it either hits the network or waits for a timeout. This one
 * records what was sent and lets the test decide when — and how — the
 * request finishes.
 *
 * It exists so the page tests can exercise the *real* path:
 * `SessionProvider` builds the real API client, which calls the real
 * `uploadWithProgress`, which drives this. Injecting a fake upload
 * function instead would test the page against a contract nothing else
 * obeys, and would never notice if the client stopped attaching the
 * token.
 */

export interface SentRequest {
  method: string
  url: string
  headers: Record<string, string>
  body: unknown
}

type Listener = () => void

export class FakeXhr {
  status = 0
  responseText = ''

  readonly sent: SentRequest = { method: '', url: '', headers: {}, body: undefined }

  /** Set by the test; read back through `getResponseHeader`. */
  responseHeaders: Record<string, string> = {}

  private readonly listeners = new Map<string, Listener[]>()
  private readonly uploadListeners: ((event: ProgressEventLike) => void)[] = []

  readonly upload = {
    addEventListener: (type: string, listener: (event: ProgressEventLike) => void): void => {
      if (type === 'progress') this.uploadListeners.push(listener)
    },
  }

  open(method: string, url: string): void {
    this.sent.method = method
    this.sent.url = url
  }

  setRequestHeader(name: string, value: string): void {
    this.sent.headers[name] = value
  }

  send(body: unknown): void {
    this.sent.body = body
  }

  abort(): void {
    this.fire('abort')
  }

  addEventListener(type: string, listener: Listener): void {
    const existing = this.listeners.get(type) ?? []
    existing.push(listener)
    this.listeners.set(type, existing)
  }

  getResponseHeader(name: string): string | null {
    return this.responseHeaders[name] ?? null
  }

  // --- what a test drives ------------------------------------------------

  /** Report `loaded` of `total` bytes gone out. */
  progress(loaded: number, total = 100): void {
    for (const listener of this.uploadListeners) {
      listener({ lengthComputable: true, loaded, total })
    }
  }

  /**
   * Report progress the browser could not measure, which is what happens
   * for a body of unknown length.
   */
  immeasurableProgress(): void {
    for (const listener of this.uploadListeners) {
      listener({ lengthComputable: false, loaded: 0, total: 0 })
    }
  }

  /** Finish with a status and a JSON body. */
  respond(status: number, body?: unknown): void {
    this.status = status
    this.responseText = body === undefined ? '' : JSON.stringify(body)
    this.fire('load')
  }

  /** Finish with a body that is not JSON at all, such as a proxy's HTML. */
  respondWithGarbage(status: number, text: string): void {
    this.status = status
    this.responseText = text
    this.fire('load')
  }

  /** The request never arrived. */
  networkFailure(): void {
    this.fire('error')
  }

  timeout(): void {
    this.fire('timeout')
  }

  private fire(type: string): void {
    for (const listener of this.listeners.get(type) ?? []) listener()
  }
}

export interface ProgressEventLike {
  lengthComputable: boolean
  loaded: number
  total: number
}

/**
 * Replace `globalThis.XMLHttpRequest` and hand back the instances created.
 *
 * Returns the list rather than a single instance because the retry tests
 * make a second request, and asserting on the first one after a retry is
 * how a retry test passes without a retry having happened.
 */
export function stubXhr(): FakeXhr[] {
  const made: FakeXhr[] = []
  globalThis.XMLHttpRequest = function XMLHttpRequestStub(this: unknown) {
    const instance = new FakeXhr()
    made.push(instance)
    return instance
    // The cast is the point of the helper: a fake that satisfies the parts
    // of the interface our own code touches, and nothing else.
  } as unknown as typeof XMLHttpRequest
  return made
}
