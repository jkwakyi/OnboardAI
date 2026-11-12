/**
 * StatTile (ON-64).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StatTile from './StatTile'

describe('StatTile', () => {
  it('shows the label and the value', () => {
    render(<StatTile label="Documents" value={12} />)

    expect(screen.getByText('Documents')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('shows a caption when there is one', () => {
    render(<StatTile label="Documents" value={12} caption="2 added this week" />)

    expect(screen.getByText('2 added this week')).toBeInTheDocument()
  })

  it('has no ring unless a percentage is given', () => {
    render(<StatTile label="Documents" value={12} />)

    expect(screen.queryByRole('img')).toBeNull()
  })

  it('names the ring after the tile, so the percentage has a subject', () => {
    // A ring announcing a bare "72%" beside a label a screen reader has
    // already read is the failure this guards against.
    render(<StatTile label="Documents processed" value="72%" percent={72} />)

    expect(
      screen.getByRole('img', { name: 'Documents processed: 72%' }),
    ).toBeInTheDocument()
  })

  it('shows a ring at zero, rather than hiding it', () => {
    // `percent={0}` is a real measurement - nothing processed yet - and a
    // truthiness check would drop it.
    render(<StatTile label="Processed" value="0%" percent={0} />)

    expect(screen.getByRole('img', { name: 'Processed: 0%' })).toBeInTheDocument()
  })

  it('gives the ring the tile accent', () => {
    const { container } = render(
      <StatTile label="Escalations" value={3} percent={30} accent="escalations" />,
    )

    expect(container.querySelector('.oa-ring')).toHaveClass('oa-accent-escalations')
  })
})
