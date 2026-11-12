/**
 * Routing and the guards (ON-65).
 *
 * The two refusals are tested separately because they are different
 * answers to different questions, and conflating them is the usual bug:
 * "not signed in" is a step that has not happened yet and redirects,
 * "signed in but not allowed" is a refusal and stays put and says so.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { EMPLOYEE, HR, renderApp } from '../test/renderApp'

/** The rail is the shell: if it is there, the page rendered inside it. */
function shellIsShowing(): boolean {
  return screen.queryByRole('navigation', { name: 'Navigation' }) !== null
}

describe('signed out', () => {
  it.each(['/chat', '/documents', '/inbox', '/'])(
    'sends a request for %s to the login page',
    (path) => {
      renderApp({ path })

      expect(screen.getByText('Sign in as either role to look at the shell.', { exact: false }))
        .toBeInTheDocument()
      expect(shellIsShowing()).toBe(false)
    },
  )

  it('renders the login page outside the shell', () => {
    // An acceptance criterion in its own right: the login page has no
    // navigation, because there is nothing yet to navigate to.
    renderApp({ path: '/login' })

    expect(shellIsShowing()).toBe(false)
    expect(screen.queryByRole('link', { name: /Chat/ })).toBeNull()
  })

  it('finishes the journey the guard interrupted', async () => {
    // Signing in should land on the page that was asked for, not on the
    // default one. Losing it is invisible when the default happens to be
    // where you were going anyway.
    renderApp({ path: '/documents' })

    await userEvent.click(
      screen.getByRole('button', { name: 'Continue as HR administrator' }),
    )

    expect(screen.getByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(shellIsShowing()).toBe(true)
  })

  it('lands on chat when there was nowhere in particular to go', async () => {
    renderApp({ path: '/login' })

    await userEvent.click(screen.getByRole('button', { name: 'Continue as Employee' }))

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })
})

describe('as an Employee', () => {
  it('lands on chat from the root', () => {
    renderApp({ path: '/', session: EMPLOYEE })

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })

  it('sees only the chat link', () => {
    renderApp({ path: '/chat', session: EMPLOYEE })

    const nav = screen.getByRole('navigation', { name: 'Navigation' })
    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Documents' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'HR Inbox' })).toBeNull()
  })

  it.each(['/documents', '/inbox'])('is refused %s, in place', (path) => {
    renderApp({ path, session: EMPLOYEE })

    expect(screen.getByText('Not authorised')).toBeInTheDocument()
    // Still inside the shell, and still on the URL that was asked for:
    // being bounced elsewhere hides that the page exists at all.
    expect(shellIsShowing()).toBe(true)
  })

  it('is offered the employee quick action', () => {
    renderApp({ path: '/chat', session: EMPLOYEE })

    expect(screen.getByRole('button', { name: 'Ask a question' })).toBeInTheDocument()
  })
})

describe('as an HR administrator', () => {
  it.each([
    ['/documents', 'Documents'],
    ['/inbox', 'HR Inbox'],
    ['/chat', 'Chat'],
  ])('may open %s', (path, title) => {
    renderApp({ path, session: HR })

    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.queryByText('Not authorised')).toBeNull()
  })

  it('sees all three links', () => {
    renderApp({ path: '/chat', session: HR })

    for (const title of ['Documents', 'HR Inbox', 'Chat']) {
      expect(screen.getByRole('link', { name: title })).toBeInTheDocument()
    }
  })

  it('is offered the upload quick action', () => {
    renderApp({ path: '/documents', session: HR })

    expect(screen.getByRole('button', { name: 'Upload a document' })).toBeInTheDocument()
  })
})

describe('pages that do not exist yet', () => {
  it('say which ticket builds them', () => {
    // More use to a teammate than "coming soon", and it is why every route
    // the epic names is routed from the start rather than added one at a
    // time as the pages land.
    renderApp({ path: '/chat', session: EMPLOYEE })

    expect(screen.getByText(/built in ON-48/)).toBeInTheDocument()
  })
})

describe('an address that is not a route', () => {
  it('says so, inside the shell', () => {
    renderApp({ path: '/nothing-here', session: EMPLOYEE })

    expect(screen.getByText('Page not found')).toBeInTheDocument()
    expect(shellIsShowing()).toBe(true)
  })
})

describe('the login page while already signed in', () => {
  it('goes to the application instead', () => {
    renderApp({ path: '/login', session: EMPLOYEE })

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })
})

describe('the development sign-in', () => {
  it('is behind the literal Vite replaces at build time', async () => {
    // Otherwise the alpha ships a way in with no password. Same mechanism
    // as the galleries: the literal is what makes the branch dead code.
    const { readFileSync } = await import('node:fs')
    const { fromSrc } = await import('../test/paths')
    const source = readFileSync(fromSrc('shell', 'LoginPage.tsx'), 'utf8')

    expect(source).toContain('import.meta.env.DEV ?')
  })
})

describe('rendering outside a SessionProvider', () => {
  it('says what is actually wrong', async () => {
    // Reading the session outside the provider gives null, which looks
    // exactly like "signed out" and would send someone to the login page
    // for a reason nobody could find.
    const { default: AppRoutes } = await import('./AppRoutes')
    const { MemoryRouter } = await import('react-router')

    expect(() =>
      render(
        <MemoryRouter initialEntries={['/chat']}>
          <AppRoutes />
        </MemoryRouter>,
      ),
    ).toThrow(/SessionProvider/)
  })
})
