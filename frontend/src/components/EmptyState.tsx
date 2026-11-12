/**
 * EmptyState (ON-64).
 *
 * What a list says when it has nothing in it. Three parts, and the second
 * one is the one that gets skipped: a title that names the emptiness, a
 * description saying why it is empty or what would fill it, and the action
 * that would.
 *
 * "No documents" on its own tells an HR administrator nothing they could
 * not see. "No documents yet - upload a PDF or TXT file and employees can
 * ask about it" tells them what to do next.
 */
import type { ReactNode } from 'react'

import { cx } from './classNames'
import { Inbox } from './icons'
import './EmptyState.css'

export interface EmptyStateProps {
  /** Defaults to a tray. Pass an icon that matches what is missing. */
  icon?: ReactNode
  title: string
  description?: string
  /** Normally a Button: the thing that would end the emptiness. */
  action?: ReactNode
  /** `danger` tints the icon: used by ErrorState. */
  tone?: 'neutral' | 'danger'
  className?: string
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  className,
}: EmptyStateProps) {
  return (
    <div className={cx('oa-empty', `oa-empty--${tone}`, className)}>
      <span className="oa-empty__icon" aria-hidden="true">
        {icon ?? <Inbox />}
      </span>
      <p className="oa-empty__title">{title}</p>
      {description !== undefined && <p className="oa-empty__description">{description}</p>}
      {action !== undefined && <div className="oa-empty__action">{action}</div>}
    </div>
  )
}
