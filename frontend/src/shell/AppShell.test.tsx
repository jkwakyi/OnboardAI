/**
 * The shell itself (ON-65): the frame, and getting around it by keyboard.
 *
 * The keyboard assertions are the substance. A skip link that is present
 * but points at nothing, or an active link that is coloured but carries no
 * `aria-current`, both look completely correct in a screenshot.
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { CONTENT_ID } from './AppShell'
import { EMPLOYEE_TOKEN, HR_TOKEN, renderApp } from '../test/renderApp'

describe('the shell', () => {
  it('names the page in the top bar', () => {
    renderApp({ path: '/inbox', token: HR_TOKEN })

    expect(screen.getByRole('heading', { level: 1, name: 'HR Inbox' })).toBeInTheDocument()
  })

  it('says which role is signed in', () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    const chip = screen.getByText('Signed in as', { exact: false }).closest('p')

    expect(chip).toHaveTextContent('Signed in as HR administrator')
  })

  it('shows who is signed in, by name', () => {
    renderApp({ path: '/chat', token: EMPLOYEE_TOKEN })

    expect(screen.getByText('Ada Employee')).toBeInTheDocument()
  })

  it('shows the application name as plain text, with no image', () => {
    // Epic ON-62: no product branding, the app name is plain text.
    const { container } = renderApp({ path: '/chat', token: EMPLOYEE_TOKEN })

    expect(screen.getByText('OnboardAI')).toBeInTheDocument()
    expect(container.querySelectorAll('img')).toHaveLength(0)
  })
})

describe('the keyboard', () => {
  it('reaches the skip link first', async () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    await userEvent.tab()

    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveFocus()
  })

  it('points the skip link at something that can take focus', async () => {
    // The usual failure: an anchor to a non-focusable target scrolls the
    // page and leaves the keyboard in the navigation, so the link appears
    // to do nothing at all.
    renderApp({ path: '/chat', token: HR_TOKEN })

    const skip = screen.getByRole('link', { name: 'Skip to content' })
    expect(skip).toHaveAttribute('href', `#${CONTENT_ID}`)

    const target = document.getElementById(CONTENT_ID)
    expect(target, 'the skip link points at nothing').not.toBeNull()
    expect(target).toHaveAttribute('tabindex', '-1')
    expect(target?.tagName).toBe('MAIN')
  })

  it('reaches the quick action and every navigation link', async () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    const reached: string[] = []
    for (let press = 0; press < 6; press += 1) {
      await userEvent.tab()
      const focused = document.activeElement
      if (focused !== null && focused.textContent !== null) {
        reached.push(focused.textContent.trim())
      }
    }

    expect(reached).toContain('Upload a document')
    expect(reached).toContain('Documents')
    expect(reached).toContain('HR Inbox')
    expect(reached).toContain('Chat')
  })

  it('marks the active link, and only the active link', async () => {
    renderApp({ path: '/documents', token: HR_TOKEN })

    expect(screen.getByRole('link', { name: 'Documents' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    for (const title of ['HR Inbox', 'Chat']) {
      expect(screen.getByRole('link', { name: title })).not.toHaveAttribute('aria-current')
    }

    await userEvent.click(screen.getByRole('link', { name: 'Chat' }))

    expect(screen.getByRole('link', { name: 'Chat' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Documents' })).not.toHaveAttribute(
      'aria-current',
    )
  })
})

describe('navigating', () => {
  it('follows a link in the rail', async () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    await userEvent.click(screen.getByRole('link', { name: 'HR Inbox' }))

    expect(screen.getByRole('heading', { level: 1, name: 'HR Inbox' })).toBeInTheDocument()
  })

  it('follows the quick action', async () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    await userEvent.click(screen.getByRole('button', { name: 'Upload a document' }))

    expect(screen.getByRole('heading', { level: 1, name: 'Documents' })).toBeInTheDocument()
  })

  it('signs out to the login page', async () => {
    renderApp({ path: '/chat', token: HR_TOKEN })

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(screen.queryByRole('navigation', { name: 'Navigation' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})
