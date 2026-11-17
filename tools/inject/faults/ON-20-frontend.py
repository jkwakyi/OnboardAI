"""Faults for the Send to HR button (ON-20), the frontend half.

The other half is `ON-20-backend.py`. Two files because the injector
takes one `ROOT` and one `RUNNER` each, and pretending a pytest run and
a vitest run are one pass would be worse than saying so.

This button is the end of the fallback. An employee has just been told
the assistant could not help and that HR can; everything here is about
that handover not quietly failing. The worst faults below are the ones
where it looks like it worked.

Four are changes somebody would make on purpose:

* "every answer offers Send to HR" removes a condition that looks like
  needless narrowing. It offers to send HR a question that already has
  an answer, and the backend refuses it with a 409 - so the button's
  only effect is a dead end.
* "the button is disabled once sent rather than replaced" is the obvious
  way to stop a second press. A disabled button says "you cannot do
  this"; what is true is "this is done", and the two look the same.
* "the newest fallback's id is sent" is what you get from reaching for
  the answer in scope instead of the one the button belongs to. It sends
  HR the wrong question, from the right person, with a 201 either way.
* "a failure to send is swallowed" looks like not bothering the employee
  with an error. They are left believing HR has their question.
"""

TESTS = [
    "src/shell/ChatPage.test.tsx",
    "src/api/escalations.test.ts",
    "src/api/chat.test.ts",
]
RUNNER = "vitest"
ROOT = "frontend"

PAGE = "src/shell/ChatPage.tsx"
CLIENT = "src/api/escalations.ts"

FAULTS = [
    # --- when the button appears ---------------------------------------
    (
        "every answer offers Send to HR, not only a fallback",
        PAGE,
        "        <p className=\"chat__text\">{answer.answer}</p>\n        <SendToHr escalated={escalated} onEscalate={onEscalate} />",
        "        <p className=\"chat__text\">{answer.answer}</p>",
    ),
    (
        "no answer offers Send to HR at all",
        PAGE,
        "  if (escalated?.state === 'sent') {",
        "  if (true) {",
    ),
    # --- which question gets sent ----------------------------------------
    (
        # The quiet one: the right person, a 201, and the wrong question
        # in front of HR.
        "the id of a different answer is sent",
        PAGE,
        "          onEscalate={() => onEscalate(turn.answer.id)}",
        "          onEscalate={() => onEscalate(0)}",
    ),
    (
        "the escalation is tracked against the turn rather than the answer",
        PAGE,
        "          escalated={escalated[turn.answer.id]}",
        "          escalated={escalated[0]}",
    ),
    (
        "the question is sent along with the id",
        CLIENT,
        "    body: { chat_log_id: chatLogId },",
        "    body: { chat_log_id: chatLogId, question: 'see the chat log' },",
    ),
    (
        "the id is sent under a name the backend does not read",
        CLIENT,
        "    body: { chat_log_id: chatLogId },",
        "    body: { chatLogId },",
    ),
    (
        "it is sent somewhere other than the escalations endpoint",
        CLIENT,
        "  return client.request<Escalation>('/escalations', {",
        "  return client.request<Escalation>('/escalate', {",
    ),
    (
        "it is sent as a GET, which carries no body",
        CLIENT,
        "    method: 'POST',",
        "    method: 'GET',",
    ),
    (
        "the abort signal is dropped",
        CLIENT,
        "    signal: options.signal,",
        "    signal: undefined,",
    ),
    # --- what the employee is told ----------------------------------------
    (
        "nothing says the question reached HR",
        PAGE,
        "  if (escalated?.state === 'sent') {",
        "  if (false) {",
    ),
    (
        "the button is disabled once sent rather than replaced",
        PAGE,
        "  if (escalated?.state === 'sent') {\n    return (\n      <p className=\"chat__sent\">",
        "  if (false) {\n    return (\n      <p className=\"chat__sent\">",
    ),
    (
        "the confirmation does not say HR will reply here",
        PAGE,
        "          <strong>{SENT_TO_HR_LABEL}.</strong> {SENT_TO_HR_DETAIL}",
        "          <strong>{SENT_TO_HR_LABEL}.</strong>",
    ),
    (
        "the confirmation is not announced",
        PAGE,
        '        <span aria-live="polite" className="chat__sent-inner">',
        '        <span className="chat__sent-inner">',
    ),
    # --- sending ------------------------------------------------------------
    (
        "the button can be pressed again while it is sending",
        PAGE,
        "        loading={escalated?.state === 'sending'}",
        "        loading={false}",
    ),
    (
        "nothing is recorded while it is sending",
        PAGE,
        "      setEscalated((current) => ({ ...current, [chatLogId]: { state: 'sending' } }))",
        "      void chatLogId",
    ),
    (
        "sending one fallback marks every fallback as sent",
        PAGE,
        "        setEscalated((current) => ({ ...current, [chatLogId]: { state: 'sent' } }))",
        "        setEscalated(() => ({ 13: { state: 'sent' }, 99: { state: 'sent' } }))",
    ),
    # --- failures -------------------------------------------------------------
    (
        "a failure to send is swallowed",
        PAGE,
        "        setEscalated((current) => ({\n          ...current,\n          [chatLogId]: { state: 'failed', message: failure.message },\n        }))",
        "        setEscalated((current) => ({ ...current, [chatLogId]: { state: 'sent' } }))",
    ),
    (
        "a failure is reported with our own wording, not the backend's",
        PAGE,
        "          [chatLogId]: { state: 'failed', message: failure.message },",
        "          [chatLogId]: { state: 'failed', message: 'It did not work.' },",
    ),
    (
        "a failure is not announced",
        PAGE,
        '        <p className="chat__detail" role="alert">\n          {escalated.message}\n        </p>',
        '        <p className="chat__detail">\n          {escalated.message}\n        </p>',
    ),
    (
        "the button disappears after a failure, leaving no way to try again",
        PAGE,
        "      {escalated?.state === 'failed' && (",
        "      {escalated === undefined && (",
    ),
]
