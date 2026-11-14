/**
 * The route table, wired up (ON-65).
 *
 * Every route the epic names exists from the start, including the ones
 * whose pages are later tickets. That way the navigation is the real
 * navigation and the guards are the real guards, rather than something
 * assembled page by page and only true once the last one lands.
 *
 * The routes come from `navigation.ts`, which is also what the rail is
 * built from — so a route cannot be reachable by typing its URL while
 * being absent from the navigation, which is the usual way a half-built
 * page gets found.
 */
import { Navigate, Route, Routes } from 'react-router'

import type { ReactNode } from 'react'

import AppShell from './AppShell'
import DocumentsPage from './DocumentsPage'
import LoginPage from './LoginPage'
import NotAvailableYet from './NotAvailableYet'
import NotFound from './NotFound'
import { RequireRole, RequireSession } from './guards'
import { DEFAULT_PATH, LOGIN_PATH, ROUTES } from './navigation'

/**
 * The pages that exist, by path.
 *
 * A route with no entry here renders `NotAvailableYet` naming the ticket
 * that builds it. Keyed off the same `ROUTES` table rather than listed
 * separately, so a page cannot be built and left unreachable, or routed
 * at a path the rail does not show.
 */
const PAGES: Record<string, ReactNode> = {
  '/documents': <DocumentsPage />,
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* Outside the shell: there is nothing to navigate to yet. */}
      <Route element={<LoginPage />} path={LOGIN_PATH} />

      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route element={<Navigate replace to={DEFAULT_PATH} />} index />

          {ROUTES.map((route) => (
            <Route
              element={
                <RequireRole route={route}>
                  {PAGES[route.path] ?? <NotAvailableYet route={route} />}
                </RequireRole>
              }
              key={route.path}
              path={route.path}
            />
          ))}

          <Route element={<NotFound />} path="*" />
        </Route>
      </Route>
    </Routes>
  )
}
