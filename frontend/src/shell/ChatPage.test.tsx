/**
 * The Chat Page (ON-48).
 *
 * These drive the real path. `renderApp` builds a real `SessionProvider`,
 * which builds a real API client, which calls `fetch` — stubbed here, and
 * nothing between the Send button and that call is mocked out. A change
 * that stopped the client attaching the token, or stopped the page
 * sending the question, fails here rather than passing against a stubbed
 * `askQuestion`.
 *
 * The test this file exists for is the one about a fallback. The
 * contracts make it a `200`, and an employee who is shown it in red
 * learns that the assistant is broken — when it is in fact doing the one
 * thing it exists to do, which is refusing to invent a policy. So there
 * are tests that it appears, and tests that it does not appear as an
 * error.
 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MAX_QUESTION_CHARACTERS } from '../api'
import { EMPLOYEE_TOKEN, HR_TOKEN, renderApp } from '../test/renderApp'
import {
  EMPTY_TITLE,
  FALLBACK_LABEL,
  SENT_TO_HR_LABEL,
  SEND_TO_HR_LABEL,
  WAITING_LABEL,
  canRetry,
  citationLabels,
} from './ChatPage'
import { ApiError, NetworkError } from '../api'

/** What the backend actually answers with, from ON-47's `AskResponse`. */
const ANSWERED = {
  id: 12,
  answer: 'You accrue eighteen days of paid time off in your fourth year.',
  citations: [
    { section_id: 475, heading: '4.1 PAID TIME OFF', document: '04-time-off-and-leave.txt' },
  ],
  fallback: false,
}

const FELL_BACK = {
  id: 13,
  answer:
    'I could not find an answer to that in the approved HR documents. ' +
    'Please send the question to HR and someone will reply to you here.',
  citations: [],
  fallback: true,
}

let fetchMock: ReturnType<typeof vi.fn>
const realFetch = globalThis.fetch

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response
}

/** Hold the next request open, and hand back the resolver. */
function pending(): { resolve: (body: unknown) => void } {
  let release!: (value: Response) => void
  fetchMock.mockImplementationOnce(
    () =>
      new Promise<Response>((resolveWith) => {
        release = resolveWith
      }),
  )
  return { resolve: (body) => release(jsonResponse(body)) }
}

beforeEach(() => {
  fetchMock = vi.fn(async () => jsonResponse(ANSWERED))
  globalThis.fetch = fetchMock as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = realFetch
  vi.restoreAllMocks()
})

function open(token = EMPLOYEE_TOKEN) {
  return renderApp({ path: '/chat', token })
}

async function ask(question = 'How much paid time off do I accrue?') {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Your question'), question)
  await user.click(screen.getByRole('button', { name: 'Send' }))
  return user
}

// --- the empty page -----------------------------------------------------

it('opens with nothing asked and says what the answers are drawn from', () => {
  open()

  expect(screen.getByText(EMPTY_TITLE)).toBeInTheDocument()
  expect(screen.getByText(/documents HR has approved/i)).toBeInTheDocument()
})

it('cannot send an empty question', () => {
  open()

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
})

it('cannot send a question of only spaces', async () => {
  open()
  await userEvent.setup().type(screen.getByLabelText('Your question'), '    ')

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
})

// --- asking ---------------------------------------------------------------

it('sends the question to the ask endpoint with the login token', async () => {
  open()
  await ask('How much paid time off do I accrue?')

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toMatch(/\/chat\/ask$/)
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({
    question: 'How much paid time off do I accrue?',
  })
  expect((init.headers as Record<string, string>).Authorization).toMatch(/^Bearer /)
})

it('shows the question in the transcript while it waits', async () => {
  const request = pending()
  open()
  await ask('How much paid time off do I accrue?')

  expect(screen.getByText('How much paid time off do I accrue?')).toBeInTheDocument()
  expect(screen.getByText(WAITING_LABEL)).toBeInTheDocument()

  request.resolve(ANSWERED)
  await screen.findByText(ANSWERED.answer)
})

it('clears the box once the question is sent, so it is not asked twice', async () => {
  pending()
  open()
  await ask('How much paid time off do I accrue?')

  expect(screen.getByLabelText('Your question')).toHaveValue('')
})

it('cannot send a second question while one is in flight', async () => {
  pending()
  open()
  await ask()

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
})

it('Enter does not send a second question while one is in flight', async () => {
  /**
   * The button is disabled by `loading` whether or not anything else
   * stops it, so the test above passes with the real guard deleted -
   * the same redundancy that hid a missing guard in ON-42. Enter does
   * not go through the button at all, so this is the one that proves
   * the guard exists. Found by fault injection.
   */
  pending()
  open()
  const user = await ask('First question')

  await user.type(screen.getByLabelText('Your question'), 'Second question{Enter}')

  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('shows the answer', async () => {
  open()
  await ask()

  expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument()
})

it('keeps earlier turns when another question is asked', async () => {
  open()
  const user = await ask('First question')
  await screen.findByText(ANSWERED.answer)

  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ ...ANSWERED, id: 14, answer: 'A different answer.' }),
  )
  await user.type(screen.getByLabelText('Your question'), 'Second question')
  await user.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByText('A different answer.')).toBeInTheDocument()
  expect(screen.getByText('First question')).toBeInTheDocument()
  expect(screen.getByText('Second question')).toBeInTheDocument()
})

it('sends on Enter and does not send on Shift+Enter', async () => {
  open()
  const user = userEvent.setup()
  const box = screen.getByLabelText('Your question')

  await user.type(box, 'First line{Shift>}{Enter}{/Shift}second line')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(box).toHaveValue('First line\nsecond line')

  await user.type(box, '{Enter}')
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
})

it('brings the newest turn into view', async () => {
  /**
   * A long answer pushes the question that prompted it off the top, and
   * the page then looks as though nothing happened. jsdom has no
   * `scrollIntoView` at all, so `src/test/setup.ts` supplies one that
   * records the call - without it the component throws on render rather
   * than failing an assertion, which is how this behaviour would have
   * gone untested.
   */
  open()
  await ask()
  await screen.findByText(ANSWERED.answer)

  const scrolled = document.querySelectorAll('[data-testid], div')
  expect(
    Array.from(scrolled).some(
      (element) => (element as Element & { scrolledIntoView?: boolean }).scrolledIntoView === true,
    ),
  ).toBe(true)
})

// --- the citations ---------------------------------------------------------

it('shows which documents the answer was drawn from', async () => {
  open()
  await ask()

  const sources = await screen.findByRole('list', { name: /drawn from/i })
  expect(
    within(sources).getByRole('button', {
      name: 'Source: 04-time-off-and-leave.txt, 4.1 PAID TIME OFF',
    }),
  ).toBeInTheDocument()
})

it('labels a section with no heading by its id rather than leaving it blank', () => {
  expect(citationLabels({ section_id: 7, heading: null, document: 'handbook.pdf' })).toEqual({
    title: 'handbook.pdf',
    location: 'Section 7',
  })
})

it('names the document even when the backend sent none', () => {
  expect(citationLabels({ section_id: 7, heading: '4.1 PTO', document: null })).toEqual({
    title: 'Approved HR document',
    location: '4.1 PTO',
  })
})

it('shows every citation the answer carried', async () => {
  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({
      ...ANSWERED,
      citations: [
        { section_id: 1, heading: 'One', document: 'a.txt' },
        { section_id: 2, heading: 'Two', document: 'b.txt' },
        { section_id: 3, heading: 'Three', document: 'c.txt' },
      ],
    }),
  )
  open()
  await ask()

  const sources = await screen.findByRole('list', { name: /drawn from/i })
  expect(within(sources).getAllByRole('button')).toHaveLength(3)
})

// --- the fallback, which is not a failure -----------------------------------

it('shows the HR fallback message when fallback is true', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  await ask('What is the airspeed velocity of an unladen swallow?')

  expect(await screen.findByText(FELL_BACK.answer)).toBeInTheDocument()
  expect(screen.getByText(FALLBACK_LABEL)).toBeInTheDocument()
})

it('does not tint a fallback as a problem', async () => {
  /**
   * The colour is the signal somebody takes in before any of the words,
   * and nothing checked it: the other fallback tests look for an alert
   * role and a retry button, both of which stay absent while the pill
   * turns red. Found by fault injection.
   */
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  await ask()

  const pill = await screen.findByText(FALLBACK_LABEL)
  expect(pill).toHaveClass('oa-pill--neutral')
  expect(pill).not.toHaveClass('oa-pill--danger')
})

it('does not dress a fallback up as an error', async () => {
  /**
   * The one that matters. A `200` with `fallback: true` is the assistant
   * working correctly — it found nothing good enough and said so rather
   * than inventing a policy. Shown as an alert, it teaches an employee
   * that the thing is broken, and the next step they take is to complain
   * rather than to ask HR.
   */
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  await ask()

  await screen.findByText(FELL_BACK.answer)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
})

it('offers no sources on a fallback, because there were none', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  await ask()

  await screen.findByText(FELL_BACK.answer)
  expect(screen.queryByRole('list', { name: /drawn from/i })).not.toBeInTheDocument()
})

it('reads the fallback flag rather than guessing from empty citations', async () => {
  /**
   * An answer can legitimately arrive with no citations the page can show
   * while still being an answer. Guessing from `citations.length` would
   * label it "No answer found" and hide text the model did produce.
   */
  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ id: 15, answer: 'A real answer.', citations: [], fallback: false }),
  )
  open()
  await ask()

  expect(await screen.findByText('A real answer.')).toBeInTheDocument()
  expect(screen.queryByText(FALLBACK_LABEL)).not.toBeInTheDocument()
})

// --- Send to HR (ON-20, E1) ---------------------------------------------------

/** What POST /api/escalations answers with. */
const ESCALATION = {
  id: 4,
  chat_log_id: FELL_BACK.id,
  question: 'What is the airspeed velocity of an unladen swallow?',
  status: 'open',
  created_at: '2026-11-17T12:00:00Z',
}

async function askAndFallBack() {
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  const user = await ask()
  await screen.findByText(FELL_BACK.answer)
  return user
}

it('offers Send to HR on a fallback', async () => {
  await askAndFallBack()

  expect(screen.getByRole('button', { name: SEND_TO_HR_LABEL })).toBeInTheDocument()
})

it('does not offer Send to HR on an answer', async () => {
  /**
   * The button is for a question that was not answered. On an answered
   * one it invites somebody to send HR a question they already have the
   * answer to - and the backend refuses it with a 409, so the only thing
   * offering it achieves is a dead end.
   */
  open()
  await ask()
  await screen.findByText(ANSWERED.answer)

  expect(screen.queryByRole('button', { name: SEND_TO_HR_LABEL })).not.toBeInTheDocument()
})

it('sends the chat log id, and not the question', async () => {
  /**
   * The server reads what was asked out of the chat log. Sending a
   * question from here would be sending text a caller chose, which is
   * how HR's inbox fills with questions nobody asked.
   */
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit]
  expect(url).toMatch(/\/escalations$/)
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({ chat_log_id: FELL_BACK.id })
})

it('says the question is with HR once it is sent', async () => {
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  expect(await screen.findByText(new RegExp(SENT_TO_HR_LABEL))).toBeInTheDocument()
  // By selector, because the sentence spans a <strong> inside its
  // <span>, so both the span and its <p> match the text.
  expect(screen.getByText(/will reply to you here/i, { selector: 'span' })).toBeInTheDocument()
})

it('announces that the question reached HR', async () => {
  /**
   * The button the person just pressed disappears, which on a screen
   * reader can mean focus lands nowhere and nothing is said - so the
   * only thing confirming the press is a live region. Found by fault
   * injection: every other test here reads the text, and the text is
   * there whether or not anybody is told about it.
   */
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  const confirmation = await screen.findByText(/will reply to you here/i, { selector: 'span' })
  expect(confirmation).toHaveAttribute('aria-live', 'polite')
})

it('replaces the button rather than disabling it', async () => {
  /**
   * A disabled button says "you cannot do this". What is true is "this
   * is done", and the two look identical while meaning opposite things.
   */
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))
  await screen.findByText(new RegExp(SENT_TO_HR_LABEL))

  expect(screen.queryByRole('button', { name: SEND_TO_HR_LABEL })).not.toBeInTheDocument()
})

it('cannot be pressed twice while it is being sent', async () => {
  const user = await askAndFallBack()
  const held = pending()

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  expect(screen.getByRole('button', { name: SEND_TO_HR_LABEL })).toBeDisabled()
  held.resolve(ESCALATION)
})

it('reports a failure to send and leaves the button there to try again', async () => {
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(() => Promise.reject(new TypeError('Failed to fetch')))

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be reached/i)
  expect(screen.getByRole('button', { name: SEND_TO_HR_LABEL })).toBeEnabled()
})

it('shows the backend wording when it refuses to escalate', async () => {
  const user = await askAndFallBack()
  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ detail: 'That answer could not be found.' }, 404),
  )

  await user.click(screen.getByRole('button', { name: SEND_TO_HR_LABEL }))

  expect(await screen.findByRole('alert')).toHaveTextContent('That answer could not be found.')
})

it('sends only the fallback that was pressed', async () => {
  /**
   * Two fallbacks in the transcript, one sent. The other must still
   * offer its button - sharing one piece of state between them would
   * mark both as sent and lose the second question entirely.
   */
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  const user = await ask('First unanswerable question')
  await screen.findByText(FELL_BACK.answer)

  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ ...FELL_BACK, id: 99, answer: 'A second fallback answer.' }),
  )
  await user.type(screen.getByLabelText('Your question'), 'Second unanswerable question')
  await user.click(screen.getByRole('button', { name: 'Send' }))
  await screen.findByText('A second fallback answer.')

  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))
  const buttons = screen.getAllByRole('button', { name: SEND_TO_HR_LABEL })
  expect(buttons).toHaveLength(2)
  await user.click(buttons[0])
  await screen.findByText(new RegExp(SENT_TO_HR_LABEL))

  expect(screen.getAllByRole('button', { name: SEND_TO_HR_LABEL })).toHaveLength(1)
})

it('sends the id of the fallback it belongs to, not the newest one', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse(FELL_BACK))
  open()
  const user = await ask('First unanswerable question')
  await screen.findByText(FELL_BACK.answer)

  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ ...FELL_BACK, id: 99, answer: 'A second fallback answer.' }),
  )
  await user.type(screen.getByLabelText('Your question'), 'Second unanswerable question')
  await user.click(screen.getByRole('button', { name: 'Send' }))
  await screen.findByText('A second fallback answer.')

  fetchMock.mockImplementationOnce(async () => jsonResponse(ESCALATION, 201))
  await user.click(screen.getAllByRole('button', { name: SEND_TO_HR_LABEL })[0])

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  const [, init] = fetchMock.mock.calls[2] as [string, RequestInit]
  expect(JSON.parse(init.body as string)).toEqual({ chat_log_id: FELL_BACK.id })
})

// --- failures, which are failures ---------------------------------------------

it('shows the backend wording when the server refuses the question', async () => {
  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ detail: 'The answer could not be recorded. Please try again.' }, 500),
  )
  open()
  await ask()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('The answer could not be recorded.')
})

it('offers a retry for a server that broke', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse({ detail: 'Server fell over.' }, 500))
  open()
  const user = await ask()

  const again = await screen.findByRole('button', { name: 'Try again' })
  await user.click(again)

  expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument()
})

it('asks the same question again on retry, not an empty one', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse({ detail: 'Server fell over.' }, 500))
  open()
  const user = await ask('How many company holidays are there?')

  await user.click(await screen.findByRole('button', { name: 'Try again' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
  expect(JSON.parse(init.body as string)).toEqual({
    question: 'How many company holidays are there?',
  })
})

it('a retry replaces only the turn being retried', async () => {
  /**
   * Every other retry test has a single turn in the transcript, where
   * "replace the one that failed" and "replace all of them" do the same
   * thing. With two, they do not. Found by fault injection.
   */
  open()
  const user = await ask('First question')
  await screen.findByText(ANSWERED.answer)

  fetchMock.mockImplementationOnce(async () => jsonResponse({ detail: 'Server fell over.' }, 500))
  await user.type(screen.getByLabelText('Your question'), 'Second question')
  await user.click(screen.getByRole('button', { name: 'Send' }))
  await screen.findByRole('alert')

  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ ...ANSWERED, id: 16, answer: 'The second answer.' }),
  )
  await user.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('The second answer.')).toBeInTheDocument()
  // The first turn's answer is still there, not thrown back into waiting.
  expect(screen.getByText(ANSWERED.answer)).toBeInTheDocument()
  expect(screen.queryByText(WAITING_LABEL)).not.toBeInTheDocument()
})

it('offers no retry for a question the server will never accept', async () => {
  fetchMock.mockImplementationOnce(async () =>
    jsonResponse({ detail: 'The question cannot be blank.' }, 422),
  )
  open()
  await ask()

  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
})

it('reports an unreachable server rather than failing silently', async () => {
  fetchMock.mockImplementationOnce(() => Promise.reject(new TypeError('Failed to fetch')))
  open()
  await ask()

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be reached/i)
})

it('can ask again after a failure', async () => {
  fetchMock.mockImplementationOnce(async () => jsonResponse({ detail: 'Server fell over.' }, 500))
  open()
  const user = await ask('First question')
  await screen.findByRole('alert')

  await user.type(screen.getByLabelText('Your question'), 'Second question')
  await user.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument()
})

// --- which failures are worth trying again ------------------------------------

it('knows a network failure is worth another go', () => {
  expect(canRetry(new NetworkError('offline'))).toBe(true)
})

it('knows a refused question is not', () => {
  expect(canRetry(new ApiError(422, 'too long'))).toBe(false)
})

it('knows an ended session is not, because the page is about to change', () => {
  expect(canRetry(new ApiError(401, 'signed out'))).toBe(false)
})

it('knows a server that broke is', () => {
  expect(canRetry(new ApiError(500, 'oh dear'))).toBe(true)
})

// --- the length limit -----------------------------------------------------------

it('refuses to send a question longer than the backend will read', async () => {
  open()
  const box = screen.getByLabelText('Your question')
  await userEvent.setup().click(box)
  // Typed character by character would be two thousand keystrokes.
  await userEvent.setup().paste('x'.repeat(MAX_QUESTION_CHARACTERS + 1))

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  expect(screen.getByText(/limited to 2000 characters/i)).toBeInTheDocument()
})

it('sends a question exactly at the limit', async () => {
  open()
  await userEvent.setup().click(screen.getByLabelText('Your question'))
  await userEvent.setup().paste('x'.repeat(MAX_QUESTION_CHARACTERS))

  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
})

it('uses the backend LLM Gateway limit', () => {
  /**
   * The literal, not the constant. The backend's
   * `MAX_QUESTION_CHARACTERS` is 2000 and there is no shared source for
   * the two to read it from, so this pins the number rather than
   * comparing the constant with itself — which would let both drift
   * together and pass.
   */
  expect(MAX_QUESTION_CHARACTERS).toBe(2000)
})

// --- who may open it --------------------------------------------------------------

it('is the page an HR administrator reaches too', async () => {
  open(HR_TOKEN)
  await ask()

  expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument()
})
