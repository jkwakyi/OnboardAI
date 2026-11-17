/**
 * The Escalations API, as the Chat Page calls it (ON-20).
 *
 * The contracts give this page one of the three escalation endpoints:
 * `POST /api/escalations`, the "Send to HR" button on a fallback answer
 * (E1, E2). `GET` is the HR Inbox and the employee's view of replies
 * (ON-21, ON-22) and `PATCH` is HR replying (ON-21); neither exists on
 * the server yet, and a client function for an endpoint that answers 404
 * is worse than no function because it looks callable.
 *
 * **The question is not sent.** Only which answer is being escalated.
 * The server reads what was asked out of that chat log, which is the
 * only way the question in HR's inbox is the question the employee
 * actually asked.
 */
import type { ApiClient } from './client'

/** An escalation, exactly as the backend reports a newly opened one. */
export interface Escalation {
  id: number
  chat_log_id: number | null
  question: string
  /** Always `open` from this endpoint; E2 says so. */
  status: string
  /** ISO 8601, from the server's clock. */
  created_at: string
}

/**
 * Send a fallback answer's question to HR (E1, E2).
 *
 * `chatLogId` is the `id` from `POST /api/chat/ask`. Sending the same
 * one twice is safe: the backend returns the escalation that already
 * exists rather than putting the question in HR's inbox again.
 */
export function sendToHr(
  client: ApiClient,
  chatLogId: number,
  options: { signal?: AbortSignal } = {},
): Promise<Escalation> {
  return client.request<Escalation>('/escalations', {
    method: 'POST',
    body: { chat_log_id: chatLogId },
    signal: options.signal,
  })
}
