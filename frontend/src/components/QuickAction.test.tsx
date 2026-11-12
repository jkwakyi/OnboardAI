/**
 * QuickAction (ON-64).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import QuickAction from './QuickAction'

describe('QuickAction', () => {
  it('is a button named after its label', () => {
    render(<QuickAction label="Ask a question" />)

    expect(screen.getByRole('button', { name: 'Ask a question' })).toBeInTheDocument()
  })

  it('shows the plus, hidden from the accessibility tree', () => {
    const { container } = render(<QuickAction label="Upload a document" />)

    const icon = container.querySelector('.oa-button__icon')
    expect(icon?.querySelector('svg')).not.toBeNull()
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('calls onClick', async () => {
    const onClick = vi.fn()
    render(<QuickAction label="Upload" onClick={onClick} />)

    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('can be disabled', async () => {
    const onClick = vi.fn()
    render(<QuickAction label="Upload" disabled onClick={onClick} />)

    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('carries the accent it was given', () => {
    render(<QuickAction label="Send to HR" accent="escalations" />)

    expect(screen.getByRole('button', { name: 'Send to HR' })).toHaveClass(
      'oa-accent-escalations',
    )
  })

  it('is a real Button underneath', () => {
    // Not cosmetic: it is why the loading, disabled and focus behaviour is
    // the behaviour Button.test.tsx already covers.
    render(<QuickAction label="Upload" />)

    expect(screen.getByRole('button', { name: 'Upload' })).toHaveClass('oa-button')
  })
})
