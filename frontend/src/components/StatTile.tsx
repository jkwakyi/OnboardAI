/**
 * StatTile (ON-64).
 *
 * One number, said once: an uppercase label, the value at display size, an
 * optional caption underneath, and an optional progress ring beside it.
 *
 * When a ring is shown the tile passes its own label down, so the ring
 * announces "Documents processed: 72%" rather than a bare percentage next
 * to text a screen reader has already moved past.
 */
import type { ReactNode } from 'react'

import { accentClass, type Accent } from './accents'
import { cx } from './classNames'
import ProgressRing from './ProgressRing'
import './StatTile.css'

export interface StatTileProps {
  label: string
  value: ReactNode
  /** A line under the value: a unit, a comparison, a timestamp. */
  caption?: string
  /** 0 to 100. Draws a progress ring beside the value when given. */
  percent?: number
  accent?: Accent
  className?: string
}

export default function StatTile({
  label,
  value,
  caption,
  percent,
  accent = 'info',
  className,
}: StatTileProps) {
  return (
    <div className={cx('oa-stat', accentClass(accent), className)}>
      <div className="oa-stat__text">
        <p className="section-label oa-stat__label">{label}</p>
        <p className="oa-stat__value">{value}</p>
        {caption !== undefined && <p className="oa-stat__caption">{caption}</p>}
      </div>
      {percent !== undefined && (
        <ProgressRing value={percent} label={label} accent={accent} />
      )}
    </div>
  )
}
