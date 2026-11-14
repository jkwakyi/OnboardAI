/**
 * The login page (ON-38).
 *
 * `fetch` is replaced per test, so what is being checked is the page's
 * behaviour against each thing the Login API can answer: a token, a
 * refusal, an attempt limit, and a backend that is not running.
 *
 * The one that matters most is the last test in the file. A password must
 * not end up anywhere it can be read back.
 */
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '../test/renderApp'
import { makeToken } from '../test/tokens'
import { UNUSABLE_TOKEN_MESSAGE } from './LoginPage'

const EMAIL = 'employee@onboardai.example'
const PASSWORD = 'a development password'

function backendReplying(
  body: unknown,
  { status = 200, headers = {} as Record<string, string> } = {},
) {
  const fetchImpl = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      }),
  )
  vi.stubGlobal('fetch', fetchImpl)
  return fetchImpl
}

async function signIn(email = EMAIL, password = PASSWORD) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email address'), email)
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  return user
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

// --- the form ----------------------------------------------------------

describe('the form', () => {
  it('asks for an email address and a password', () => {
    renderApp({ path: '/login' })

    expect(screen.getByLabelText('Email address')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('hides what is typed in the password field', () => {
    renderApp({ path: '/login' })

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it('tells the password manager which field is which', () => {
    // Without autocomplete hints a password manager either does not offer
    // to fill the form or fills the wrong field.
    renderApp({ path: '/login' })

    expect(screen.getByLabelText('Email address')).toHaveAttribute('autocomplete', 'username')
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password')
  })

  it('no longer offers a way in without a password', () => {
    // ON-65 shipped two development buttons behind import.meta.env.DEV.
    // There is a real Auth Service now, so the stub is gone rather than
    // kept alongside - that is what closes TD-18.
    renderApp({ path: '/login' })

    expect(screen.queryByRole('button', { name: /Continue as/ })).toBeNull()
  })
})

// --- signing in --------------------------------------------------------

describe('signing in', () => {
  it('posts the credentials to the Login API', async () => {
    const fetchImpl = backendReplying({ token: makeToken() })
    renderApp({ path: '/login' })

    await signIn()

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledOnce())
    const [url, options] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/api\/auth\/login$/)
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body as string)).toEqual({ email: EMAIL, password: PASSWORD })
  })

  it('lands on the chat page', async () => {
    backendReplying({ token: makeToken({ role: 'employee' }) })
    renderApp({ path: '/login' })

    await signIn()

    expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })

  it('shows the name and role out of the token', async () => {
    backendReplying({
      token: makeToken({ role: 'hr_administrator', fullName: 'Jordan Blake' }),
    })
    renderApp({ path: '/login' })

    await signIn('hr@onboardai.example')

    expect(await screen.findByText('Jordan Blake')).toBeInTheDocument()
    // Twice: the rail says who you are and the top bar chips your role.
    // getByText would fail on the second one, which is how this test found
    // out.
    expect(screen.getAllByText('HR administrator')).toHaveLength(2)
  })

  it('finishes the journey the guard interrupted', async () => {
    // Asked for /documents, was sent to the login page, and should end up
    // at /documents rather than on the default page.
    backendReplying({ token: makeToken({ role: 'hr_administrator' }) })
    renderApp({ path: '/documents' })

    await signIn('hr@onboardai.example')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  })

  it('keeps the token so a refresh does not sign you out', async () => {
    // TD-18's complaint, which this closes.
    const token = makeToken()
    backendReplying({ token })
    renderApp({ path: '/login' })

    await signIn()
    await screen.findByRole('heading', { name: 'Chat' })

    expect(window.sessionStorage.getItem('onboardai.token')).toBe(token)
  })
})

// --- when it does not work --------------------------------------------

describe('when signing in does not work', () => {
  it('shows what the backend said about the credentials', async () => {
    backendReplying({ detail: 'The email address or password is incorrect.' }, { status: 401 })
    renderApp({ path: '/login' })

    await signIn(EMAIL, 'the wrong password')

    expect(
      await screen.findByText('The email address or password is incorrect.'),
    ).toBeInTheDocument()
  })

  it('stays on the login page', async () => {
    backendReplying({ detail: 'The email address or password is incorrect.' }, { status: 401 })
    renderApp({ path: '/login' })

    await signIn(EMAIL, 'wrong')

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('announces the problem rather than leaving it to be noticed', async () => {
    backendReplying({ detail: 'The email address or password is incorrect.' }, { status: 401 })
    renderApp({ path: '/login' })

    await signIn(EMAIL, 'wrong')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The email address or password is incorrect.',
    )
  })

  it('says to wait when the attempt limit has been reached', async () => {
    backendReplying(
      { detail: 'Too many failed sign-in attempts. Please wait and try again.' },
      { status: 429, headers: { 'Retry-After': '889' } },
    )
    renderApp({ path: '/login' })

    await signIn(EMAIL, 'wrong')

    expect(await screen.findByText(/Too many failed sign-in attempts/)).toBeInTheDocument()
  })

  it('says the server could not be reached when it could not', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    renderApp({ path: '/login' })

    await signIn()

    expect(await screen.findByText(/could not be reached/)).toBeInTheDocument()
  })

  it('does not claim the password was wrong when the token is unreadable', async () => {
    // A 200 with a token this page cannot read. The person did nothing
    // wrong and retrying will not help, so "wrong password" would send
    // them looking in the wrong place.
    backendReplying({ token: 'not-a-token' })
    renderApp({ path: '/login' })

    await signIn()

    expect(await screen.findByText(UNUSABLE_TOKEN_MESSAGE)).toBeInTheDocument()
  })

  it('clears the old problem when trying again', async () => {
    backendReplying({ detail: 'The email address or password is incorrect.' }, { status: 401 })
    renderApp({ path: '/login' })
    const user = await signIn(EMAIL, 'wrong')
    await screen.findByRole('alert')

    backendReplying({ token: makeToken() })
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument()
    // And the old message is gone. Without this the test passed whether
    // or not the problem was cleared, because a successful sign-in
    // navigates away either way - which is how it let a fault through.
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('clears the old problem before the next attempt finishes', async () => {
    // The moment that matters is between submitting and the reply: an
    // error from the previous attempt still on screen reads as a fresh
    // failure of this one.
    backendReplying({ detail: 'The email address or password is incorrect.' }, { status: 401 })
    renderApp({ path: '/login' })
    const user = await signIn(EMAIL, 'wrong')
    await screen.findByRole('alert')

    let release: (value: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Promise<Response>((resolve) => {
        release = resolve
      })),
    )
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())

    release(
      new Response(JSON.stringify({ token: makeToken() }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
})

// --- the password ------------------------------------------------------

describe('the password', () => {
  it('is nowhere it can be read back', async () => {
    // The one test in this file worth failing a release over. A password
    // in storage, or in the URL, is a password somebody else can read.
    backendReplying({ token: makeToken() })
    renderApp({ path: '/login' })

    await signIn()
    await screen.findByRole('heading', { name: 'Chat' })

    const everythingStored = [
      ...Object.values({ ...window.sessionStorage }),
      ...Object.values({ ...window.localStorage }),
      window.location.href,
      document.body.innerHTML,
    ].join(' ')

    expect(everythingStored).not.toContain(PASSWORD)
  })
})
