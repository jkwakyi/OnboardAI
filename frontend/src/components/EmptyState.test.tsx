/**
 * EmptyState and ErrorState (ON-64).
 *
 * They share a file because ErrorState is an EmptyState with a tone and a
 * retry button, and testing them apart would mean testing the same markup
 * twice.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import Button from './Button'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'

describe('EmptyState', () => {
  it('shows a title and a description', () => {
    render(
      <EmptyState
        title="No documents yet"
        description="Upload a PDF or TXT file and employees can ask about it."
      />,
    )

    expect(screen.getByText('No documents yet')).toBeInTheDocument()
    expect(
      screen.getByText('Upload a PDF or TXT file and employees can ask about it.'),
    ).toBeInTheDocument()
  })

  it('works with a title alone', () => {
    render(<EmptyState title="Nothing here" />)

    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('renders the action that would end the emptiness', async () => {
    const onClick = vi.fn()
    render(
      <EmptyState
        title="No documents yet"
        action={<Button onClick={onClick}>Upload a document</Button>}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Upload a document' }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is neutral by default and hides its icon', () => {
    const { container } = render(<EmptyState title="Nothing here" />)

    expect(container.querySelector('.oa-empty')).toHaveClass('oa-empty--neutral')
    expect(container.querySelector('.oa-empty__icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })
})

describe('ErrorState', () => {
  it('always offers a way out', async () => {
    // Without a retry the only escape is a page reload, and a reload loses
    // whatever the user had typed.
    const onRetry = vi.fn()
    render(<ErrorState onRetry={onRetry} />)

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('says nothing was changed, which is the thing people want to know', () => {
    render(<ErrorState onRetry={vi.fn()} />)

    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument()
  })

  it('takes its own wording when the caller has something better', () => {
    render(
      <ErrorState
        title="Could not reach the HR Inbox"
        description="The escalation was not sent."
        retryLabel="Send again"
        onRetry={vi.fn()}
      />,
    )

    expect(screen.getByText('Could not reach the HR Inbox')).toBeInTheDocument()
    expect(screen.getByText('The escalation was not sent.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send again' })).toBeInTheDocument()
  })

  it('is drawn in the danger tone', () => {
    const { container } = render(<ErrorState onRetry={vi.fn()} />)

    expect(container.querySelector('.oa-empty')).toHaveClass('oa-empty--danger')
  })
})
