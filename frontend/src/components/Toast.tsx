/**
 * Toast (ON-64).
 *
 * A short message about something that just happened: a document uploaded,
 * an escalation sent, a request that failed.
 *
 * The component is only the message. Where toasts stack and how long they
 * stay is the app shell's business (ON-65), because a component that owns
 * its own timer cannot be tested without one.
 *
 * `role` is the part that matters. A failure interrupts whatever a screen
 * reader is saying; a success waits its turn. Using `alert` for both is the
 * common mistake, and it makes a routine confirmation shout.
 */
import type { ReactNode } from 'react'

import Button from './Button'
import { cx } from './classNames'
import { CircleCheckBig, Info, TriangleAlert, X } from './icons'
import './Toast.css'

export type ToastVariant = 'info' | 'success' | 'danger'

export interface ToastProps {
  variant?: ToastVariant
  /** A heading above the message. Optional: most toasts are one line. */
  title?: string
  children: ReactNode
  /** Shows a close button when given. */
  onDismiss?: () => void
  className?: string
}

const ICONS = {
  info: Info,
  success: CircleCheckBig,
  danger: TriangleAlert,
}

export default function Toast({
  variant = 'info',
  title,
  children,
  onDismiss,
  className,
}: ToastProps) {
  const Icon = ICONS[variant]

  return (
    <div
      className={cx('oa-toast', `oa-toast--${variant}`, className)}
      role={variant === 'danger' ? 'alert' : 'status'}
    >
      <Icon className="oa-toast__icon" aria-hidden="true" />
      <div className="oa-toast__text">
        {title !== undefined && <p className="oa-toast__title">{title}</p>}
        <p className="oa-toast__message">{children}</p>
      </div>
      {onDismiss !== undefined && (
        <Button
          variant="ghost"
          size="sm"
          icon={<X />}
          aria-label="Dismiss"
          onClick={onDismiss}
        />
      )}
    </div>
  )
}
