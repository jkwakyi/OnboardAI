/**
 * Skeleton (ON-64).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Skeleton from './Skeleton'

function bars(container: HTMLElement): Element[] {
  return [...container.querySelectorAll('.oa-skeleton__bar')]
}

describe('Skeleton', () => {
  it('says that something is loading', () => {
    // The bars are a drawing of text that does not exist yet, so they are
    // hidden. Without this one announcement a screen reader gets silence
    // while the page waits.
    render(<Skeleton />)

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Loading')
    expect(status).toHaveAttribute('aria-busy', 'true')
  })

  it('names what is loading when told', () => {
    render(<Skeleton label="Loading documents" />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading documents')
  })

  it('draws three bars by default', () => {
    const { container } = render(<Skeleton />)

    expect(bars(container)).toHaveLength(3)
  })

  it('draws the number of bars asked for', () => {
    const { container } = render(<Skeleton lines={5} />)

    expect(bars(container)).toHaveLength(5)
  })

  it.each([0, -3, 0.5])('draws at least one bar when asked for %p', (lines) => {
    // A skeleton of nothing is a gap, which reads as a broken layout
    // rather than as waiting.
    const { container } = render(<Skeleton lines={lines} />)

    expect(bars(container)).toHaveLength(1)
  })

  it('draws one shape in block form, whatever the line count', () => {
    const { container } = render(<Skeleton variant="block" lines={4} />)

    expect(bars(container)).toHaveLength(1)
    expect(container.querySelector('.oa-skeleton')).toHaveClass('oa-skeleton--block')
  })

  it('hides every bar from the accessibility tree', () => {
    const { container } = render(<Skeleton lines={3} />)

    for (const bar of bars(container)) {
      expect(bar).toHaveAttribute('aria-hidden', 'true')
    }
  })
})
