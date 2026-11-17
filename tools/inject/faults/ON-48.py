"""Faults for the Chat Page (ON-48).

This page has one failure mode that matters more than all the others
combined, and it is not a crash.

A `200` carrying `fallback: true` is the assistant working *correctly*:
it found nothing good enough in the approved documents and said so
rather than inventing a policy. Draw that in red, with an alert and a
"Try again" button, and an employee learns that the thing is broken. The
next step they take is to complain rather than to ask HR, and the one
behaviour this whole design exists to produce is the one they are being
taught to distrust. Several faults here change nothing but that.

Four are changes somebody would make on purpose:

* "a fallback is shown as a failure" is what you write if you think an
  answer that answers nothing is an error. It is the fault above.
* "whether it fell back is read off the citations" removes a field that
  looks redundant - an answer with no sources must be a fallback,
  surely. An answer can legitimately arrive with none, and is then
  labelled "No answer found" over text the model did produce.
* "every failure offers a retry" is friendlier by one line, and invites
  somebody to re-send a question the server has already refused for a
  reason that will not change.
* "the transcript keeps only the latest turn" looks like keeping the
  page tidy. It throws away everything the person has asked, which on a
  page with no history to reload from is the only copy there is.
"""

TESTS = [
    "src/shell/ChatPage.test.tsx",
    "src/api/chat.test.ts",
    "src/shell/AppRoutes.test.tsx",
]
RUNNER = "vitest"
ROOT = "frontend"

PAGE = "src/shell/ChatPage.tsx"
CHAT = "src/api/chat.ts"
ROUTES = "src/shell/AppRoutes.tsx"

FAULTS = [
    # --- the fallback is not a failure ---------------------------------
    (
        # The one this file exists for.
        "a fallback is shown as a failure",
        PAGE,
        '  if (answer.fallback) {\n    return (\n      <div className="chat__answer">',
        '  if (answer.fallback) {\n    return (\n      <div className="chat__answer" role="alert">',
    ),
    (
        "a fallback offers a retry, as though asking again would help",
        PAGE,
        "      {turn.state === 'answered' && <AnswerView answer={turn.answer} />}",
        "      {turn.state === 'answered' && (\n        <>\n          <AnswerView answer={turn.answer} />\n          {turn.answer.fallback && (\n            <Button onClick={onRetry} size=\"sm\" variant=\"secondary\">\n              Try again\n            </Button>\n          )}\n        </>\n      )}",
    ),
    (
        "whether it fell back is read off the citations",
        PAGE,
        "  if (answer.fallback) {",
        "  if (answer.citations.length === 0) {",
    ),
    (
        "a fallback is not marked as one at all",
        PAGE,
        "  if (answer.fallback) {",
        "  if (false) {",
    ),
    (
        "the fallback is given our own wording instead of the backend's",
        PAGE,
        '        <p className="chat__text">{answer.answer}</p>\n      </div>\n    )\n  }',
        '        <p className="chat__text">No answer.</p>\n      </div>\n    )\n  }',
    ),
    (
        "the pill tints a fallback as a problem",
        PAGE,
        '          <StatusPill variant="neutral">',
        '          <StatusPill variant="danger">',
    ),
    # --- the answer and its sources -------------------------------------
    (
        "the answer text is never shown",
        PAGE,
        '      <p className="chat__text">{answer.answer}</p>\n      {answer.citations.length > 0 && (',
        '      <p className="chat__text" />\n      {answer.citations.length > 0 && (',
    ),
    (
        "the sources are not shown",
        PAGE,
        "      {answer.citations.length > 0 && (",
        "      {false && (",
    ),
    (
        "only the first source is shown",
        PAGE,
        "            {answer.citations.map((citation) => {",
        "            {answer.citations.slice(0, 1).map((citation) => {",
    ),
    (
        "the sources list has no name, so it cannot be found by one",
        PAGE,
        '          <p className="chat__citations-label" id={`sources-${answer.id}`}>',
        '          <p className="chat__citations-label">',
    ),
    (
        "a section with no heading is labelled with nothing",
        PAGE,
        "    location: citation.heading ?? `Section ${citation.section_id}`,",
        "    location: citation.heading ?? '',",
    ),
    (
        "a citation with no document named is left blank",
        PAGE,
        "    title: citation.document ?? 'Approved HR document',",
        "    title: citation.document ?? '',",
    ),
    (
        "the heading and the document are swapped",
        PAGE,
        "    title: citation.document ?? 'Approved HR document',",
        "    title: citation.heading ?? 'Approved HR document',",
    ),
    # --- the transcript ---------------------------------------------------
    (
        "the transcript keeps only the latest turn",
        PAGE,
        "    setTurns((current) => [...current, { state: 'waiting', id, question }])",
        "    setTurns(() => [{ state: 'waiting', id, question }])",
    ),
    (
        "the question is not shown while the answer is awaited",
        PAGE,
        '      <p className="chat__question">{turn.question}</p>',
        '      <p className="chat__question" />',
    ),
    (
        "nothing says a question is being looked up",
        PAGE,
        "      {turn.state === 'waiting' && (",
        "      {false && (",
    ),
    (
        "the newest turn is not brought into view",
        PAGE,
        "    latest.current?.scrollIntoView({ block: 'nearest' })",
        "    void latest",
    ),
    # --- the box and the send button ----------------------------------------
    (
        "the box is not cleared, so the same question is sent twice",
        PAGE,
        "    setTurns((current) => [...current, { state: 'waiting', id, question }])\n    setDraft('')",
        "    setTurns((current) => [...current, { state: 'waiting', id, question }])",
    ),
    (
        "a second question can be sent while one is in flight",
        PAGE,
        "  const ready = question !== '' && !tooLong && !waiting",
        "  const ready = question !== '' && !tooLong",
    ),
    (
        "a question of only spaces can be sent",
        PAGE,
        "  const question = draft.trim()",
        "  const question = draft",
    ),
    (
        "an empty question can be sent",
        PAGE,
        "  const ready = question !== '' && !tooLong && !waiting",
        "  const ready = !tooLong && !waiting",
    ),
    (
        "a question longer than the backend will read is sent anyway",
        PAGE,
        "  const tooLong = draft.length > MAX_QUESTION_CHARACTERS",
        "  const tooLong = false",
    ),
    (
        "the length limit is a number of this page's own, free to drift",
        CHAT,
        "export const MAX_QUESTION_CHARACTERS = 2000",
        "export const MAX_QUESTION_CHARACTERS = 500",
    ),
    (
        "nothing says why a long question will not send",
        PAGE,
        "          error={tooLong ? `Questions are limited to ${MAX_QUESTION_CHARACTERS} characters.` : undefined}",
        "          error={undefined}",
    ),
    (
        "Enter does not send",
        PAGE,
        "            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {",
        "            if (false) {",
    ),
    (
        "Shift+Enter sends instead of starting a new line",
        PAGE,
        "            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {",
        "            if (event.key === 'Enter' && !event.nativeEvent.isComposing) {",
    ),
    # --- failures, which really are failures ---------------------------------
    (
        "a failure is reported with our own wording, not the backend's",
        PAGE,
        "                  message: failure.message,",
        "                  message: 'It did not work.',",
    ),
    (
        "a failure is not announced",
        PAGE,
        '          <p className="chat__detail" role="alert">',
        '          <p className="chat__detail">',
    ),
    (
        "every failure offers a retry, including a question already refused",
        PAGE,
        "    return ![401, 422].includes(failure.status)",
        "    return true",
    ),
    (
        "no failure offers a retry, not even a server that merely broke",
        PAGE,
        "  if (failure instanceof NetworkError) return true",
        "  if (failure instanceof NetworkError) return false",
    ),
    (
        "a retry sends an empty question rather than the one that failed",
        PAGE,
        "      void send(turn.question, turn.id)",
        "      void send('', turn.id)",
    ),
    (
        "a retry replaces every turn rather than the one being retried",
        PAGE,
        "          existing.id === turn.id\n            ? { state: 'waiting', id: turn.id, question: turn.question }\n            : existing,",
        "          true ? { state: 'waiting', id: turn.id, question: turn.question } : existing,",
    ),
    (
        "a failed turn stays failed after a successful retry",
        PAGE,
        "            turn.id === id ? { state: 'answered', id, question: asked, answer } : turn,",
        "            turn.id === 'never' ? { state: 'answered', id, question: asked, answer } : turn,",
    ),
    # --- the request itself ----------------------------------------------------
    (
        "the question is sent somewhere other than the ask endpoint",
        CHAT,
        "  return client.request<ChatAnswer>('/chat/ask', {",
        "  return client.request<ChatAnswer>('/chat/question', {",
    ),
    (
        "the question is sent as a GET, which carries no body",
        CHAT,
        "    method: 'POST',",
        "    method: 'GET',",
    ),
    (
        "the question is not in the request at all",
        CHAT,
        "    body: { question },",
        "    body: {},",
    ),
    (
        "the abort signal is dropped",
        CHAT,
        "    signal: options.signal,",
        "    signal: undefined,",
    ),
    # --- the route -----------------------------------------------------------------
    (
        "the chat route goes back to the placeholder",
        ROUTES,
        "  '/chat': <ChatPage />,\n",
        "",
    ),
]
