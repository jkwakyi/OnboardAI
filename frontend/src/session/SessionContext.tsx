/**
 * Who is signed in (ON-65, finished in ON-38).
 *
 * ON-65 held a made-up `{fullName, role}` and said the shape of a real
 * session was ON-38's to decide. It is now decided, and it is simpler than
 * the placeholder: there is one piece of state, the **token**, and the
 * session is read out of it.
 *
 * That matters more than it looks. Two pieces of state — a token and a
 * separate session object — can disagree, and the way they disagree is
 * that the interface shows somebody as signed in with a token the server
 * has stopped accepting. One source means the rail, the guards and the
 * Authorization header can never say different things.
 *
 * The claims are the token's own account of itself and are not verified
 * here; `session/token.ts` explains why that is fine for drawing a page and
 * not fine for protecting anything. Auth Check (ON-14) is what enforces
 * access, on every request.
 */
import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

import { createApiClient, type ApiClient } from '../api/client'
import type { Role } from './roles'
import { clearStoredToken, readStoredToken, storeToken } from './storage'
import { readToken } from './token'

export interface Session {
  userId: number
  /** The signed-in person's name, shown in the rail. */
  fullName: string
  email: string
  role: Role
  /** When the token runs out, after which every request will be refused. */
  expiresAt: Date
}

export interface SessionValue {
  /** Null when nobody is signed in. */
  session: Session | null
  /** An API client that sends the current token and signs out on a 401. */
  api: ApiClient
  /**
   * Take a token from `POST /api/auth/login`.
   *
   * Returns false for a token that cannot be read or has already expired,
   * so the login page can say something rather than appearing to succeed
   * and then bouncing the person straight back.
   */
  signIn: (token: string) => boolean
  signOut: () => void
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({
  children,
  initialToken,
}: {
  children: ReactNode
  /**
   * Starts signed in. For tests, and for nothing else — the real initial
   * token comes from storage, which is read once below.
   */
  initialToken?: string | null
}) {
  const [token, setToken] = useState<string | null>(() => {
    // Read once, on the first render, rather than in an effect: an effect
    // runs after the first paint, so the app would render the login page
    // and then replace it, and anybody watching would see a flicker of
    // being signed out on every refresh.
    const candidate = initialToken ?? readStoredToken()
    // A token that has expired while the tab was closed is not a session.
    // Clearing it here keeps a dead token out of the Authorization header.
    if (readToken(candidate) === null) {
      if (candidate !== null && candidate !== undefined) clearStoredToken()
      return null
    }
    return candidate ?? null
  })

  const session = useMemo<Session | null>(() => {
    const claims = readToken(token)
    if (claims === null) return null
    return {
      userId: claims.userId,
      fullName: claims.fullName,
      email: claims.email,
      role: claims.role,
      expiresAt: claims.expiresAt,
    }
  }, [token])

  const signOut = useCallback(() => {
    clearStoredToken()
    setToken(null)
  }, [])

  const signIn = useCallback((next: string) => {
    if (readToken(next) === null) return false
    storeToken(next)
    setToken(next)
    return true
  }, [])

  const api = useMemo(
    () => createApiClient({ token, onUnauthorised: signOut }),
    [token, signOut],
  )

  const value = useMemo<SessionValue>(
    () => ({ session, api, signIn, signOut }),
    [session, api, signIn, signOut],
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
