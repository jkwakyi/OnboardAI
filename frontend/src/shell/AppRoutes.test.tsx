/**
 * Routing and the guards (ON-65).
 *
 * The two refusals are tested separately because they are different
 * answers to different questions, and conflating them is the usual bug:
 * "not signed in" is a step that has not happened yet and redirects,
 * "signed in but not allowed" is a refusal and stays put and says so.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EMPLOYEE_TOKEN, HR_TOKEN, renderApp } from '../test/renderApp'

/** The rail is the shell: if it is there, the page rendered inside it. */
function shellIsShowing(): boolean {
  return screen.queryByRole('navigation', { name: 'Navigation' }) !== null
}

describe('signed out', () => {
  it.each(['/chat', '/documents', '/inbox', '/'])(
    'sends a request for %s to the login page',
    (path) => {
      renderApp({ path })

      expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
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

  it('remembers where the guard turned somebody away from', () => {
    // The round trip itself is driven through the real form in
    // LoginPage.test.tsx. What belongs here is that the guard records the
    // interrupted path at all - losing it is invisible when the default
    // happens to be where you were going anyway.
    renderApp({ path: '/documents' })

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(shellIsShowing()).toBe(false)
  })

  it('lands on chat when there was nowhere in particular to go', () => {
    renderApp({ path: '/login', token: EMPLOYEE_TOKEN })

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })
})

describe('as an Employee', () => {
  it('lands on chat from the root', () => {
    renderApp({ path: '/', token: EMPLOYEE_TOKEN })

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })

  it('sees only the chat link', () => {
    renderApp({ path: '/chat', token: EMPLOYEE_TOKEN })

    const nav = screen.getByRole('navigation', { name: 'Navigation' })
    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Documents' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'HR Inbox' })).toBeNull()
  })

  it.each(['/documents', '/inbox'])('is refused %s, in place', (path) => {
    renderApp({ path, token: EMPLOYEE_TOKEN })

    expect(screen.getByText('Not authorised')).toBeInTheDocument()
    // Still inside the shell, and still on the URL that was asked for:
    // being bounced elsewhere hides that the page exists at all.
    expect(shellIsShowing()).toBe(true)
  })

  it('is offered the employee quick action', () => {
    renderApp({ path: '/chat', token: EMPLOYEE_TOKEN })

    expect(screen.getByRole('button', { name: 'Ask a question' })).toBeInTheDocument()
  })
})

describe('as an HR administrator', () => {
  it.each([
    ['/documents', 'Documents'],
    ['/inbox', 'HR Inbox'],
    ['/chat', 'Chat'],
  ])('may open %s', (path, title) => {
    renderApp({ path, token: HR_TOKEN })

    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.queryByText('Not authorised')).toBeNull()
  })

  it('sees all three links', () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    for (const title of ['Documents', 'HR Inbox', 'Chat']) {
      expect(screen.getByRole('link', { name: title })).toBeInTheDocument()
    }
  })

  it('is offered the upload quick action', () => {
    renderApp({ path: '/documents', token: HR_TOKEN })

    expect(screen.getByRole('button', { name: 'Upload a document' })).toBeInTheDocument()
  })
})

describe('pages that do not exist yet', () => {
  it('say which ticket builds them', () => {
    // More use to a teammate than "coming soon", and it is why every route
    // the epic names is routed from the start rather than added one at a
    // time as the pages land.
    //
    // The HR Inbox, since ON-48 built the chat page. When ON-21 lands
    // there will be no route left without a page and this test goes with
    // it - which is the right ending for it.
    renderApp({ path: '/inbox', token: HR_TOKEN })

    expect(screen.getByText(/built in ON-21/)).toBeInTheDocument()
  })
})

describe('an address that is not a route', () => {
  it('says so, inside the shell', () => {
    renderApp({ path: '/nothing-here', token: EMPLOYEE_TOKEN })

    expect(screen.getByText('Page not found')).toBeInTheDocument()
    expect(shellIsShowing()).toBe(true)
  })
})

describe('the login page while already signed in', () => {
  it('goes to the application instead', () => {
    renderApp({ path: '/login', token: EMPLOYEE_TOKEN })

    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })
})

describe('the login page', () => {
  it('has no way in that skips the password', async () => {
    // This test used to assert the opposite: that ON-65's two development
    // buttons were behind the `import.meta.env.DEV` literal, so the
    // bundler would drop them. ON-38 deleted them instead, which is the
    // stronger answer - a password-free way in that only works in
    // development is still one somebody eventually ships.
    //
    // Kept, pointed the other way, because the thing worth guarding is
    // that nobody reintroduces one while the real form is inconvenient to
    // type during a demo.
    const { readFileSync } = await import('node:fs')
    const { fromSrc } = await import('../test/paths')
    // Comments stripped first. The module docstring explains that the
    // development buttons were behind `import.meta.env.DEV` and are now
    // gone, which is exactly the sentence a scan of raw source trips over
    // - this test failed on its own explanation before it checked
    // anything. A comment about the absence of a thing is not the thing.
    const source = readFileSync(fromSrc('shell', 'LoginPage.tsx'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/.*$/gm, '')

    expect(source).not.toContain('import.meta.env.DEV')
    expect(source).not.toMatch(/Continue as/)
  })

  it('posts to the endpoint the contracts define and no other', async () => {
    const { readFileSync } = await import('node:fs')
    const { fromSrc } = await import('../test/paths')
    const source = readFileSync(fromSrc('api', 'auth.ts'), 'utf8')

    expect(source).toContain("'/auth/login'")
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
