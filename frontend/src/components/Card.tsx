/**
 * Card (ON-64).
 *
 * The surface everything on a page sits in: a rounded panel with a thin
 * border, an optional uppercase section label, and an optional accent rule
 * along the top saying which area of the app it belongs to.
 *
 * It renders a `<section>` and wires `aria-labelledby` to the label when
 * there is one, so the cards on a page show up as named regions rather
 * than as a flat run of text.
 */
import type { HTMLAttributes, ReactNode } from 'react'
import { useId } from 'react'

import { accentClass, type Accent } from './accents'
import { cx } from './classNames'
import './Card.css'

export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** The uppercase section label above the card's contents. */
  label?: string
  /** Draws an accent rule along the top edge. */
  accent?: Accent
  /** Shown at the end of the label row: a count, a button, a status pill. */
  action?: ReactNode
  children?: ReactNode
}

export default function Card({
  label,
  accent,
  action,
  className,
  children,
  ...rest
}: CardProps) {
  const labelId = useId()

  return (
    <section
      className={cx(
        'oa-card',
        accent !== undefined && 'oa-card--accented',
        accent !== undefined && accentClass(accent),
        className,
      )}
      aria-labelledby={label === undefined ? undefined : labelId}
      {...rest}
    >
      {(label !== undefined || action !== undefined) && (
        <div className="oa-card__header">
          {label !== undefined && (
            <h2 className="section-label oa-card__label" id={labelId}>
              {label}
            </h2>
          )}
          {action !== undefined && <div className="oa-card__action">{action}</div>}
        </div>
      )}
      <div className="oa-card__body">{children}</div>
    </section>
  )
}
