/**
 * The Chat Page (ON-48).
 *
 * An employee types a question, and gets back either an answer with the
 * sections it came from, or a message directing them to HR. Both roles
 * reach it — the contracts put the HR administrator on this page too,
 * and the rail gives them Chat as well.
 *
 * **A fallback is not a failure, and must not look like one.** The
 * contracts are explicit that a timeout, a provider error, invalid
 * output from the model and no good match are all `200` with
 * `fallback: true`. Styling that like an error teaches people that the
 * assistant is broken when it is in fact doing the one thing it exists
 * to do: declining to invent a policy. So a fallback is drawn as a
 * normal turn in the conversation with a quiet "No answer found" pill,
 * and the page keeps a red alert for the things that really did fail —
 * the network, a refusal, a server that broke.
 *
 * **The transcript lives in this page and nowhere else.** The backend
 * saves every chat (ON-47), but the contracts define exactly nine
 * endpoints and none of them reads chat history back, so there is
 * nothing to restore from and nothing here pretends otherwise: a reload
 * starts an empty page. Inventing a tenth endpoint to fix that is not
 * this ticket's to do.
 *
 * **The wait can be twenty seconds.** That is the LLM Gateway's timeout
 * and the worst case is a model that never answers, so the pending turn
 * is a visible part of the transcript saying the question is being
 * looked up, rather than a spinner on a button that leaves the page
 * looking frozen.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  ApiError,
  MAX_QUESTION_CHARACTERS,
  NetworkError,
  askQuestion,
  sendToHr,
  type ChatAnswer,
  type Citation,
} from '../api'
import { Button, Card, CitationChip, EmptyState, FormField, StatusPill } from '../components'
import { Inbox, MessageSquare, SearchX } from '../components/icons'
import { useSession } from '../session/SessionContext'
import './ChatPage.css'

/** One exchange, from the moment it is sent. */
export type Turn =
  | { state: 'waiting'; id: string; question: string }
  | { state: 'answered'; id: string; question: string; answer: ChatAnswer }
  | { state: 'failed'; id: string; question: string; message: string; canRetry: boolean }

/**
 * Whether a fallback has been sent to HR, kept per chat log (ON-20).
 *
 * Keyed by the chat log's id rather than carried on the turn, because
 * that id is what the escalation points at: the backend returns the
 * existing escalation if the same one is sent twice, so the key here and
 * the key there are the same thing.
 */
export type Escalated =
  | { state: 'sending' }
  | { state: 'sent' }
  | { state: 'failed'; message: string }

export const EMPTY_TITLE = 'Ask about anything in the HR documents'
export const EMPTY_DESCRIPTION =
  'Answers come only from documents HR has approved and uploaded, and every answer shows which ones it used.'

/** Shown on a turn the AI path declined to answer. */
export const FALLBACK_LABEL = 'No answer found'

/** The button, and what replaces it once the question is with HR. */
export const SEND_TO_HR_LABEL = 'Send to HR'
export const SENT_TO_HR_LABEL = 'Sent to HR'
export const SENT_TO_HR_DETAIL =
  'HR has your question and will reply to you here.'

/**
 * What a question is labelled as while it is in flight.
 *
 * It says the sources are being searched rather than "thinking", because
 * that is what is actually happening for most of the wait and because an
 * assistant that says it is thinking is an assistant pretending to be a
 * person.
 */
export const WAITING_LABEL = 'Searching the HR documents…'

/**
 * Whether asking the same question again could work.
 *
 * A question the server refused will be refused identically however many
 * times it is sent, and offering a retry for one wastes the person's
 * time twice. A request that failed — the network, a server that broke —
 * is worth another go.
 */
export function canRetry(failure: unknown): boolean {
  if (failure instanceof NetworkError) return true
  if (failure instanceof ApiError) {
    // 422 is a question this server will not take: blank, or too long.
    // 401 has already signed the person out from the API client.
    return ![401, 422].includes(failure.status)
  }
  return false
}

/** A citation's two lines: which document, and where in it. */
export function citationLabels(citation: Citation): { title: string; location: string } {
  return {
    title: citation.document ?? 'Approved HR document',
    // The backend sends null when the section had no heading of its own.
    // Its id is the only other thing that identifies it, and a number on
    // its own is not a location, so it is labelled as one.
    location: citation.heading ?? `Section ${citation.section_id}`,
  }
}

export default function ChatPage() {
  const { api } = useSession()
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [escalated, setEscalated] = useState<Record<number, Escalated>>({})
  const nextId = useRef(0)
  const latest = useRef<HTMLDivElement | null>(null)

  const waiting = turns.some((turn) => turn.state === 'waiting')
  const question = draft.trim()
  const tooLong = draft.length > MAX_QUESTION_CHARACTERS
  const ready = question !== '' && !tooLong && !waiting

  // The newest turn, once it lands. Without this a long answer pushes the
  // question off the top and the page looks as though nothing happened.
  useEffect(() => {
    latest.current?.scrollIntoView({ block: 'nearest' })
  }, [turns])

  const send = useCallback(
    async (asked: string, id: string): Promise<void> => {
      try {
        const answer = await askQuestion(api, asked)
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id ? { state: 'answered', id, question: asked, answer } : turn,
          ),
        )
      } catch (failure) {
        if (!(failure instanceof ApiError || failure instanceof NetworkError)) throw failure
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id
              ? {
                  state: 'failed',
                  id,
                  question: asked,
                  message: failure.message,
                  canRetry: canRetry(failure),
                }
              : turn,
          ),
        )
      }
    },
    [api],
  )

  const ask = useCallback(() => {
    if (!ready) return
    const id = `turn-${nextId.current++}`
    setTurns((current) => [...current, { state: 'waiting', id, question }])
    setDraft('')
    void send(question, id)
  }, [question, ready, send])

  const escalate = useCallback(
    async (chatLogId: number): Promise<void> => {
      setEscalated((current) => ({ ...current, [chatLogId]: { state: 'sending' } }))
      try {
        await sendToHr(api, chatLogId)
        setEscalated((current) => ({ ...current, [chatLogId]: { state: 'sent' } }))
      } catch (failure) {
        if (!(failure instanceof ApiError || failure instanceof NetworkError)) throw failure
        setEscalated((current) => ({
          ...current,
          [chatLogId]: { state: 'failed', message: failure.message },
        }))
      }
    },
    [api],
  )

  const retry = useCallback(
    (turn: Turn) => {
      setTurns((current) =>
        current.map((existing) =>
          existing.id === turn.id
            ? { state: 'waiting', id: turn.id, question: turn.question }
            : existing,
        ),
      )
      void send(turn.question, turn.id)
    },
    [send],
  )

  return (
    <div className="chat">
      <div className="chat__transcript">
        {turns.length === 0 ? (
          <EmptyState
            description={EMPTY_DESCRIPTION}
            icon={<MessageSquare />}
            title={EMPTY_TITLE}
          />
        ) : (
          /* A feed rather than a log: entries are added at the end and
             the person is reading as they arrive, which is what
             `aria-live="polite"` on a feed is for. */
          <ol aria-live="polite" className="chat__turns">
            {turns.map((turn, index) => (
              <li className="chat__turn" key={turn.id}>
                <div ref={index === turns.length - 1 ? latest : null}>
                  <TurnView
                    escalated={escalated}
                    onEscalate={escalate}
                    onRetry={() => retry(turn)}
                    turn={turn}
                  />
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <Card className="chat__composer" label="Ask a question">
        <FormField
          as="textarea"
          error={tooLong ? `Questions are limited to ${MAX_QUESTION_CHARACTERS} characters.` : undefined}
          helper="Press Enter to send, Shift+Enter for a new line."
          label="Your question"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter is a newline. Not while the
            // browser's own composition is open, or typing a question in
            // an input method sends it halfway through a word.
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              ask()
            }
          }}
          placeholder="How much paid time off do I get?"
          rows={3}
          value={draft}
        />
        <div className="chat__actions">
          <Button disabled={!ready} loading={waiting} onClick={ask}>
            Send
          </Button>
        </div>
      </Card>
    </div>
  )
}

function TurnView({
  escalated,
  onEscalate,
  onRetry,
  turn,
}: {
  escalated: Record<number, Escalated>
  onEscalate: (chatLogId: number) => void
  onRetry: () => void
  turn: Turn
}) {
  return (
    <Card accent="chat" className="chat__card" label="You asked">
      <p className="chat__question">{turn.question}</p>

      {turn.state === 'waiting' && (
        <p className="chat__waiting">
          {/* aria-live, because the answer arrives without the person
              doing anything and a silent change is one they have to go
              and look for. */}
          <span aria-live="polite">{WAITING_LABEL}</span>
        </p>
      )}

      {turn.state === 'answered' && (
        <AnswerView
          answer={turn.answer}
          escalated={escalated[turn.answer.id]}
          onEscalate={() => onEscalate(turn.answer.id)}
        />
      )}

      {turn.state === 'failed' && (
        <div className="chat__failed">
          {/* role="alert" so it is announced when it appears. The wording
              is the backend's where it sent any: it knows why it refused,
              and this page does not. */}
          <p className="chat__detail" role="alert">
            {turn.message}
          </p>
          {turn.canRetry && (
            <Button onClick={onRetry} size="sm" variant="secondary">
              Try again
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

function AnswerView({
  answer,
  escalated,
  onEscalate,
}: {
  answer: ChatAnswer
  escalated?: Escalated
  onEscalate: () => void
}) {
  if (answer.fallback) {
    return (
      <div className="chat__answer">
        <p className="chat__outcome">
          {/* Neutral, not danger. This is the assistant working correctly:
              it found nothing good enough and said so instead of making
              something up. */}
          <StatusPill variant="neutral">
            <SearchX aria-hidden="true" className="chat__pill-icon" />
            {FALLBACK_LABEL}
          </StatusPill>
        </p>
        <p className="chat__text">{answer.answer}</p>
        <SendToHr escalated={escalated} onEscalate={onEscalate} />
      </div>
    )
  }

  return (
    <div className="chat__answer">
      <p className="chat__text">{answer.answer}</p>
      {answer.citations.length > 0 && (
        <div className="chat__citations">
          <p className="chat__citations-label" id={`sources-${answer.id}`}>
            Drawn from
          </p>
          <ul aria-labelledby={`sources-${answer.id}`} className="chat__citation-list">
            {answer.citations.map((citation) => {
              const { location, title } = citationLabels(citation)
              return (
                <li key={citation.section_id}>
                  {/* Not pressable yet: opening the section needs an
                      endpoint that reads one, which the contracts do not
                      define. CitationChip is a button by design (ON-64),
                      so it is disabled rather than left as a control that
                      takes a keyboard user's time and does nothing. */}
                  <CitationChip disabled location={location} title={title} />
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}

/**
 * The "Send to HR" button, and what it becomes (ON-20, E1).
 *
 * Only ever drawn on a fallback: the contracts say the button appears
 * when an employee gets one, and sending an answered question would put
 * a solved question in front of HR. The backend enforces that too — a
 * button that is absent is not a rule — but this is where it is visible.
 *
 * Once sent, the button is replaced rather than disabled. A disabled
 * button says "you cannot do this"; what is true is "this is done", and
 * the two look identical while meaning opposite things.
 */
function SendToHr({ escalated, onEscalate }: { escalated?: Escalated; onEscalate: () => void }) {
  if (escalated?.state === 'sent') {
    return (
      <p className="chat__sent">
        {/* aria-live, because the change happens without the person
            doing anything further and a silent one is a person pressing
            the button again. */}
        <span aria-live="polite" className="chat__sent-inner">
          <Inbox aria-hidden="true" className="chat__pill-icon" />
          <strong>{SENT_TO_HR_LABEL}.</strong> {SENT_TO_HR_DETAIL}
        </span>
      </p>
    )
  }

  return (
    <div className="chat__escalate">
      <Button
        loading={escalated?.state === 'sending'}
        onClick={onEscalate}
        size="sm"
        variant="secondary"
      >
        {SEND_TO_HR_LABEL}
      </Button>
      {escalated?.state === 'failed' && (
        <p className="chat__detail" role="alert">
          {escalated.message}
        </p>
      )}
    </div>
  )
}
