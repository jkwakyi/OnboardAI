/**
 * ProgressRing (ON-64).
 *
 * The donut inside a stat tile. An SVG rather than two nested divs, so it
 * stays crisp at any size and the arc is one stroke instead of a stack of
 * clipped boxes.
 *
 * The ring is one image to a screen reader: `role="img"` with a label on
 * the wrapper, and everything inside hidden. Reading out a `<circle>` and a
 * stray "72%" tells nobody what the 72% was of.
 */
import { accentClass, type Accent } from './accents'
import { cx } from './classNames'
import './ProgressRing.css'

/**
 * The ring is drawn in a 100 x 100 viewBox, so every number below is a
 * percentage of its own width and the shape holds at any --ring-size.
 */
const VIEWBOX = 100

/**
 * The stroke, in those same units.
 *
 * It is also declared as `--ring-thickness` in tokens.css, because the
 * stylesheet is what applies it; this copy is what the radius is derived
 * from. `ProgressRing.test.tsx` fails if the two stop agreeing.
 */
export const RING_THICKNESS = 10

/** Half the box, less half a stroke, so the stroke lands inside the box. */
const RADIUS = (VIEWBOX - RING_THICKNESS) / 2

const CIRCUMFERENCE = 2 * Math.PI * RADIUS

const CENTRE = VIEWBOX / 2

export interface ProgressRingProps {
  /** 0 to 100. Anything outside that range, or not a number, is clamped. */
  value: number
  /** What the percentage measures, read out before it. */
  label: string
  accent?: Accent
  className?: string
}

/**
 * 0 to 100.
 *
 * NaN means the caller has no number yet, which is nothing done rather
 * than a blank ring. Infinity is a number, just a very large one, so it
 * clamps like any other value out of range.
 */
function clampPercent(value: number): number {
  if (Number.isNaN(value)) {
    return 0
  }
  return Math.min(100, Math.max(0, value))
}

export default function ProgressRing({
  value,
  label,
  accent = 'info',
  className,
}: ProgressRingProps) {
  const percent = clampPercent(value)
  const shown = Math.round(percent)

  return (
    <div
      className={cx('oa-ring', accentClass(accent), className)}
      role="img"
      aria-label={`${label}: ${shown}%`}
    >
      <svg className="oa-ring__svg" viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`} aria-hidden="true">
        <circle className="oa-ring__track" cx={CENTRE} cy={CENTRE} r={RADIUS} />
        <circle
          className="oa-ring__value"
          cx={CENTRE}
          cy={CENTRE}
          r={RADIUS}
          strokeDasharray={CIRCUMFERENCE}
          // The gap starts where the arc should stop. A full ring leaves no
          // gap; an empty one is all gap.
          strokeDashoffset={CIRCUMFERENCE * (1 - percent / 100)}
        />
      </svg>
      <span className="oa-ring__percent" aria-hidden="true">
        {shown}%
      </span>
    </div>
  )
}
