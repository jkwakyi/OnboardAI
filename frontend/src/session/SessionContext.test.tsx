/**
 * The session (ON-65, finished in ON-38).
 *
 * There is one piece of state now - the token - and the session is read
 * out of it. Two pieces, a token and a separate session object, can
 * disagree, and the way they disagree is that the interface shows somebody
 * as signed in with a token the server has stopped accepting. Several of
 * these tests exist to pin that down.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { makeToken } from '../test/tokens'
import { SessionProvider, useSession } from './SessionContext'
import { ROLES, ROLE_LABELS, isRole } from './roles'
import { TOKEN_KEY } from './storage'

const TOKEN = makeToken({ fullName: 'Ada', role: 'employee' })

function Probe() {
  const { session, api, signIn, signOut } = useSession()

  return (
    <div>
      <p>{session === null ? 'signed out' : `${session.fullName} (${session.role})`}</p>
      <p>{`sending: ${api.token ?? 'nothing'}`}</p>
      <button onClick={() => signIn(TOKEN)} type="button">
        sign in
      </button>
      <button onClick={() => signIn('not-a-token')} type="button">
        sign in badly
      </button>
      <button onClick={signOut} type="button">
        sign out
      </button>
    </div>
  )
}

afterEach(() => {
  window.sessionStorage.clear()
})

describe('the session', () => {
  it('starts signed out', () => {
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('signed out')).toBeInTheDocument()
  })

  it('can start signed in, which is how the tests work', () => {
    render(
      <SessionProvider
        initialToken={makeToken({ fullName: 'Hari', role: 'hr_administrator' })}
      >
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('Hari (hr_administrator)')).toBeInTheDocument()
  })

  it('starts signed in from a token left in storage by a previous visit', () => {
    // TD-18's complaint: a refresh used to sign you out.
    window.sessionStorage.setItem(TOKEN_KEY, makeToken({ fullName: 'Ada' }))

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('Ada (employee)')).toBeInTheDocument()
  })

  it('throws away a stored token that has expired', () => {
    // A token that ran out while the tab was closed is not a session, and
    // leaving it in storage would put a dead token in every Authorization
    // header.
    window.sessionStorage.setItem(TOKEN_KEY, makeToken({ expiresInMinutes: -1 }))

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('throws away a stored token it cannot read', () => {
    window.sessionStorage.setItem(TOKEN_KEY, 'not-a-token')

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('signs in and out', async () => {
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'sign in' }))
    expect(screen.getByText('Ada (employee)')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'sign out' }))
    expect(screen.getByText('signed out')).toBeInTheDocument()
  })

  it('keeps the token so a refresh does not sign you out', async () => {
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'sign in' }))

    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN)
  })

  it('takes the token out of storage on the way out', async () => {
    // Signing in first, rather than starting from initialToken. That
    // route never writes to storage, so there was nothing to clear and
    // the assertion below passed whether or not signing out cleared
    // anything - which is how it let a fault through.
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'sign in' }))
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN)

    await userEvent.click(screen.getByRole('button', { name: 'sign out' }))

    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('refuses a token it cannot read rather than appearing to succeed', async () => {
    // signIn returns false so the login page can say something, instead of
    // the person being bounced straight back to it with no explanation.
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'sign in badly' }))

    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('gives out an API client carrying the current token', async () => {
    // One source of truth. If the client could carry a different token
    // from the one the rail was drawn from, the two would eventually
    // disagree about who is signed in.
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('sending: nothing')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'sign in' }))
    expect(screen.getByText(`sending: ${TOKEN}`)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'sign out' }))
    expect(screen.getByText('sending: nothing')).toBeInTheDocument()
  })

  it('refuses to be read outside its provider', () => {
    // Returning null here would be indistinguishable from "signed out",
    // and the symptom would be a login page nobody could explain.
    expect(() => render(<Probe />)).toThrow(/SessionProvider/)
  })
})

describe('roles', () => {
  it('are the two the users table is constrained to', () => {
    // These strings are the contract with Auth Check. Spelling one
    // differently here produces an interface that disagrees with the
    // server about who somebody is.
    expect([...ROLES]).toEqual(['employee', 'hr_administrator'])
  })

  it('each have a label to show', () => {
    for (const role of ROLES) {
      expect(ROLE_LABELS[role].length, `${role} has no label`).toBeGreaterThan(0)
    }
  })

  it('recognise themselves and nothing else', () => {
    expect(isRole('employee')).toBe(true)
    expect(isRole('hr_administrator')).toBe(true)
    expect(isRole('admin')).toBe(false)
    expect(isRole('HR_ADMINISTRATOR')).toBe(false)
  })
})
