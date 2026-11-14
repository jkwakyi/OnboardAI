/**
 * Render the application at a path, as somebody or as nobody (ON-65,
 * updated in ON-38).
 *
 * The shell's behaviour is almost entirely "who are you and where are you
 * going", so nearly every test needs the same two knobs. A `MemoryRouter`
 * rather than the real one, because jsdom has one history shared by the
 * whole file and tests that push to it leak into each other.
 *
 * Signing in is now a token rather than a made-up session object, which is
 * what the application itself holds since ON-38 — so these tests exercise
 * the real decode path instead of a shape nothing else uses.
 */
import type { ReactElement } from 'react'

import { render, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { SessionProvider } from '../session/SessionContext'
import AppRoutes from '../shell/AppRoutes'

export { EMPLOYEE_TOKEN, HR_TOKEN, makeToken } from './tokens'

export function renderApp({
  path = '/',
  token = null,
}: { path?: string; token?: string | null } = {}): RenderResult {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider initialToken={token}>
        <AppRoutes />
      </SessionProvider>
    </MemoryRouter>,
  )
}

/** The same, for a component that needs a router and a session around it. */
export function renderInApp(
  element: ReactElement,
  { path = '/', token = null }: { path?: string; token?: string | null } = {},
): RenderResult {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider initialToken={token}>{element}</SessionProvider>
    </MemoryRouter>,
  )
}
