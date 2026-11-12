/**
 * Skeleton (ON-64).
 *
 * The shape of the content that is coming, while it is still on its way.
 * Better than a spinner in a list, because the page does not jump when the
 * data lands.
 *
 * The bars themselves are hidden from the accessibility tree - they are a
 * drawing of text that does not exist yet - and one `role="status"` says
 * "Loading" in their place. Without that, a screen reader gets silence.
 */
import { cx } from './classNames'
import './Skeleton.css'

export interface SkeletonProps {
  /** Number of text bars. Ignored when `variant` is `block`. */
  lines?: number
  /** `text` draws bars; `block` draws one filled rectangle. */
  variant?: 'text' | 'block'
  /** What is loading, announced once. */
  label?: string
  className?: string
}

export default function Skeleton({
  lines = 3,
  variant = 'text',
  label = 'Loading',
  className,
}: SkeletonProps) {
  // A block is one shape; text is however many bars were asked for, and at
  // least one, because a skeleton of nothing is just a gap.
  const count = variant === 'block' ? 1 : Math.max(1, Math.trunc(lines))

  return (
    <div
      className={cx('oa-skeleton', `oa-skeleton--${variant}`, className)}
      role="status"
      aria-busy="true"
    >
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: count }, (_unused, index) => (
        <span
          className="oa-skeleton__bar"
          // The bars are interchangeable and never reordered, so the index
          // is the whole of their identity.
          key={index}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}
