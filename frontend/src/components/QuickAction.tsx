/**
 * QuickAction (ON-64).
 *
 * The button in the left rail that starts something: ask a question, upload
 * a document, open an escalation. Full width, a plus in an accent-tinted
 * square, and the label beside it.
 *
 * It is a Button underneath rather than a second button implementation, so
 * the disabled, loading and focus behaviour is the one that is already
 * tested.
 */
import { accentClass, type Accent } from './accents'
import Button, { type ButtonProps } from './Button'
import { cx } from './classNames'
import { Plus } from './icons'
import './QuickAction.css'

export interface QuickActionProps
  extends Omit<ButtonProps, 'children' | 'variant' | 'size' | 'icon'> {
  label: string
  accent?: Accent
}

export default function QuickAction({
  label,
  accent = 'info',
  className,
  ...rest
}: QuickActionProps) {
  return (
    <Button
      variant="ghost"
      className={cx('oa-quick', accentClass(accent), className)}
      icon={<Plus />}
      {...rest}
    >
      {label}
    </Button>
  )
}
