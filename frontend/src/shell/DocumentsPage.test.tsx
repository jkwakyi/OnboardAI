/**
 * The Admin Upload Page (ON-42).
 *
 * One test per state the ticket names — idle, file chosen, uploading,
 * success, validation error, server error with a retry — plus the state
 * the ticket does not name but the server creates: the gap after the last
 * byte is up and before the server has finished reading the document.
 *
 * These drive the real path. `renderApp` builds a real `SessionProvider`,
 * which builds a real API client, which calls the real transport, which
 * drives a fake `XMLHttpRequest`. Nothing between the button and the
 * socket is mocked out, so a change that stopped the client attaching the
 * token would fail here rather than passing against a stubbed upload.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { EMPTY_FILE_MESSAGE, WRONG_TYPE_MESSAGE } from '../components'
import { stubXhr, type FakeXhr } from '../test/fakeXhr'
import { HR_TOKEN, renderApp } from '../test/renderApp'
import { SUCCESS_DETAIL, SUCCESS_TITLE, canRetry } from './DocumentsPage'
import { ApiError, NetworkError } from '../api'

/**
 * What the server actually answers 201 with.
 *
 * `content_type` is the bare string `pdf` or `txt`, not a MIME type: the
 * Document Upload service settles the kind from the file's own bytes and
 * stores its own two-value vocabulary. Checked against the running
 * backend rather than assumed — a fixture carrying `application/pdf`
 * would have let this page render something the real server never sends.
 */
const SAVED = {
  id: 12,
  filename: 'handbook.pdf',
  content_type: 'pdf',
  size_bytes: 2048,
  uploaded_at: '2026-11-14T09:00:00Z',
}

let requests: FakeXhr[]
const realXhr = globalThis.XMLHttpRequest

function pdf(name = 'handbook.pdf'): File {
  return new File(['%PDF-1.4 some policy text'], name, { type: 'application/pdf' })
}

/**
 * A file the dropzone will reject on its extension.
 *
 * The MIME type is `text/plain` deliberately. The file input carries an
 * `accept` list, and `userEvent.upload` honours it the way the real file
 * picker does — a file matching neither an accepted extension nor an
 * accepted type is discarded before any change event fires, so the
 * component never sees it and never reports an error. A `.docx` labelled
 * `text/plain` gets past the picker and is then caught by the extension
 * check, which is also exactly what a mislabelled file does in real life.
 */
function wrongType(name = 'notes.docx'): File {
  return new File(['some notes'], name, { type: 'text/plain' })
}

function open() {
  return renderApp({ path: '/documents', token: HR_TOKEN })
}

/** Choose a file and press Upload, leaving the request in flight. */
async function startUpload(file = pdf()): Promise<FakeXhr> {
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText(/drop a document here/i), file)
  await user.click(screen.getByRole('button', { name: 'Upload' }))

  await waitFor(() => {
    expect(requests).toHaveLength(1)
  })
  return requests[0]
}

beforeEach(() => {
  requests = stubXhr()
})

afterEach(() => {
  globalThis.XMLHttpRequest = realXhr
  vi.restoreAllMocks()
})

describe('before anything is chosen', () => {
  it('invites a file and says which kinds', () => {
    open()

    expect(screen.getByText(/drop a document here/i)).toBeInTheDocument()
    expect(screen.getByText('PDF or TXT')).toBeInTheDocument()
  })

  it('cannot be uploaded', () => {
    open()

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('sends nothing', () => {
    open()

    expect(requests).toHaveLength(0)
  })
})

describe('when a file has been chosen', () => {
  it('names it, with its size', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(screen.getByLabelText(/drop a document here/i), pdf('leave-policy.pdf'))

    expect(screen.getByText('leave-policy.pdf')).toBeInTheDocument()
    expect(screen.getByText('25 B')).toBeInTheDocument()
  })

  it('can now be uploaded', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(screen.getByLabelText(/drop a document here/i), pdf())

    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled()
  })

  it('has still sent nothing until the button is pressed', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(screen.getByLabelText(/drop a document here/i), pdf())

    expect(requests).toHaveLength(0)
  })
})

describe('while it is uploading', () => {
  it('sends the file to the documents endpoint, with the token', async () => {
    open()
    const xhr = await startUpload()

    expect(xhr.sent.method).toBe('POST')
    expect(xhr.sent.url).toMatch(/\/documents$/)
    expect(xhr.sent.headers.Authorization).toBe(`Bearer ${HR_TOKEN}`)
  })

  it('shows how far the file has got', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.progress(40, 100)
    })

    expect(screen.getByRole('img', { name: 'Uploaded: 40%' })).toBeInTheDocument()
  })

  it('names the file being uploaded', async () => {
    open()
    const xhr = await startUpload(pdf('leave-policy.pdf'))

    act(() => {
      xhr.progress(40, 100)
    })

    expect(screen.getByText('Uploading leave-policy.pdf')).toBeInTheDocument()
  })

  it('cannot be uploaded again while it is in flight', async () => {
    open()
    await startUpload()

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('will not take another file while it is in flight', async () => {
    open()
    await startUpload()

    expect(screen.getByLabelText(/drop a document here/i)).toBeDisabled()
  })
})

describe('once the bytes are up but the server is still reading', () => {
  it('stops reporting a percentage', async () => {
    // A ring parked at 100% while the server extracts the text reads as a
    // hung page. The server does that work before it answers, so there is
    // a real gap here and it is not a percentage of anything.
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.progress(100, 100)
    })

    expect(screen.queryByRole('img', { name: /uploaded/i })).not.toBeInTheDocument()
  })

  it('says it is being read, not that it is still uploading', async () => {
    open()
    const xhr = await startUpload(pdf('leave-policy.pdf'))

    act(() => {
      xhr.progress(100, 100)
    })

    expect(screen.getByText('Reading leave-policy.pdf')).toBeInTheDocument()
    expect(screen.queryByText(/^Uploading /)).not.toBeInTheDocument()
  })

  it('announces the change rather than leaving it to be noticed', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.progress(100, 100)
    })

    expect(screen.getByText(/^Reading /)).toHaveAttribute('aria-live', 'polite')
  })

  it('is not dragged back by a late progress event', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.progress(100, 100)
      xhr.progress(60, 100)
    })

    expect(screen.getByText(/^Reading /)).toBeInTheDocument()
  })

  it('survives a progress event arriving after the answer', async () => {
    // Not hypothetical, and not merely untidy: the branch that moves to
    // 'reading' reads the file out of the current state, and a finished
    // state has no file in it. An unguarded late event therefore replaces
    // the success card with "Reading undefined".
    open()
    const xhr = await startUpload()
    act(() => {
      xhr.respond(201, SAVED)
    })
    await screen.findByText(SUCCESS_TITLE)

    act(() => {
      xhr.progress(100, 100)
    })

    expect(screen.getByText(SUCCESS_TITLE)).toBeInTheDocument()
    expect(screen.queryByText(/^Reading /)).not.toBeInTheDocument()
  })
})

describe('when the upload succeeds', () => {
  it('says the document was saved', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(201, SAVED)
    })

    expect(await screen.findByText(SUCCESS_TITLE)).toBeInTheDocument()
  })

  it('says the document can now be found', async () => {
    // Until ON-41 this asserted the opposite: U4 did not exist, so the
    // page had to say the document could not answer questions yet. The
    // upload now embeds its sections before it answers at all - a 201
    // means the vectors are stored - so the careful wording has become
    // the lie, and claiming less than is true sends an HR administrator
    // off to re-upload a document that was fine.
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(201, SAVED)
    })

    expect(await screen.findByText(SUCCESS_DETAIL)).toBeInTheDocument()
    expect(screen.queryByText(/not connected/i)).not.toBeInTheDocument()
  })

  it('shows what the server recorded, not what was chosen', async () => {
    // The server settles the content type and the stored filename, and a
    // page that echoed its own copy would hide any disagreement.
    open()
    const xhr = await startUpload(pdf('chosen-name.pdf'))

    act(() => {
      xhr.respond(201, { ...SAVED, filename: 'handbook.pdf' })
    })

    expect(await screen.findByText('handbook.pdf')).toBeInTheDocument()
    expect(screen.getByText('pdf')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB')).toBeInTheDocument()
  })

  it('stops showing progress', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.progress(50, 100)
      xhr.respond(201, SAVED)
    })

    await screen.findByText(SUCCESS_TITLE)
    expect(screen.queryByText(/^Uploading /)).not.toBeInTheDocument()
  })
})

describe('when the file itself is refused', () => {
  it('shows the wrong-type message without sending anything', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(screen.getByLabelText(/drop a document here/i), wrongType())

    expect(screen.getByText(WRONG_TYPE_MESSAGE)).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('shows the empty-file message without sending anything', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(
      screen.getByLabelText(/drop a document here/i),
      new File([], 'empty.txt', { type: 'text/plain' }),
    )

    expect(screen.getByText(EMPTY_FILE_MESSAGE)).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('cannot be uploaded', async () => {
    const user = userEvent.setup()
    open()

    await user.upload(screen.getByLabelText(/drop a document here/i), wrongType())

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('clears an earlier result, so it is not read as this file’s', async () => {
    const user = userEvent.setup()
    open()
    const xhr = await startUpload()
    act(() => {
      xhr.respond(201, SAVED)
    })
    await screen.findByText(SUCCESS_TITLE)

    await user.upload(screen.getByLabelText(/drop a document here/i), wrongType())

    expect(screen.queryByText(SUCCESS_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the server refuses it', () => {
  it('shows the backend’s own wording', async () => {
    // It knows why it refused the file. This page does not, and should
    // not be guessing from a status code when a sentence was supplied.
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(422, { detail: 'That document contains no readable text.' })
    })

    expect(await screen.findByText('That document contains no readable text.')).toBeInTheDocument()
  })

  it('announces the failure', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(413, { detail: 'That file is too large.' })
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('That file is too large.')
  })

  it('offers no retry for a file that will be refused identically', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(415, { detail: 'Only PDF and TXT documents are accepted.' })
    })

    await screen.findByText('Upload failed')
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('offers a retry when the server merely broke', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.respond(500, { detail: 'The document could not be read. Please try again.' })
    })

    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('actually sends the file again on retry', async () => {
    const user = userEvent.setup()
    open()
    const xhr = await startUpload()
    act(() => {
      xhr.respond(500, {})
    })

    await user.click(await screen.findByRole('button', { name: 'Try again' }))

    await waitFor(() => {
      expect(requests).toHaveLength(2)
    })
    expect(requests[1].sent.body).toBeInstanceOf(FormData)
  })

  it('succeeds on a retry that works', async () => {
    const user = userEvent.setup()
    open()
    const first = await startUpload()
    act(() => {
      first.respond(500, {})
    })
    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    await waitFor(() => {
      expect(requests).toHaveLength(2)
    })

    act(() => {
      requests[1].respond(201, SAVED)
    })

    expect(await screen.findByText(SUCCESS_TITLE)).toBeInTheDocument()
    expect(screen.queryByText('Upload failed')).not.toBeInTheDocument()
  })
})

describe('when the server cannot be reached', () => {
  it('says so, and offers a retry', async () => {
    open()
    const xhr = await startUpload()

    act(() => {
      xhr.networkFailure()
    })

    expect(await screen.findByText(/could not be reached/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('deciding whether a retry is worth offering', () => {
  it.each([400, 413, 415, 422])('is pointless for %d, which is about the file', (status) => {
    expect(canRetry(new ApiError(status, 'no'))).toBe(false)
  })

  it.each([429, 500, 502, 503])('is worth it for %d, which is about the server', (status) => {
    expect(canRetry(new ApiError(status, 'no'))).toBe(true)
  })

  it('is worth it when the request never arrived', () => {
    expect(canRetry(new NetworkError('no'))).toBe(true)
  })

  it('is not offered for something this page does not understand', () => {
    expect(canRetry(new TypeError('something else entirely'))).toBe(false)
  })
})

describe('who may open it', () => {
  it('is not available to an employee', async () => {
    const { EMPLOYEE_TOKEN } = await import('../test/tokens')
    renderApp({ path: '/documents', token: EMPLOYEE_TOKEN })

    expect(screen.queryByText(/drop a document here/i)).not.toBeInTheDocument()
  })
})
