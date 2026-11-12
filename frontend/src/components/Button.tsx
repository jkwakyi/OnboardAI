/**
 * Button (ON-64).
 *
 * Four variants, two sizes, and a loading state that disables the control
 * and says `aria-busy` rather than only spinning something.
 *
 * The exported type is a union: a button either has children, or it has an
 * `aria-label`. That is what makes an icon-only button without an
 * accessible name a compile error instead of a thing someone notices in a
 * screen reader three tickets later.
 */
import type { ButtonHTMLAttributes, ReactElement, ReactNode } from 'react'

import { cx } from './classNames'
import { LoaderCircle } from './icons'
import './Button.css'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md'

interface ButtonBaseProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Drawn before the label, and replaced by the spinner while loading. */
  icon?: ReactNode
  /** Disables the button, shows a spinner and sets `aria-busy`. */
  loading?: boolean
}

/**
 * Either a visible label, or an invisible one. `children?: never` is what
 * stops the second form being satisfied by passing both.
 */
type AccessibleName = { children: ReactNode } | { children?: never; 'aria-label': string }

export type ButtonProps = ButtonBaseProps & AccessibleName

function ButtonImpl({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonBaseProps) {
  const iconOnly = children === undefined

  return (
    <button
      // eslint-disable-next-line react/button-has-type -- defaulted above
      type={type}
      className={cx(
        'oa-button',
        `oa-button--${variant}`,
        `oa-button--${size}`,
        iconOnly && 'oa-button--icon-only',
        loading && 'oa-button--loading',
        className,
      )}
      // A button that is busy is also not clickable, so the two states are
      // set together and never drift apart.
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <LoaderCircle className="oa-button__spinner" aria-hidden="true" />
      ) : (
        icon !== undefined && (
          <span className="oa-button__icon" aria-hidden="true">
            {icon}
          </span>
        )
      )}
      {!iconOnly && <span className="oa-button__label">{children}</span>}
    </button>
  )
}

/**
 * The cast is what narrows the public signature to the union above. The
 * implementation stays a plain function over one interface, which is what
 * makes destructuring the props readable, while the call site still has to
 * supply an accessible name.
 */
const Button = ButtonImpl as (props: ButtonProps) => ReactElement

export default Button
