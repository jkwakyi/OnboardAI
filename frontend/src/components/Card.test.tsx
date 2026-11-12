/**
 * Card (ON-64).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Card from './Card'

describe('Card', () => {
  it('renders its children', () => {
    render(<Card>Inside</Card>)

    expect(screen.getByText('Inside')).toBeInTheDocument()
  })

  it('names the region after its label', () => {
    // The point of the label is that a page of cards reads as a set of
    // named regions rather than one long run of text. A visible heading
    // that is not wired to the section does not do that.
    render(<Card label="Recent documents">Inside</Card>)

    const region = screen.getByRole('region', { name: 'Recent documents' })
    expect(region).toContainElement(screen.getByRole('heading', { name: 'Recent documents' }))
  })

  it('is an unnamed section when there is no label', () => {
    render(<Card>Inside</Card>)

    // An unlabelled <section> is deliberately not a landmark: announcing
    // "region" with no name is noise.
    expect(screen.queryByRole('region')).toBeNull()
  })

  it.each(['chat', 'documents', 'escalations', 'info'] as const)(
    'carries the %s accent',
    (accent) => {
      const { container } = render(<Card accent={accent}>Inside</Card>)

      const card = container.querySelector('.oa-card')
      expect(card).toHaveClass(`oa-accent-${accent}`)
      expect(card).toHaveClass('oa-card--accented')
    },
  )

  it('draws no accent rule when no accent is given', () => {
    const { container } = render(<Card>Inside</Card>)

    expect(container.querySelector('.oa-card')).not.toHaveClass('oa-card--accented')
  })

  it('renders an action beside the label', () => {
    render(
      <Card label="Documents" action={<button type="button">Upload</button>}>
        Inside
      </Card>,
    )

    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
  })

  it('renders an action even without a label', () => {
    // Easy to drop: the header only exists because of the label, so an
    // action passed on its own silently disappears.
    render(<Card action={<button type="button">Upload</button>}>Inside</Card>)

    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
  })
})
