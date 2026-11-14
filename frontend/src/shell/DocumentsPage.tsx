/**
 * The Admin Upload Page (ON-42).
 *
 * An HR administrator chooses a PDF or TXT file, uploads it, and sees what
 * happened to it. HR only, which `RequireRole` enforces here and Auth
 * Check (ON-14) enforces again on the request — the page's own guard is a
 * courtesy to the person, not the control.
 *
 * Two things about this page are deliberate and would be easy to get
 * wrong by being more optimistic.
 *
 * **The upload has two halves, and only the first has a percentage.**
 * The progress number is bytes leaving the browser. When it reaches 100
 * the server has not finished: it then extracts the document's text and
 * splits it into sections before it answers (U2 to U3, synchronously, by
 * ON-39's design — and it discards the whole upload if that second half
 * fails). A bar parked at 100% while the server works reads as a hung
 * page, so this says "Reading the document" instead and stops claiming a
 * number it does not have.
 *
 * **The pill is the upload's state, not the document's.** The Interface
 * Contracts define no status field for a document — `GET /api/documents`
 * is specified as "The uploaded documents" and the backend's response
 * carries id, filename, content type, size and uploaded-at, nothing more.
 * So rather than invent a status vocabulary, the pill reports what this
 * page actually witnessed happening.
 */
import { useCallback, useState, type ReactNode } from 'react'

import { ApiError, NetworkError, uploadDocument, type UploadedDocument } from '../api'
import {
  Button,
  Card,
  FileDropzone,
  ProgressRing,
  StatusPill,
  formatFileSize,
  type StatusVariant,
} from '../components'
import { useSession } from '../session/SessionContext'
import './DocumentsPage.css'

/**
 * What the page is doing, as one value.
 *
 * A union rather than a handful of booleans, because the booleans permit
 * states that cannot happen — uploading and failed at once, a progress
 * number with no file — and the render then has to decide which of two
 * contradictory flags to believe.
 */
type Upload =
  | { phase: 'idle' }
  | { phase: 'chosen'; file: File }
  /** `percent` is null when the browser cannot measure the body. */
  | { phase: 'sending'; file: File; percent: number | null }
  /** Every byte is up; the server is extracting the text. */
  | { phase: 'reading'; file: File }
  | { phase: 'done'; document: UploadedDocument }
  | { phase: 'failed'; file: File; message: string; canRetry: boolean }

/**
 * Whether trying the same file again could work.
 *
 * A refused *file* will be refused identically however many times it is
 * sent, and offering Retry for one is an invitation to find that out the
 * slow way. A refused *request* — the server was down, busy, or broke —
 * is worth another go with the file already chosen.
 */
export function canRetry(failure: unknown): boolean {
  if (failure instanceof NetworkError) return true
  if (failure instanceof ApiError) {
    // 413 too large, 415 wrong type, 422 nothing readable in it, 400
    // empty or unnamed: all properties of this file.
    return ![400, 413, 415, 422].includes(failure.status)
  }
  return false
}

export const SUCCESS_TITLE = 'Document saved'

/**
 * What a successful upload actually achieved, said plainly.
 *
 * It does *not* say the document is searchable, because it is not yet:
 * turning its sections into vectors is U4, which is ON-41, which is
 * waiting on the Embedding API key (ON-10). Telling an HR administrator
 * their policy is now answerable when no question can reach it would be
 * the most useful-sounding lie this page could tell.
 */
export const SUCCESS_DETAIL =
  'The file is stored and its text has been read and split into sections. Answering questions from it also needs the Embedding API, which is not connected yet.'

/** The file this state is about, where it has one. */
function fileOf(upload: Upload): File | null {
  return upload.phase === 'idle' || upload.phase === 'done' ? null : upload.file
}

export default function DocumentsPage() {
  const { api } = useSession()
  const [upload, setUpload] = useState<Upload>({ phase: 'idle' })

  const send = useCallback(
    async (file: File): Promise<void> => {
      setUpload({ phase: 'sending', file, percent: 0 })

      try {
        const document = await uploadDocument(api, file, {
          onProgress: (percent) => {
            setUpload((current) => {
              // Only while still sending, and not merely for tidiness. A
              // progress event can land after the response has already
              // resolved, and the branch below reads `current.file` - which
              // a 'done' state does not have. Without this line a late
              // 100% event replaces the success card with "Reading
              // undefined".
              if (current.phase !== 'sending') return current
              // Every byte is up, so there is nothing left to measure:
              // what remains is the server reading the document, which
              // has no percentage attached to it.
              if (percent >= 100) return { phase: 'reading', file: current.file }
              return { ...current, percent }
            })
          },
        })
        setUpload({ phase: 'done', document })
      } catch (failure) {
        if (failure instanceof ApiError || failure instanceof NetworkError) {
          setUpload({ phase: 'failed', file, message: failure.message, canRetry: canRetry(failure) })
          return
        }
        throw failure
      }
    },
    [api],
  )

  const choose = useCallback((file: File): void => {
    setUpload({ phase: 'chosen', file })
  }, [])

  /** The dropzone rejected the file and is showing why. */
  const reject = useCallback((): void => {
    // Back to idle, so a previous success or failure is not left on screen
    // above a validation message about a different file entirely.
    setUpload({ phase: 'idle' })
  }, [])

  const busy = upload.phase === 'sending' || upload.phase === 'reading'
  const ready = fileOf(upload)

  return (
    <div className="documents">
      <Card label="Upload a document">
        <p className="documents__lead">
          PDF or TXT. The document is read when it is uploaded, so anything it cannot read is
          refused rather than stored.
        </p>

        <FileDropzone disabled={busy} onError={reject} onFileSelected={choose} />

        <Button
          // `loading` is what stops a second press: Button disables itself
          // while loading, and also sets aria-busy and swaps in the
          // spinner. `disabled={... || busy}` alongside it was redundant,
          // and worse than redundant - it masked the loss of `loading`
          // from the fault-injection pass, so the one guard that actually
          // matters was untested.
          disabled={ready === null}
          loading={busy}
          onClick={() => {
            if (ready !== null) void send(ready)
          }}
        >
          Upload
        </Button>
      </Card>

      {busy && <Progress upload={upload} />}
      {upload.phase === 'done' && <Succeeded document={upload.document} />}
      {upload.phase === 'failed' && (
        <Failed
          message={upload.message}
          onRetry={upload.canRetry ? () => void send(upload.file) : undefined}
        />
      )}
    </div>
  )
}

function Progress({ upload }: { upload: Extract<Upload, { phase: 'sending' | 'reading' }> }) {
  // The ring is only drawn while there is a measurable number to draw.
  // Once the bytes are up, or when the browser could never measure them,
  // a ring would either sit full or sit at nothing - both of which read
  // as a stuck page rather than as work in progress.
  const sending = upload.phase === 'sending' && upload.percent !== null

  return (
    <Card label="Uploading">
      <div className="documents__progress">
        {sending && (
          <ProgressRing accent="documents" label="Uploaded" value={upload.percent ?? 0} />
        )}
        {/* aria-live, so the move from sending to reading is announced
            rather than being a silent change somebody has to go and
            check. Polite: it is progress, not a problem. */}
        <p aria-live="polite" className="documents__phase">
          {upload.phase === 'sending'
            ? `Uploading ${upload.file.name}`
            : `Reading ${upload.file.name}`}
        </p>
      </div>
    </Card>
  )
}

function Succeeded({ document }: { document: UploadedDocument }) {
  return (
    <Card label="Result">
      <Outcome title={SUCCESS_TITLE} variant="success" />
      <p className="documents__detail">{SUCCESS_DETAIL}</p>
      <dl className="documents__facts">
        <Fact label="File">{document.filename}</Fact>
        <Fact label="Size">{formatFileSize(document.size_bytes)}</Fact>
        <Fact label="Type">{document.content_type}</Fact>
      </dl>
    </Card>
  )
}

function Failed({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card label="Result">
      <Outcome title="Upload failed" variant="danger" />
      {/* role="alert" so it is announced when it appears. The text is the
          backend's own wording where it sent any - it knows why it
          refused the file, and this page does not. */}
      <p className="documents__detail" role="alert">
        {message}
      </p>
      {onRetry !== undefined && (
        <Button onClick={onRetry} variant="secondary">
          Try again
        </Button>
      )}
    </Card>
  )
}

function Outcome({ title, variant }: { title: string; variant: StatusVariant }) {
  return (
    <p className="documents__outcome">
      <StatusPill variant={variant}>{title}</StatusPill>
    </p>
  )
}

function Fact({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="documents__fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}
