/**
 * The Documents API client (ON-42).
 */
import { describe, expect, it, vi } from 'vitest'

import { createApiClient } from './client'
import { FILE_FIELD, uploadDocument } from './documents'

function clientThatRecords() {
  const upload = vi.fn().mockResolvedValue({ id: 1 })
  return { client: { request: vi.fn(), upload, token: null }, upload }
}

describe('uploading a document', () => {
  it('posts to the endpoint the contracts name', async () => {
    const { client, upload } = clientThatRecords()

    await uploadDocument(client, new File(['x'], 'handbook.pdf'))

    expect(upload).toHaveBeenCalledWith('/documents', expect.any(FormData), {})
  })

  it('sends the file under the field name the server reads', async () => {
    const { client, upload } = clientThatRecords()
    const file = new File(['policy text'], 'handbook.pdf', { type: 'application/pdf' })

    await uploadDocument(client, file)

    // The literal 'file', not FILE_FIELD. Asserting against the same
    // constant the code uses makes the test agree with whatever that
    // constant says - rename it to 'document' and both sides move
    // together, so nothing fails. The server reads a field called 'file',
    // and that string is the fact worth pinning. The fault-injection pass
    // is what caught this: renaming the constant broke the upload and no
    // test minded.
    const sent = upload.mock.calls[0][1] as FormData
    const got = sent.get('file') as File
    expect(got).not.toBeNull()
    expect(got.name).toBe('handbook.pdf')
    expect(got.type).toBe('application/pdf')
    expect(got.size).toBe(file.size)
  })

  it('exports the field name the server actually reads', () => {
    expect(FILE_FIELD).toBe('file')
  })

  it('keeps the filename, so it is not stored as "blob"', async () => {
    // A File carries its own name and FormData uses it, so this passes
    // without `append`'s third argument - which is why that argument is
    // not there. What is being guarded is that a File is sent rather than
    // a bare Blob, since a Blob has no name and arrives as "blob".
    const { client, upload } = clientThatRecords()

    await uploadDocument(client, new File(['x'], 'leave-policy.pdf'))

    const sent = upload.mock.calls[0][1] as FormData
    expect((sent.get('file') as File).name).toBe('leave-policy.pdf')
  })

  it('passes progress and abort straight through', async () => {
    const { client, upload } = clientThatRecords()
    const onProgress = vi.fn()
    const signal = new AbortController().signal

    await uploadDocument(client, new File(['x'], 'a.txt'), { onProgress, signal })

    expect(upload).toHaveBeenCalledWith('/documents', expect.any(FormData), {
      onProgress,
      signal,
    })
  })

  it('returns what the server said about the document', async () => {
    const saved = {
      id: 12,
      filename: 'handbook.pdf',
      content_type: 'application/pdf',
      size_bytes: 2048,
      uploaded_at: '2026-11-14T09:00:00Z',
    }
    const client = { request: vi.fn(), upload: vi.fn().mockResolvedValue(saved), token: null }

    await expect(uploadDocument(client, new File(['x'], 'handbook.pdf'))).resolves.toEqual(saved)
  })
})

describe('the client’s own upload method', () => {
  it('puts the base url in front of the path', async () => {
    const uploadImpl = vi.fn().mockResolvedValue({ id: 1 })
    const client = createApiClient({ baseUrl: 'http://backend.test/api', uploadImpl })

    await client.upload('/documents', new FormData())

    expect(uploadImpl).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'http://backend.test/api/documents' }),
    )
  })

  it('hands the transport the token and the sign-out callback', async () => {
    // The whole reason the upload goes through the client rather than
    // being called from the page: one place attaches the token, and one
    // place decides what a 401 means.
    const uploadImpl = vi.fn().mockResolvedValue({ id: 1 })
    const onUnauthorised = vi.fn()
    const client = createApiClient({ token: 'a-token', onUnauthorised, uploadImpl })

    await client.upload('/documents', new FormData())

    expect(uploadImpl).toHaveBeenCalledWith(
      expect.objectContaining({ token: 'a-token', onUnauthorised }),
    )
  })
})
