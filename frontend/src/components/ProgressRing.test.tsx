/**
 * ProgressRing (ON-64).
 *
 * Two things are worth checking: that the arc length actually follows the
 * value, and that the ring and the stylesheet still agree about how thick
 * the stroke is. The second is the one that breaks quietly - the radius is
 * derived from the thickness in TypeScript, and the stroke is applied from
 * a token in CSS, so changing one leaves a donut with a stroke hanging
 * over its own edge and nothing fails.
 */
import { readFileSync } from 'node:fs'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ProgressRing, { RING_THICKNESS } from './ProgressRing'
import { fromSrc } from '../test/paths'

/** The arc, as a fraction of the circle, from the rendered attributes. */
function drawnFraction(container: HTMLElement): number {
  const arc = container.querySelector('.oa-ring__value')
  if (arc === null) {
    throw new Error('the ring drew no arc')
  }

  const circumference = Number(arc.getAttribute('stroke-dasharray'))
  const offset = Number(arc.getAttribute('stroke-dashoffset'))
  return (circumference - offset) / circumference
}

describe('ProgressRing', () => {
  it('is one image, named after what it measures', () => {
    render(<ProgressRing value={72} label="Documents processed" />)

    expect(
      screen.getByRole('img', { name: 'Documents processed: 72%' }),
    ).toBeInTheDocument()
  })

  it('shows the rounded percentage in the middle', () => {
    render(<ProgressRing value={72.4} label="Done" />)

    expect(screen.getByText('72%')).toBeInTheDocument()
  })

  it.each([
    [0, 0],
    [25, 0.25],
    [50, 0.5],
    [100, 1],
  ])('draws %i%% as %f of the circle', (value, expected) => {
    const { container } = render(<ProgressRing value={value} label="Done" />)

    expect(drawnFraction(container)).toBeCloseTo(expected, 5)
  })

  it.each([
    [-20, 0],
    [140, 1],
    [Number.NaN, 0],
    [Number.POSITIVE_INFINITY, 1],
  ])('clamps %p to %f of the circle', (value, expected) => {
    // A value out of range should not produce a dash offset that makes the
    // arc wrap back over itself, which is what an unclamped value does.
    const { container } = render(<ProgressRing value={value} label="Done" />)

    expect(drawnFraction(container)).toBeCloseTo(expected, 5)
  })

  it('reports a clamped value honestly in its label', () => {
    render(<ProgressRing value={140} label="Done" />)

    expect(screen.getByRole('img', { name: 'Done: 100%' })).toBeInTheDocument()
  })

  it.each(['chat', 'documents', 'escalations', 'info'] as const)(
    'carries the %s accent',
    (accent) => {
      const { container } = render(<ProgressRing value={50} label="Done" accent={accent} />)

      expect(container.querySelector('.oa-ring')).toHaveClass(`oa-accent-${accent}`)
    },
  )

  it('hides its own drawing from the accessibility tree', () => {
    // Otherwise the 72% is read twice: once from the label, once from the
    // text in the middle.
    const { container } = render(<ProgressRing value={72} label="Done" />)

    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.oa-ring__percent')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })

  it('uses the same stroke width the stylesheet applies', () => {
    const tokens = readFileSync(fromSrc('styles', 'tokens.css'), 'utf8')
    const declared = /--ring-thickness:\s*([\d.]+)\s*;/.exec(tokens)

    expect(declared, '--ring-thickness is not declared in tokens.css').not.toBeNull()
    expect(
      Number(declared?.[1]),
      'tokens.css and ProgressRing.tsx disagree about the stroke, so the ' +
        'radius no longer keeps the stroke inside the viewBox',
    ).toBe(RING_THICKNESS)
  })
})
