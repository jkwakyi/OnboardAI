/**
 * CitationChip (ON-64).
 *
 * The source under an answer: which approved document it came from, and
 * where in it. The chat page (ON-48) hangs the "show me that section"
 * behaviour off `onClick`.
 *
 * It is a button even before anything is wired to it, because the ticket
 * asks for it to be focusable and a focusable `<span>` is a thing that
 * takes a keyboard user's time and then does nothing with it. A button at
 * least announces itself as something that can be pressed.
 */
import type { ButtonHTMLAttributes } from 'react'

import { cx } from './classNames'
import { Quote } from './icons'
import './CitationChip.css'

export interface CitationChipProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'title'> {
  /** The approved document the answer was drawn from. */
  title: string
  /** Where in it: a section heading, a page, a clause number. */
  location: string
}

export default function CitationChip({
  title,
  location,
  className,
  ...rest
}: CitationChipProps) {
  return (
    // The visible chip reads "Employee Handbook  Section 4.2", with the
    // two parts styled differently. Spelled out as a label because the
    // name computed from adjacent spans runs them together, and because a
    // screen reader meets this chip without the answer it was attached to.
    <button
      type="button"
      className={cx('oa-citation', className)}
      aria-label={`Source: ${title}, ${location}`}
      {...rest}
    >
      <Quote className="oa-citation__icon" aria-hidden="true" />
      <span className="oa-citation__title">{title}</span>
      <span className="oa-citation__location">{location}</span>
    </button>
  )
}
