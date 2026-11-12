/**
 * Render the application at a path, as somebody or as nobody (ON-65).
 *
 * The shell's behaviour is almost entirely "who are you and where are you
 * going", so nearly every test needs the same two knobs. A `MemoryRouter`
 * rather than the real one, because jsdom has one history shared by the
 * whole file and tests that push to it leak into each other.
 */
import type { ReactElement } from 'react'

import { render, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import AppRoutes from '../shell/AppRoutes'
import { SessionProvider, type Session } from '../session/SessionContext'

export const EMPLOYEE: Session = { fullName: 'Ada Employee', role: 'employee' }

export const HR: Session = { fullName: 'Hari Administrator', role: 'hr_administrator' }

export function renderApp(
  { path = '/', session = null }: { path?: string; session?: Session | null } = {},
): RenderResult {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider initialSession={session}>
        <AppRoutes />
      </SessionProvider>
    </MemoryRouter>,
  )
}

/** The same, for a component that needs a router and a session around it. */
export function renderInApp(
  element: ReactElement,
  { path = '/', session = null }: { path?: string; session?: Session | null } = {},
): RenderResult {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider initialSession={session}>{element}</SessionProvider>
    </MemoryRouter>,
  )
}
