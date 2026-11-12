/**
 * StatusPill (ON-64).
 *
 * The small rounded label beside a document or an escalation. Four
 * variants: the three status colours plus a neutral one for a state that
 * is neither good nor bad, such as a document still queued.
 *
 * The pill deliberately takes a variant rather than a status string. The
 * statuses themselves belong to the Interface Contracts, and a component
 * that knew their names would have to be edited every time one was added.
 */
import type { HTMLAttributes, ReactNode } from 'react'

import { cx } from './classNames'
import './StatusPill.css'

export type StatusVariant = 'success' | 'warning' | 'danger' | 'neutral'

export interface StatusPillProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: StatusVariant
  children: ReactNode
}

export default function StatusPill({
  variant = 'neutral',
  className,
  children,
  ...rest
}: StatusPillProps) {
  return (
    // The text is the status. Colour is a second signal on top of it, never
    // the only one, which is what WCAG 1.4.1 asks and what makes the pill
    // readable in a greyscale screenshot.
    <span className={cx('oa-pill', `oa-pill--${variant}`, className)} {...rest}>
      {children}
    </span>
  )
}
