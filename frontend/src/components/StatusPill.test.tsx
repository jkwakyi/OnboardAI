/**
 * StatusPill (ON-64).
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StatusPill from './StatusPill'

describe('StatusPill', () => {
  it('shows the status as text', () => {
    // WCAG 1.4.1: the colour is a second signal, never the only one. If
    // this ever became an icon-only dot, the status would be invisible in
    // a greyscale screenshot and to anyone who cannot distinguish the
    // three status hues.
    render(<StatusPill variant="success">Processed</StatusPill>)

    expect(screen.getByText('Processed')).toBeInTheDocument()
  })

  it.each(['success', 'warning', 'danger', 'neutral'] as const)(
    'renders the %s variant',
    (variant) => {
      render(<StatusPill variant={variant}>Status</StatusPill>)

      expect(screen.getByText('Status')).toHaveClass(`oa-pill--${variant}`)
    },
  )

  it('is neutral by default', () => {
    // A status nobody classified should not arrive looking like a success.
    render(<StatusPill>Queued</StatusPill>)

    expect(screen.getByText('Queued')).toHaveClass('oa-pill--neutral')
  })

  it('passes through the attributes a caller adds', () => {
    render(<StatusPill title="Last checked at 09:12">Processed</StatusPill>)

    expect(screen.getByText('Processed')).toHaveAttribute('title', 'Last checked at 09:12')
  })
})
