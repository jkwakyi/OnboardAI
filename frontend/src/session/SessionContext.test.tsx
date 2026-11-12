/**
 * The session (ON-65).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { SessionProvider, useSession } from './SessionContext'
import { ROLES, ROLE_LABELS, isRole } from './roles'

function Probe() {
  const { session, signIn, signOut } = useSession()

  return (
    <div>
      <p>{session === null ? 'signed out' : `${session.fullName} (${session.role})`}</p>
      <button onClick={() => signIn({ fullName: 'Ada', role: 'employee' })} type="button">
        sign in
      </button>
      <button onClick={signOut} type="button">
        sign out
      </button>
    </div>
  )
}

describe('the session', () => {
  it('starts signed out', () => {
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('signed out')).toBeInTheDocument()
  })

  it('can start signed in, which is how the tests and the stub work', () => {
    render(
      <SessionProvider initialSession={{ fullName: 'Hari', role: 'hr_administrator' }}>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByText('Hari (hr_administrator)')).toBeInTheDocument()
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
