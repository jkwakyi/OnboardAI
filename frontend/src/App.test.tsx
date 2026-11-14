/**
 * The application entry point (ON-65).
 *
 * App itself is now three branches: two development galleries and the
 * router. What is worth asserting here is that the third one is what
 * ships, and that it starts at the login page when nobody is signed in.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import App from './App'
import { SessionProvider } from './session/SessionContext'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

describe('App', () => {
  it('renders the application name', () => {
    renderAt('/login')

    expect(screen.getByText('OnboardAI')).toBeInTheDocument()
  })

  it('sends somebody who is not signed in to the login page', () => {
    renderAt('/chat')

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('renders without third-party template assets', () => {
    // Epic ON-62: original design, no copied images.
    const { container } = renderAt('/login')

    expect(container.querySelectorAll('img')).toHaveLength(0)
  })
})
