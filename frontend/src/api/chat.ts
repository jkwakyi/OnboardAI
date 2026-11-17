/**
 * The Chat API, as the Chat Page calls it (ON-48).
 *
 * The contracts give this page two endpoints: `POST /api/chat/ask` and
 * `POST /api/chat/feedback`. Only `ask` is here, because only `ask`
 * exists on the server — feedback is the Feedback epic. A client function
 * for an endpoint that answers 404 is worse than no function: it looks
 * callable.
 *
 * The shapes below are the backend's `AskResponse` and nothing more.
 */
import type { ApiClient } from './client'

/** A section an answer drew on, as the backend reports it. */
export interface Citation {
  section_id: number
  heading: string | null
  document: string | null
}

/**
 * An answer, or the HR fallback.
 *
 * `fallback` is the contracts' own field, and the page must read it
 * rather than guessing from an empty `citations`: a fallback and a
 * failure look identical that way, and only one of them is normal.
 *
 * `id` is the saved chat log. "Send to HR" and the thumbs rating both
 * reference it, so it is carried even though nothing in ON-48 uses it
 * yet — dropping it here would mean the escalation ticket has to change
 * this file before it can start.
 */
export interface ChatAnswer {
  id: number
  answer: string
  citations: Citation[]
  fallback: boolean
}

/**
 * How long a question may be.
 *
 * **This number is the backend's**, from `MAX_QUESTION_CHARACTERS` in the
 * LLM Gateway, and the two have no shared source to read it from. It is
 * duplicated here so a person is stopped while typing rather than after
 * waiting for a 422, and the server stays the authority: a question that
 * gets past this is still refused there, and the page shows that refusal.
 *
 * If the Gateway's limit moves, this moves with it.
 */
export const MAX_QUESTION_CHARACTERS = 2000

/**
 * Ask a question (steps 1 to 9).
 *
 * Resolves for an answer *and* for the HR fallback, because the fallback
 * is a 200: a timeout, a provider error, invalid output from the model or
 * no good match are all normal outcomes with `fallback: true`, not
 * failures. This rejects only for the things that really are failures —
 * a question the server will not accept, a token it will not take, or
 * the network.
 */
export function askQuestion(
  client: ApiClient,
  question: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChatAnswer> {
  return client.request<ChatAnswer>('/chat/ask', {
    method: 'POST',
    body: { question },
    signal: options.signal,
  })
}
