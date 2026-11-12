/**
 * Route guards (ON-65).
 *
 * Two separate questions, deliberately answered differently.
 *
 * Not signed in is not a refusal - it is a step that has not happened yet,
 * so it redirects to the login page and remembers where the person was
 * going. Signed in but not allowed *is* a refusal, and it stays on the URL
 * it was asked for and says so. Redirecting that case to somewhere else
 * hides the fact that the page exists and leaves people re-typing a URL
 * they will never be allowed to open.
 *
 * Neither of these is a security control. The token and the role are
 * checked again by Auth Check on every request (step 2 of the
 * architecture); this only decides what the interface shows.
 */
import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { EmptyState } from '../components'
import { ShieldAlert } from '../components/icons'
import { ROLE_LABELS } from '../session/roles'
import { useSession } from '../session/SessionContext'
import { LOGIN_PATH, mayOpen, type RouteDefinition } from './navigation'

/** Where the login page should send someone back to after signing in. */
export interface FromLocation {
  from?: string
}

export function RequireSession() {
  const { session } = useSession()
  const location = useLocation()

  if (session === null) {
    return (
      <Navigate
        replace
        state={{ from: location.pathname } satisfies FromLocation}
        to={LOGIN_PATH}
      />
    )
  }

  return <Outlet />
}

export function RequireRole({
  route,
  children,
}: {
  route: RouteDefinition
  children: ReactNode
}) {
  const { session } = useSession()

  if (session === null || !mayOpen(route, session.role)) {
    const role = session === null ? null : ROLE_LABELS[session.role]

    return (
      <EmptyState
        description={
          role === null
            ? 'Sign in to see this page.'
            : `You are signed in as ${role}, which does not have access to ${route.title}. If that is wrong, ask an HR administrator to check your account.`
        }
        icon={<ShieldAlert />}
        title="Not authorised"
        tone="danger"
      />
    )
  }

  return <>{children}</>
}
