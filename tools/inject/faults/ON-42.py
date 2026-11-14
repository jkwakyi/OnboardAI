"""Faults for the Admin Upload Page (ON-42).

The page has six states and a transport nothing else in the frontend uses,
so the question this pass answers is whether the tests notice a state
quietly collapsing into another one.

Three of these are faults somebody would introduce on purpose, each for a
plausible reason, and each is the kind of change a reviewer waves through:

* "Content-Type is set by hand" looks like tidying up an omission. It
  destroys the multipart boundary, and the request still looks perfectly
  well formed from the browser's side.
* "the success message is reverted to its pre-ON-41 wording" is a one-line
  change that looks like restoring careful hedging. Until U4 existed the
  page had to say the document could not answer questions yet; now that an
  upload embeds before it answers, that caution tells an HR administrator
  their policy is unreachable when it is already in the Vector Database -
  and sends them off to fix something that is not broken.
* "every failure offers a retry" is friendlier by one line, and invites
  somebody to re-send a 9 MB PDF that will be refused for exactly the same
  reason as before.
"""

TESTS = "src"
RUNNER = "vitest"
ROOT = "frontend"

UPLOAD = "src/api/upload.ts"
CLIENT = "src/api/client.ts"
DOCUMENTS = "src/api/documents.ts"
PAGE = "src/shell/DocumentsPage.tsx"
ROUTES = "src/shell/AppRoutes.tsx"

FAULTS = [
    # --- the request itself ---
    (
        "the login token is not sent with an upload",
        UPLOAD,
        "      xhr.setRequestHeader('Authorization', `Bearer ${token}`)",
        "      void token",
    ),
    (
        "Content-Type is set by hand, losing the multipart boundary",
        UPLOAD,
        "    xhr.open('POST', url)",
        "    xhr.open('POST', url)\n    xhr.setRequestHeader('Content-Type', 'multipart/form-data')",
    ),
    (
        "the upload is sent somewhere other than the documents endpoint",
        DOCUMENTS,
        "  return client.upload<UploadedDocument>('/documents', form, options)",
        "  return client.upload<UploadedDocument>('/upload', form, options)",
    ),
    (
        # Missed on the first pass, because the test asserted against
        # FILE_FIELD rather than the literal 'file' - so renaming the
        # constant moved the code and the assertion together and nothing
        # failed. The test now pins the string the server reads.
        "the file is sent under the wrong field name",
        DOCUMENTS,
        "export const FILE_FIELD = 'file'",
        "export const FILE_FIELD = 'document'",
    ),
    (
        # A Blob rather than the File. This is the real version of the
        # "stored as blob" hazard: `append`'s third argument turned out to
        # be a no-op for a File, which is why it is gone.
        "a nameless Blob is sent, so the server stores it as \"blob\"",
        DOCUMENTS,
        "  form.append(FILE_FIELD, file)",
        "  form.append(FILE_FIELD, new Blob([file]))",
    ),
    (
        "the base url is left off the upload path",
        CLIENT,
        "      url: `${baseUrl}${path}`,",
        "      url: path,",
    ),
    # --- progress ---
    (
        "progress is reported even when the browser cannot measure it",
        UPLOAD,
        "      if (event.lengthComputable && event.total > 0) {",
        "      if (true) {",
    ),
    (
        "progress is not clamped, so it can exceed 100",
        UPLOAD,
        "        onProgress?.(Math.min(100, (event.loaded / event.total) * 100))",
        "        onProgress?.((event.loaded / event.total) * 100)",
    ),
    (
        "progress is never reported at all",
        UPLOAD,
        "    xhr.upload.addEventListener('progress', (event) => {",
        "    ;(() => {})(() => {})\n    const _unused = (event: ProgressEvent) => {",
    ),
    (
        "the page never leaves 'sending', so the ring sits at 100%",
        PAGE,
        "              if (percent >= 100) return { phase: 'reading', file: current.file }",
        "              if (false) return { phase: 'reading', file: current.file }",
    ),
    (
        # Missed on the first pass as `if (current.phase === 'done')`,
        # which changed nothing observable: the spread below preserves
        # whatever phase it was given, so 'reading' stayed 'reading'. The
        # guard's real job is to keep the `>= 100` branch from reading
        # `current.file` out of a state that has none, which renders
        # "Reading undefined" over the success card.
        "a progress event arriving after the answer is not ignored",
        PAGE,
        "              if (current.phase !== 'sending') return current",
        "              void current",
    ),
    # --- what a success says ---
    (
        "the success message is reverted to its pre-ON-41 wording",
        PAGE,
        "  'The file is stored, its text has been read and split into sections, and those sections can now be found when an employee asks a question.'",
        "  'The file is stored and its text has been read and split into sections. Answering questions from it also needs the Embedding API, which is not connected yet.'",
    ),
    (
        "the page shows the chosen filename rather than the stored one",
        PAGE,
        "        <Fact label=\"File\">{document.filename}</Fact>",
        '        <Fact label="File">{\'chosen\'}</Fact>',
    ),
    # --- failures ---
    (
        "a refusal is reported with our own wording, not the backend's",
        PAGE,
        "          setUpload({ phase: 'failed', file, message: failure.message, canRetry: canRetry(failure) })",
        "          setUpload({ phase: 'failed', file, message: 'It did not work.', canRetry: canRetry(failure) })",
    ),
    (
        "every failure offers a retry, including a file that cannot work",
        PAGE,
        "    return ![400, 413, 415, 422].includes(failure.status)",
        "    return true",
    ),
    (
        "no failure offers a retry, not even a server that merely broke",
        PAGE,
        "  if (failure instanceof NetworkError) return true",
        "  if (failure instanceof NetworkError) return false",
    ),
    (
        "the failure is not announced",
        PAGE,
        '      <p className="documents__detail" role="alert">',
        '      <p className="documents__detail">',
    ),
    (
        "a network failure is reported as an API error",
        UPLOAD,
        "      reject(new NetworkError(NETWORK_MESSAGE))\n    })\n\n    xhr.addEventListener('timeout'",
        "      reject(new ApiError(0, NETWORK_MESSAGE))\n    })\n\n    xhr.addEventListener('timeout'",
    ),
    (
        "a 401 no longer ends the session",
        UPLOAD,
        "        onUnauthorised?.()",
        "        void onUnauthorised",
    ),
    (
        "a refusal is treated as a success",
        UPLOAD,
        "      if (xhr.status < 200 || xhr.status >= 300) {",
        "      if (xhr.status < 200 || xhr.status >= 600) {",
    ),
    (
        "an unreadable success body is resolved rather than refused",
        UPLOAD,
        "      if (body === undefined) {\n        reject(new ApiError(xhr.status, 'The server sent a reply that could not be read.'))\n        return\n      }",
        "      if (body === undefined) {\n        resolve(undefined as T)\n        return\n      }",
    ),
    # --- aborting ---
    (
        "aborting leaves the request running",
        UPLOAD,
        "    function onAbort(): void {\n      xhr.abort()",
        "    function onAbort(): void {",
    ),
    (
        "an already-aborted signal still starts the upload",
        UPLOAD,
        "    if (signal?.aborted === true) {\n      reject(abortError())\n      return\n    }",
        "    if (false) {\n      reject(abortError())\n      return\n    }",
    ),
    (
        "the abort listener is never removed",
        UPLOAD,
        "    function cleanUp(): void {\n      signal?.removeEventListener('abort', onAbort)\n    }",
        "    function cleanUp(): void {}",
    ),
    # --- the page's own gates ---
    (
        "upload is pressable with no file chosen",
        PAGE,
        "          disabled={ready === null}",
        "          disabled={false}",
    ),
    (
        # Missed on the first pass, when this removed `|| busy` from the
        # disabled prop. Button already disables itself while `loading`,
        # so that half was redundant and hid the loss of the half that
        # matters. The redundancy is gone and the fault now targets
        # `loading` itself.
        "upload is pressable while an upload is in flight",
        PAGE,
        "          loading={busy}",
        "          loading={false}",
    ),
    (
        "the dropzone stays open during an upload",
        PAGE,
        "        <FileDropzone disabled={busy} onError={reject} onFileSelected={choose} />",
        "        <FileDropzone onError={reject} onFileSelected={choose} />",
    ),
    (
        "a rejected file leaves the previous result on screen",
        PAGE,
        "    setUpload({ phase: 'idle' })\n  }, [])\n\n  const busy",
        "    setUpload((current) => current)\n  }, [])\n\n  const busy",
    ),
    (
        "the documents route goes back to the placeholder",
        ROUTES,
        "                  {PAGES[route.path] ?? <NotAvailableYet route={route} />}",
        "                  <NotAvailableYet route={route} />",
    ),
]
