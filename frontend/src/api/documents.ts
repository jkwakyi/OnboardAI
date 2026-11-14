/**
 * The Documents API, as the Admin Upload Page calls it (ON-42).
 *
 * The contracts give three endpoints to this page: `POST /api/documents`,
 * `GET /api/documents` and `DELETE /api/documents/{id}`. Only POST exists
 * on the server today — listing and deleting are ON-16 — so only POST is
 * here. A client function for an endpoint that returns 404 is worse than
 * no function: it looks callable.
 *
 * The response shape is the backend's `DocumentResponse` and nothing more.
 * Notably it carries **no status field**, and neither do the contracts,
 * which describe `GET /api/documents` only as "The uploaded documents".
 * So nothing here invents one, and the page shows the state of *the
 * upload* — which it genuinely knows — rather than a document status it
 * would have had to make up.
 */
import type { ApiClient } from './client'
import type { UploadOptions } from './upload'

/** An uploaded document, exactly as the backend reports it. */
export interface UploadedDocument {
  id: number
  filename: string
  /** `application/pdf` or `text/plain`, as the server settled it. */
  content_type: string
  size_bytes: number
  /** ISO 8601, from the server's clock. */
  uploaded_at: string
}

/** The field name `POST /api/documents` reads the file from. */
export const FILE_FIELD = 'file'

/**
 * Upload one PDF or TXT document.
 *
 * Resolves once the server has saved the file *and* split its text into
 * sections: ON-39 does both before answering, and discards the whole
 * upload if the second half fails. So a document that comes back here is
 * one that was stored and read, never one of the two.
 */
export function uploadDocument(
  client: ApiClient,
  file: File,
  options: UploadOptions = {},
): Promise<UploadedDocument> {
  const form = new FormData()
  // No third argument. `append` takes an explicit filename, and it is
  // tempting to pass `file.name` for safety, but a File already carries
  // its own name and FormData uses it - the parameter only matters for a
  // nameless Blob, which is what gets sent as "blob". Passing it here
  // changed nothing, which the fault-injection pass proved by breaking it
  // and watching every test stay green.
  form.append(FILE_FIELD, file)

  return client.upload<UploadedDocument>('/documents', form, options)
}
