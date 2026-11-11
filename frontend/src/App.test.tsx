import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the application name', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'OnboardAI' })).toBeInTheDocument()
  })

  it('renders without third-party template assets', () => {
    const { container } = render(<App />)
    expect(container.querySelectorAll('img')).toHaveLength(0)
  })
})
