/**
 * The login page (ON-65's placeholder for ON-38).
 *
 * Outside the shell: there is nothing to navigate to until someone is
 * signed in.
 *
 * ON-38 builds the real form against POST /api/auth/login and handles the
 * token. Until then this page signs you in to a stubbed session so the
 * shell, the navigation and the guards can be built and looked at - and
 * so that both roles can be seen, which is most of what there is to check
 * about a role-based layout.
 *
 * Those two buttons are behind `import.meta.env.DEV`, which Vite replaces
 * with `false` when it builds, so they are dead code the bundler drops
 * rather than a way into the alpha with no password. A test checks the
 * literal is still there.
 */
import { Navigate, useLocation } from 'react-router'

import { Button, Card, EmptyState } from '../components'
import { UserRound } from '../components/icons'
import type { Role } from '../session/roles'
import { useSession } from '../session/SessionContext'
import type { FromLocation } from './guards'
import { DEFAULT_PATH } from './navigation'
import './LoginPage.css'

/** Who you are while there is no Auth Service. Development only. */
const STUB_NAMES: Record<Role, string> = {
  employee: 'Development Employee',
  hr_administrator: 'Development HR administrator',
}

export default function LoginPage() {
  const { session, signIn } = useSession()
  const location = useLocation()

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

  function continueAs(role: Role): void {
    signIn({ fullName: STUB_NAMES[role], role })
  }

  return (
    <main className="login">
      <div className="login__panel">
        <p className="login__name">OnboardAI</p>
        <p className="login__tagline">
          Ask about company policy and get an answer with its source.
        </p>

        {import.meta.env.DEV ? (
          <Card accent="info" label="Development sign-in">
            <p className="login__note">
              There is no Auth Service yet (ON-36) and no login form (ON-38).
              Sign in as either role to look at the shell.
            </p>
            <div className="login__roles">
              <Button icon={<UserRound />} onClick={() => continueAs('employee')}>
                Continue as Employee
              </Button>
              <Button
                icon={<UserRound />}
                onClick={() => continueAs('hr_administrator')}
                variant="secondary"
              >
                Continue as HR administrator
              </Button>
            </div>
          </Card>
        ) : (
          <EmptyState
            description="The sign-in form is built in ON-38, against POST /api/auth/login."
            icon={<UserRound />}
            title="Sign-in is not available yet"
          />
        )}
      </div>
    </main>
  )
}
