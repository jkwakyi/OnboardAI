/**
 * CitationChip (ON-64).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import CitationChip from './CitationChip'

describe('CitationChip', () => {
  it('names its source and where in it', () => {
    // "Section 4.2" on its own is not a citation. The accessible name has
    // to carry the document too, because a screen reader reads the chip
    // without the answer it was attached to.
    render(<CitationChip title="Employee Handbook" location="Section 4.2" />)

    expect(
      screen.getByRole('button', { name: 'Source: Employee Handbook, Section 4.2' }),
    ).toBeInTheDocument()
  })

  it('is focusable', async () => {
    render(<CitationChip title="Employee Handbook" location="Section 4.2" />)

    await userEvent.tab()

    expect(screen.getByRole('button')).toHaveFocus()
  })

  it('activates from the keyboard', async () => {
    const onClick = vi.fn()
    render(
      <CitationChip title="Employee Handbook" location="Section 4.2" onClick={onClick} />,
    )

    await userEvent.tab()
    await userEvent.keyboard('{Enter}')

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('does not submit a form it happens to sit in', () => {
    render(<CitationChip title="Employee Handbook" location="Section 4.2" />)

    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })

  it('hides the quote mark from the accessibility tree', () => {
    const { container } = render(
      <CitationChip title="Employee Handbook" location="Section 4.2" />,
    )

    expect(container.querySelector('.oa-citation__icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })
})
