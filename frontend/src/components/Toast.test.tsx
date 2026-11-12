/**
 * Toast (ON-64).
 *
 * The role is the substance here. `alert` interrupts whatever a screen
 * reader is in the middle of; `status` waits. Using `alert` for everything
 * is the common shortcut and it turns every routine confirmation into an
 * interruption.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import Toast from './Toast'

describe('Toast', () => {
  it('shows its message', () => {
    render(<Toast>Document uploaded.</Toast>)

    expect(screen.getByText('Document uploaded.')).toBeInTheDocument()
  })

  it('shows a title above the message when given one', () => {
    render(<Toast title="Uploaded">handbook.pdf is being processed.</Toast>)

    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(screen.getByText('handbook.pdf is being processed.')).toBeInTheDocument()
  })

  it.each(['info', 'success'] as const)('reports the %s variant politely', (variant) => {
    render(<Toast variant={variant}>Saved.</Toast>)

    expect(screen.getByRole('status')).toHaveTextContent('Saved.')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('interrupts for a failure', () => {
    render(<Toast variant="danger">That did not send.</Toast>)

    expect(screen.getByRole('alert')).toHaveTextContent('That did not send.')
  })

  it.each(['info', 'success', 'danger'] as const)('renders the %s styling', (variant) => {
    const { container } = render(<Toast variant={variant}>Saved.</Toast>)

    expect(container.querySelector('.oa-toast')).toHaveClass(`oa-toast--${variant}`)
  })

  it('has no close button unless it can be dismissed', () => {
    render(<Toast>Saved.</Toast>)

    expect(screen.queryByRole('button')).toBeNull()
  })

  it('dismisses when the close button is pressed', async () => {
    const onDismiss = vi.fn()
    render(<Toast onDismiss={onDismiss}>Saved.</Toast>)

    // An icon-only button, so this also checks it carries a name rather
    // than announcing itself as "button".
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('hides its icon from the accessibility tree', () => {
    const { container } = render(<Toast variant="danger">That did not send.</Toast>)

    expect(container.querySelector('.oa-toast__icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })
})
