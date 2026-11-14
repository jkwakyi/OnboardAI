/**
 * The login page (ON-38).
 *
 * Outside the shell: there is nothing to navigate to until someone is
 * signed in.
 *
 * This replaces the two development buttons ON-65 shipped behind
 * `import.meta.env.DEV`. There is now a real Auth Service, a real endpoint
 * and a real token, so the stub is gone rather than kept alongside — a
 * password-free way in that only works in development is still a
 * password-free way in that somebody will eventually ship. That closes
 * TD-18.
 */
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'

import { login } from '../api/auth'
import { ApiError, NetworkError } from '../api/errors'
import { Button, Card, FormField } from '../components'
import { useSession } from '../session/SessionContext'
import type { FromLocation } from './guards'
import { DEFAULT_PATH } from './navigation'
import './LoginPage.css'

/**
 * What to say when the backend accepted the credentials and handed back a
 * token this frontend cannot use. Rare, and worth its own message: the
 * person did nothing wrong and retrying will not help, so "wrong password"
 * would send them looking in the wrong place.
 */
export const UNUSABLE_TOKEN_MESSAGE =
  'Signing in worked, but the server sent a session this page could not read. Please tell the team.'

export default function LoginPage() {
  const { session, signIn } = useSession()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [signingIn, setSigningIn] = useState(false)

  // Where the guard turned them away from, so signing in finishes the
  // journey they started rather than dropping them on the default page.
  const from = (location.state as FromLocation | null)?.from ?? DEFAULT_PATH

  // One redirect, declared rather than called. Signing in and then calling
  // navigate() races this branch: the session lands first, this renders a
  // redirect to the default page, and the imperative one is overridden -
  // so the page the guard interrupted is quietly lost.
  if (session !== null) {
    return <Navigate replace to={from} />
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setProblem(null)
    setSigningIn(true)

    try {
      const token = await login(email, password)
      if (!signIn(token)) {
        setProblem(UNUSABLE_TOKEN_MESSAGE)
      }
      // On success nothing else happens here: the session changes, this
      // component renders again, and the <Navigate> above does the rest.
    } catch (failure) {
      if (failure instanceof ApiError || failure instanceof NetworkError) {
        setProblem(failure.message)
      } else {
        throw failure
      }
    } finally {
      setSigningIn(false)
    }
  }

  return (
    <main className="login">
      <div className="login__panel">
        <p className="login__name">OnboardAI</p>
        <p className="login__tagline">
          Ask about company policy and get an answer with its source.
        </p>

        <Card label="Sign in">
          <form className="login__form" noValidate onSubmit={submit}>
            <FormField
              autoComplete="username"
              id="login-email"
              label="Email address"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
            <FormField
              autoComplete="current-password"
              id="login-password"
              label="Password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />

            {/* role="alert" so it is announced when it appears, rather than
                being a change somebody using a screen reader has to go
                looking for. */}
            {problem !== null && (
              <p className="login__problem" role="alert">
                {problem}
              </p>
            )}

            <Button loading={signingIn} type="submit">
              Sign in
            </Button>
          </form>
        </Card>
      </div>
    </main>
  )
}
