/**
 * Button (ON-64).
 *
 * The loading state is the one worth testing hard. It is three separate
 * promises - a spinner, `aria-busy`, and no second submission - and any one
 * of them can be dropped without the other two looking wrong.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import Button from './Button'
import { Plus } from './icons'

describe('Button', () => {
  it('renders its label and is a button, not a submit', () => {
    // A bare <button> inside a form submits it. Defaulting to "button" is
    // what stops a toolbar action posting the form it happens to sit in.
    render(<Button>Upload</Button>)

    const button = screen.getByRole('button', { name: 'Upload' })
    expect(button).toHaveAttribute('type', 'button')
  })

  it('can still be a submit button when asked', () => {
    render(<Button type="submit">Sign in</Button>)

    expect(screen.getByRole('button', { name: 'Sign in' })).toHaveAttribute('type', 'submit')
  })

  it.each(['primary', 'secondary', 'ghost', 'danger'] as const)(
    'renders the %s variant',
    (variant) => {
      render(<Button variant={variant}>Go</Button>)

      expect(screen.getByRole('button')).toHaveClass(`oa-button--${variant}`)
    },
  )

  it.each(['sm', 'md'] as const)('renders the %s size', (size) => {
    render(<Button size={size}>Go</Button>)

    expect(screen.getByRole('button')).toHaveClass(`oa-button--${size}`)
  })

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Send</Button>)

    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is reachable and operable from the keyboard', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Send</Button>)

    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Send' })).toHaveFocus()

    await userEvent.keyboard('{Enter}')
    await userEvent.keyboard(' ')

    expect(onClick).toHaveBeenCalledTimes(2)
  })

  describe('while loading', () => {
    it('says so, and refuses a second press', async () => {
      const onClick = vi.fn()
      render(
        <Button loading onClick={onClick}>
          Send
        </Button>,
      )

      const button = screen.getByRole('button', { name: 'Send' })
      expect(button).toHaveAttribute('aria-busy', 'true')
      expect(button).toBeDisabled()

      await userEvent.click(button)
      expect(onClick).not.toHaveBeenCalled()
    })

    it('shows a spinner in place of the icon', () => {
      const { container } = render(
        <Button loading icon={<Plus />}>
          Send
        </Button>,
      )

      expect(container.querySelector('.oa-button__spinner')).not.toBeNull()
      expect(container.querySelector('.oa-button__icon')).toBeNull()
    })

    it('keeps the label, so the button does not change width', () => {
      render(<Button loading>Send</Button>)

      expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
    })
  })

  it('does not fire when disabled', async () => {
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        Send
      </Button>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('renders an icon before the label', () => {
    const { container } = render(<Button icon={<Plus />}>Add</Button>)

    const icon = container.querySelector('.oa-button__icon')
    expect(icon).not.toBeNull()
    // Hidden, because the label already says what the button does and
    // "plus Add" is not an improvement on "Add".
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  describe('an icon-only button', () => {
    it('takes its accessible name from aria-label', () => {
      render(<Button icon={<Plus />} aria-label="Add a document" />)

      expect(screen.getByRole('button', { name: 'Add a document' })).toHaveClass(
        'oa-button--icon-only',
      )
    })

    it('does not compile without one', () => {
      // Checked by `tsc -b`, which covers this file: if the union in
      // Button.tsx ever stops requiring a label, the directive below
      // becomes unused and the build fails. The call is never rendered -
      // it only has to be type-checked.
      const unlabelled = () =>
        // @ts-expect-error - an icon-only button must carry an aria-label
        <Button icon={<Plus />} />

      expect(unlabelled).toBeTypeOf('function')
    })
  })
})
