/**
 * Who is signed in (ON-65).
 *
 * The shell needs two things about a person: what to call them and what
 * they are allowed to see. That is all this holds.
 *
 * It deliberately does not model the login response. The Interface
 * Contracts say "login credentials in, login token out" and leave the
 * fields to ON-13 and ON-36; ON-38 owns the token and the API client. When
 * those land, ON-38 maps whatever the response turns out to be onto this
 * `Session` and calls `signIn`. Guessing the shape here would mean writing
 * a contract nobody agreed to and then finding out.
 *
 * The session is in memory only, so a refresh signs you out. Where a token
 * is kept, and for how long, is ON-38's decision and not one to make twice.
 */
import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

import type { Role } from './roles'

export interface Session {
  /** The signed-in person's name, shown in the rail. */
  fullName: string
  role: Role
}

export interface SessionValue {
  /** Null when nobody is signed in. */
  session: Session | null
  signIn: (session: Session) => void
  signOut: () => void
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({
  children,
  initialSession = null,
}: {
  children: ReactNode
  /** Lets a test, or the development sign-in, start signed in. */
  initialSession?: Session | null
}) {
  const [session, setSession] = useState<Session | null>(initialSession)

  const signIn = useCallback((next: Session) => setSession(next), [])
  const signOut = useCallback(() => setSession(null), [])

  const value = useMemo<SessionValue>(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  )

  return <SessionContext value={value}>{children}</SessionContext>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)

  if (value === null) {
    // Reading the session outside the provider gives `null`, which looks
    // exactly like "signed out" and would send someone to the login page
    // for a reason nobody could find. Better to say what actually happened.
    throw new Error('useSession must be called inside a SessionProvider')
  }

  return value
}
